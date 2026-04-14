"""Downloads blueprint — file serving for reports, zips, and activity logs."""
import io
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user, login_required

from database_api.model_planitem import PlanItem
from database_api.planexe_db_singleton import db
from worker_plan_api.filenames import ExtraFilenameEnum

from src.utils import safe_int

logger = logging.getLogger(__name__)

downloads_bp = Blueprint("downloads", __name__)


def _admin_required(view):
    from functools import wraps
    from flask import abort
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def _sanitize_legacy_run_zip_for_download(run_zip_snapshot: bytes) -> Optional[io.BytesIO]:
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            extract_dir = Path(tmp_dir) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(run_zip_snapshot), "r") as in_zip:
                in_zip.extractall(extract_dir)

            for sensitive_file in extract_dir.rglob(ExtraFilenameEnum.TRACK_ACTIVITY_JSONL.value):
                try:
                    sensitive_file.unlink()
                except OSError:
                    logger.warning("Unable to remove sensitive file from zip staging: %s", sensitive_file)

            sanitized_buffer = io.BytesIO()
            with zipfile.ZipFile(sanitized_buffer, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
                for file_path in extract_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(extract_dir)
                        out_zip.write(file_path, arcname=str(arcname))
            sanitized_buffer.seek(0)
            return sanitized_buffer
    except zipfile.BadZipFile:
        return None


@downloads_bp.route("/plan/download/report")
@login_required
def plan_download_report():
    plan_id = request.args.get("id", "")
    plan = db.session.get(PlanItem, plan_id)
    if plan is None:
        return jsonify({"error": "Plan not found"}), 400
    if not current_user.is_admin and str(plan.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403
    if not plan.generated_report_html:
        return jsonify({"error": "Report not available"}), 404
    buffer = io.BytesIO(plan.generated_report_html.encode("utf-8"))
    buffer.seek(0)
    download_name = f"{plan.id}-report.html"
    return send_file(buffer, mimetype="text/html", as_attachment=True, download_name=download_name)


@downloads_bp.route("/plan/download/zip")
@login_required
def plan_download_zip():
    plan_id = request.args.get("id", "")
    plan = db.session.get(PlanItem, plan_id)
    if plan is None:
        return jsonify({"error": "Plan not found"}), 400
    if not current_user.is_admin and str(plan.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403
    if not plan.run_zip_snapshot:
        return jsonify({"error": "Run zip not available"}), 404

    layout_version = safe_int(getattr(plan, "run_artifact_layout_version", None)) or 0
    if layout_version >= 2:
        buffer = io.BytesIO(plan.run_zip_snapshot)
        buffer.seek(0)
    else:
        buffer = _sanitize_legacy_run_zip_for_download(plan.run_zip_snapshot)
        if buffer is None:
            logger.error("Invalid legacy run zip snapshot for plan_id=%s", plan_id)
            return jsonify({"error": "Run zip is invalid"}), 500

    download_name = f"{plan.id}.zip"
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=download_name)


@downloads_bp.route("/admin/task/<uuid:task_id>/report")
@_admin_required
def download_task_report(task_id):
    task = db.session.get(PlanItem, task_id)
    if task is None or not task.generated_report_html:
        return "Report not found", 404
    buffer = io.BytesIO(task.generated_report_html.encode("utf-8"))
    buffer.seek(0)
    return send_file(buffer, mimetype="text/html", as_attachment=True, download_name="report.html")


@downloads_bp.route("/admin/task/<uuid:task_id>/run_zip")
@_admin_required
def download_task_run_zip(task_id):
    task = db.session.get(PlanItem, task_id)
    if task is None or not task.run_zip_snapshot:
        return "Run zip not found", 404
    buffer = io.BytesIO(task.run_zip_snapshot)
    buffer.seek(0)
    download_name = f"{task_id}.zip"
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=download_name)


@downloads_bp.route("/admin/task/<uuid:task_id>/track_activity")
@_admin_required
def download_task_track_activity(task_id):
    task = db.session.get(PlanItem, task_id)
    if task is None or not task.run_track_activity_jsonl:
        return "Track activity not found", 404
    buffer = io.BytesIO(task.run_track_activity_jsonl.encode("utf-8"))
    buffer.seek(0)
    download_name = f"{task_id}-track_activity.jsonl"
    return send_file(buffer, mimetype="application/x-ndjson", as_attachment=True, download_name=download_name)
