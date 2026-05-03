"""Admin routes blueprint — database utilities, reconciliation, backup, demo."""
import json
import logging
import os
import uuid
from typing import Any, Optional

import requests
from flask import Blueprint, Response, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import text

from database_api.model_event import EventItem, EventType
from database_api.model_planitem import PlanItem, PlanState
from database_api.planexe_db_singleton import db

from src.utils import safe_float, safe_int

logger = logging.getLogger(__name__)

admin_routes_bp = Blueprint("admin_routes", __name__)


def _admin_required(view):
    """Decorator that requires an authenticated admin user."""
    from functools import wraps
    from flask import abort
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def _read_activity_overview_from_task(task: PlanItem) -> Optional[dict[str, Any]]:
    import io
    import zipfile
    from worker_plan_api.filenames import ExtraFilenameEnum
    raw_payload = getattr(task, "run_activity_overview_json", None)
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        try:
            decoded_payload = json.loads(raw_payload)
            if isinstance(decoded_payload, dict):
                return decoded_payload
        except Exception as exc:
            logger.warning("Unable to parse task.run_activity_overview_json for %s: %s", task.id, exc)
    # Fallback: read from run_zip_snapshot
    run_zip_snapshot = task.run_zip_snapshot
    if not run_zip_snapshot:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(run_zip_snapshot), "r") as archive:
            activity_name = ExtraFilenameEnum.ACTIVITY_OVERVIEW_JSON.value
            for member_name in archive.namelist():
                if member_name.endswith(activity_name):
                    payload = json.loads(archive.read(member_name).decode("utf-8"))
                    if isinstance(payload, dict):
                        return payload
                    return None
    except Exception as exc:
        logger.warning("Unable to parse run_zip_snapshot activity overview: %s", exc)
    return None


def _read_inference_cost_from_task(task: PlanItem) -> Optional[float]:
    payload = _read_activity_overview_from_task(task)
    if not isinstance(payload, dict):
        return None
    return safe_float(payload.get("total_cost"))


def _get_database_size_info() -> dict[str, Any]:
    info: dict[str, Any] = {"error": None, "database_name": None, "total_bytes": 0, "total_mb": 0.0, "tables": []}
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(), pg_database_size(current_database())"
            )).fetchone()
            if row:
                info["database_name"] = row[0]
                info["total_bytes"] = row[1]
                info["total_mb"] = round(row[1] / (1024 * 1024), 2)

            tables = conn.execute(text(
                "SELECT schemaname, tablename, "
                "pg_total_relation_size(schemaname || '.' || tablename) AS total_bytes, "
                "pg_relation_size(schemaname || '.' || tablename) AS table_bytes, "
                "pg_total_relation_size(schemaname || '.' || tablename) - pg_relation_size(schemaname || '.' || tablename) AS index_bytes "
                "FROM pg_tables WHERE schemaname = 'public' "
                "ORDER BY total_bytes DESC"
            )).fetchall()
            for t in tables:
                info["tables"].append({
                    "name": t[1],
                    "total_bytes": t[2],
                    "total_mb": round(t[2] / (1024 * 1024), 2),
                    "table_mb": round(t[3] / (1024 * 1024), 2),
                    "index_mb": round(t[4] / (1024 * 1024), 2),
                })
    except Exception as e:
        logger.exception("Failed to query database size")
        info["error"] = str(e)
    return info


def _get_purge_activity_info() -> dict[str, Any]:
    info: dict[str, Any] = {"error": None, "total_rows": 0, "rows_with_data": 0, "total_data_mb": 0.0, "options": []}
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT count(*), "
                "count(run_track_activity_jsonl), "
                "coalesce(sum(octet_length(run_track_activity_jsonl)), 0) "
                "FROM plans"
            )).fetchone()
            if row:
                info["total_rows"] = row[0]
                info["rows_with_data"] = row[1]
                info["total_data_mb"] = round(row[2] / (1024 * 1024), 2)

            for keep_n in [10, 25, 50, 100, 250, 500]:
                result = conn.execute(text(
                    "SELECT coalesce(sum(octet_length(run_track_activity_jsonl)), 0), count(*) "
                    "FROM plans "
                    "WHERE run_track_activity_jsonl IS NOT NULL "
                    "AND id NOT IN ("
                    "  SELECT id FROM plans "
                    "  ORDER BY timestamp_created DESC "
                    "  LIMIT :keep_n"
                    ")"
                ), {"keep_n": keep_n}).fetchone()
                if result:
                    info["options"].append({
                        "keep_n": keep_n,
                        "purgeable_rows": result[1],
                        "savings_bytes": result[0],
                        "savings_mb": round(result[0] / (1024 * 1024), 2),
                    })
    except Exception as e:
        logger.exception("Failed to query purge activity info")
        info["error"] = str(e)
    return info


def _purge_activity_data(keep_n: int) -> dict[str, Any]:
    result: dict[str, Any] = {"error": None, "purged_rows": 0}
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text(
                "UPDATE plans "
                "SET run_track_activity_jsonl = NULL, run_track_activity_bytes = NULL "
                "WHERE run_track_activity_jsonl IS NOT NULL "
                "AND id NOT IN ("
                "  SELECT id FROM plans "
                "  ORDER BY timestamp_created DESC "
                "  LIMIT :keep_n"
                ")"
            ), {"keep_n": keep_n})
            result["purged_rows"] = row.rowcount
            conn.commit()
    except Exception as e:
        logger.exception("Failed to purge activity data")
        result["error"] = str(e)
    return result


def _vacuum_plans() -> dict[str, Any]:
    result: dict[str, Any] = {"error": None}
    try:
        with db.engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT").execute(
                text("VACUUM FULL plans")
            )
    except Exception as e:
        logger.exception("Failed to vacuum plans")
        result["error"] = str(e)
    return result


def _proxy_backup_response() -> requests.Response:
    worker_url = os.environ.get("PLANEXE_DATABASE_WORKER_URL", "http://database_worker:8002")
    api_key = os.environ.get("PLANEXE_DATABASE_WORKER_API_KEY", "")
    headers = {}
    if api_key:
        headers["X-Database-Worker-Key"] = api_key
    resp = requests.get(f"{worker_url}/backup", headers=headers, stream=True, timeout=600)
    resp.raise_for_status()
    return resp


def _build_reconciliation_report(max_tasks: int, tolerance_usd: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tasks = (
        PlanItem.query
        .order_by(PlanItem.timestamp_created.desc())
        .limit(max_tasks)
        .all()
    )
    task_ids = {str(task.id) for task in tasks}
    billing_events_by_task_id: dict[str, EventItem] = {}
    max_event_scan = max(1000, max_tasks * 20)
    billing_events = (
        EventItem.query
        .filter(EventItem.event_type.in_([EventType.TASK_COMPLETED, EventType.TASK_FAILED]))
        .order_by(EventItem.timestamp.desc())
        .limit(max_event_scan)
        .all()
    )

    for event in billing_events:
        context = event.context if isinstance(event.context, dict) else {}
        task_id = str(context.get("task_id") or "").strip()
        if not task_id or task_id not in task_ids or task_id in billing_events_by_task_id:
            continue
        if context.get("billing_usage_cost_usd") is None:
            continue
        billing_events_by_task_id[task_id] = event
        if len(billing_events_by_task_id) == len(task_ids):
            break

    rows: list[dict[str, Any]] = []
    mismatch_count = 0
    missing_count = 0

    for task in tasks:
        task_id = str(task.id)
        tracked_usage_cost_usd = _read_inference_cost_from_task(task)

        billing_event = billing_events_by_task_id.get(task_id)
        context = billing_event.context if billing_event and isinstance(billing_event.context, dict) else {}
        billed_usage_cost_usd = safe_float(context.get("billing_usage_cost_usd"))

        delta_usd: Optional[float] = None
        status = "ok"
        if billed_usage_cost_usd is None or tracked_usage_cost_usd is None:
            status = "missing_data"
            missing_count += 1
        else:
            delta_usd = billed_usage_cost_usd - tracked_usage_cost_usd
            if abs(delta_usd) > tolerance_usd:
                status = "mismatch"
                mismatch_count += 1

        rows.append(
            {
                "task_id": task_id,
                "timestamp_created": (
                    task.timestamp_created.strftime("%Y-%m-%d %H:%M:%S")
                    if task.timestamp_created
                    else None
                ),
                "state": task.state.name if isinstance(task.state, PlanState) else str(task.state),
                "billed_usage_cost_usd": billed_usage_cost_usd,
                "tracked_usage_cost_usd": tracked_usage_cost_usd,
                "delta_usd": delta_usd,
                "status": status,
                "has_report": bool(task.has_generated_report_html),
                "has_run_zip": bool(task.has_run_zip_snapshot),
                "billing_event_timestamp": billing_event.timestamp if billing_event else None,
            }
        )

    summary = {
        "total_tasks_checked": len(rows),
        "mismatch_count": mismatch_count,
        "missing_count": missing_count,
        "ok_count": len(rows) - mismatch_count - missing_count,
        "tolerance_usd": tolerance_usd,
        "scanned_billing_events": len(billing_events),
    }
    return rows, summary


@admin_routes_bp.route("/ping")
@login_required
def ping():
    return render_template("ping.html")


@admin_routes_bp.route("/admin/reconciliation")
@_admin_required
def admin_reconciliation():
    max_tasks = int(request.args.get("limit", "200") or "200")
    max_tasks = max(1, min(max_tasks, 2000))
    tolerance_usd = safe_float(request.args.get("tolerance_usd", "0.01")) or 0.01
    tolerance_usd = max(0.0, tolerance_usd)
    refresh_seconds = int(request.args.get("refresh_seconds", "60") or "60")
    refresh_seconds = max(10, min(refresh_seconds, 3600))

    rows, summary = _build_reconciliation_report(max_tasks=max_tasks, tolerance_usd=tolerance_usd)
    has_alert = summary["mismatch_count"] > 0
    # Use Flask-Admin's render method via the admin extension
    admin_ext = current_app.extensions.get("admin", [None])
    admin_obj = admin_ext[0] if isinstance(admin_ext, list) and admin_ext else None
    if admin_obj:
        return admin_obj.index_view.render(
            "admin/reconciliation.html",
            rows=rows,
            summary=summary,
            has_alert=has_alert,
            max_tasks=max_tasks,
            tolerance_usd=tolerance_usd,
            refresh_seconds=refresh_seconds,
        )
    return render_template(
        "admin/reconciliation.html",
        rows=rows,
        summary=summary,
        has_alert=has_alert,
        max_tasks=max_tasks,
        tolerance_usd=tolerance_usd,
        refresh_seconds=refresh_seconds,
    )


@admin_routes_bp.route("/admin/database", methods=["GET", "POST"])
@_admin_required
def admin_database():
    purge_result = None
    vacuum_result = None
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "purge":
            keep_n = int(request.form.get("keep_n", "50") or "50")
            if keep_n not in (10, 25, 50, 100, 250, 500):
                keep_n = 50
            purge_result = _purge_activity_data(keep_n)
        elif action == "vacuum":
            vacuum_result = _vacuum_plans()
    size_info = _get_database_size_info()
    purge_info = _get_purge_activity_info()
    admin_ext = current_app.extensions.get("admin", [None])
    admin_obj = admin_ext[0] if isinstance(admin_ext, list) and admin_ext else None
    if admin_obj:
        return admin_obj.index_view.render(
            "admin/database.html",
            size_info=size_info,
            purge_info=purge_info,
            purge_result=purge_result,
            vacuum_result=vacuum_result,
        )
    return render_template(
        "admin/database.html",
        size_info=size_info,
        purge_info=purge_info,
        purge_result=purge_result,
        vacuum_result=vacuum_result,
    )


@admin_routes_bp.route("/admin/database/backup")
@_admin_required
def admin_database_backup():
    try:
        upstream = _proxy_backup_response()
        return Response(
            upstream.iter_content(chunk_size=256 * 1024),
            mimetype=upstream.headers.get("Content-Type", "application/octet-stream"),
            headers={
                "Content-Disposition": upstream.headers.get(
                    "Content-Disposition", 'attachment; filename="planexe_backup.sql.gz"'
                ),
            },
        )
    except Exception as e:
        logger.exception("Failed to proxy database backup")
        return jsonify({"error": str(e)}), 502


@admin_routes_bp.route("/ping/list")
@login_required
def ping_list():
    worker_plan_url = current_app.config["WORKER_PLAN_URL"]
    url = f"{worker_plan_url}/llm-list"
    try:
        resp = requests.get(url, timeout=(5, 30))
    except Exception as exc:
        logger.error("LLM ping list proxy exception: %s", exc)
        return jsonify({"error": str(exc)}), 502
    if resp.status_code != 200:
        return jsonify({"error": f"worker_plan responded with {resp.status_code}"}), 502
    return jsonify(resp.json())


@admin_routes_bp.route("/ping/one")
@login_required
def ping_one():
    worker_plan_url = current_app.config["WORKER_PLAN_URL"]
    profile = request.args.get("profile", "")
    llm_name = request.args.get("llm_name", "")
    url = f"{worker_plan_url}/llm-ping-one"
    try:
        resp = requests.get(
            url,
            params={"profile": profile, "llm_name": llm_name},
            timeout=(5, 300),
        )
    except Exception as exc:
        logger.error("LLM ping-one proxy exception: %s", exc)
        return jsonify({
            "name": f"{profile}:{llm_name}",
            "status": "error",
            "response_time": 0,
            "response": str(exc),
        }), 502
    if resp.status_code != 200:
        return jsonify({
            "name": f"{profile}:{llm_name}",
            "status": "error",
            "response_time": 0,
            "response": f"worker_plan responded with {resp.status_code}",
        }), 502
    return jsonify(resp.json())


@admin_routes_bp.route("/admin/demo_run")
@_admin_required
def admin_demo_run():
    from src.app import _model_profile_options, DEMO_FORM_RUN_PROMPT_UUIDS
    user_id = str(current_user.id)
    nonce = "DEMO_" + str(uuid.uuid4())
    prompt_catalog = current_app.config["PROMPT_CATALOG"]
    prompts = []
    for prompt_uuid in DEMO_FORM_RUN_PROMPT_UUIDS:
        prompt_item = prompt_catalog.find(prompt_uuid)
        if prompt_item is None:
            logger.error(f"Prompt item not found for uuid: {prompt_uuid} in admin_demo_run")
            return "Error: Demo prompt configuration missing.", 500
        prompts.append(prompt_item.prompt)

    admin_ext = current_app.extensions.get("admin", [None])
    admin_obj = admin_ext[0] if isinstance(admin_ext, list) and admin_ext else None
    template_args = dict(
        user_id=user_id,
        prompts=prompts,
        nonce=nonce,
        model_profile_options=_model_profile_options(),
    )
    if admin_obj:
        return admin_obj.index_view.render("admin/demo_run.html", **template_args)
    return render_template("admin/demo_run.html", **template_args)
