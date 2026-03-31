"""Plan routes blueprint — plan execution, viewing, control, and telemetry."""
import io
import json
import logging
import os
import uuid
import zipfile
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Optional

from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import DataError

from database_api.model_credit_history import CreditHistory
from database_api.model_event import EventItem, EventType
from database_api.model_nonce import NonceItem
from database_api.model_planitem import PlanItem, PlanState
from database_api.model_token_metrics import TokenMetrics, TokenMetricsSummary
from database_api.model_user_account import UserAccount
from database_api.model_user_api_key import UserApiKey
from database_api.planexe_db_singleton import db
from worker_plan_api.filenames import FilenameEnum, ExtraFilenameEnum
from worker_plan_api.model_profile import normalize_model_profile
from worker_plan_api.pipeline_version import PIPELINE_VERSION

from src.utils import (
    CREDIT_SCALE,
    clean_text,
    coerce_json_dict,
    extract_exception_type,
    extract_nested_value,
    extract_provider_model_from_activity_key,
    format_credit_display,
    format_relative_time,
    normalize_plan_view_mode,
    safe_float,
    safe_int,
    to_credit_decimal,
)

logger = logging.getLogger(__name__)

plan_routes_bp = Blueprint("plan_routes", __name__)

SHOW_DEMO_PLAN = False


def _new_model(model_cls: Any, **kwargs: Any) -> Any:
    from typing import cast
    return cast(Any, model_cls)(**kwargs)


def _nocache(view):
    from functools import wraps
    @wraps(view)
    def no_cache_view(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "-1"
        return response
    return no_cache_view


def _admin_user_ids() -> list[str]:
    admin_username = current_app.config["ADMIN_USERNAME"]
    ids = [admin_username]
    admin_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"planexe-admin-pref:{admin_username}"))
    if admin_uuid not in ids:
        ids.append(admin_uuid)
    return ids


def _get_current_user_account() -> Optional[UserAccount]:
    if not current_user.is_authenticated:
        return None
    admin_username = current_app.config["ADMIN_USERNAME"]
    try:
        user_uuid = uuid.UUID(str(current_user.id))
    except ValueError:
        if current_user.is_admin and str(current_user.id) == admin_username:
            admin_pref_id = uuid.uuid5(uuid.NAMESPACE_URL, f"planexe-admin-pref:{admin_username}")
            user = db.session.get(UserAccount, admin_pref_id)
            if user is None:
                try:
                    user = _new_model(UserAccount, id=admin_pref_id, is_admin=True, name="Admin")
                    db.session.add(user)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    logger.exception("Failed to create admin UserAccount %s", admin_pref_id)
                    user = db.session.get(UserAccount, admin_pref_id)
            return user
        logger.warning(
            "_get_current_user_account: admin mismatch current_user.id=%r admin_username=%r is_admin=%s",
            str(current_user.id), admin_username, current_user.is_admin,
        )
        return None
    return db.session.get(UserAccount, user_uuid)


def _load_prompt_preview_safe(task_id: Any, max_chars: int = 240) -> str:
    try:
        preview = (
            db.session.query(func.substr(PlanItem.prompt, 1, max_chars))
            .filter(PlanItem.id == task_id)
            .scalar()
        )
        text = (preview or "").strip()
        if text:
            return text
    except DataError:
        db.session.rollback()
        logger.warning(
            "Detected invalid UTF-8 in task_item.prompt for task_id=%s; using placeholder preview.",
            task_id,
            exc_info=True,
        )
        return "[Prompt unavailable due to encoding issue]"
    except Exception:
        db.session.rollback()
        logger.debug("Unable to load prompt preview for task_id=%s", task_id, exc_info=True)
    return "[Prompt unavailable]"


def _find_latest_task_event(task_id: str, event_type: EventType, max_events_to_scan: int = 2000) -> Optional[EventItem]:
    events = (
        EventItem.query
        .filter_by(event_type=event_type)
        .order_by(EventItem.timestamp.desc(), EventItem.id.desc())
        .limit(max_events_to_scan)
        .all()
    )
    for event in events:
        context = event.context if isinstance(event.context, dict) else {}
        if str(context.get("task_id") or "").strip() == task_id:
            return event
    return None


def _read_activity_overview_from_run_zip(run_zip_snapshot: Optional[bytes]) -> Optional[dict[str, Any]]:
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


def _read_activity_overview_from_task(task: PlanItem) -> Optional[dict[str, Any]]:
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
    return _read_activity_overview_from_run_zip(task.run_zip_snapshot)


def _read_inference_cost_from_task(task: PlanItem) -> Optional[float]:
    payload = _read_activity_overview_from_task(task)
    if not isinstance(payload, dict):
        return None
    return safe_float(payload.get("total_cost"))


def _build_plan_failure_trace(task: PlanItem) -> dict[str, Any]:
    task_id = str(task.id)
    token_metrics_rows = (
        TokenMetrics.query
        .filter_by(task_id=task_id)
        .order_by(TokenMetrics.timestamp.asc(), TokenMetrics.id.asc())
        .all()
    )
    failed_rows = [row for row in token_metrics_rows if (row.success is False) or bool(row.error_message)]
    latest_failed_row = failed_rows[-1] if failed_rows else None

    latest_failed_event = _find_latest_task_event(task_id, EventType.TASK_FAILED)
    latest_processing_event = _find_latest_task_event(task_id, EventType.TASK_PROCESSING)
    latest_completed_event = _find_latest_task_event(task_id, EventType.TASK_COMPLETED)
    latest_terminal_event = latest_failed_event or latest_completed_event

    failed_event_context = latest_failed_event.context if latest_failed_event and isinstance(latest_failed_event.context, dict) else {}
    processing_event_context = latest_processing_event.context if latest_processing_event and isinstance(latest_processing_event.context, dict) else {}
    terminal_event_context = latest_terminal_event.context if latest_terminal_event and isinstance(latest_terminal_event.context, dict) else {}
    latest_failed_usage = latest_failed_row.raw_usage_data if latest_failed_row and isinstance(latest_failed_row.raw_usage_data, dict) else {}
    task_parameters = task.parameters if isinstance(task.parameters, dict) else {}
    activity_overview = _read_activity_overview_from_task(task)

    nested_sources: list[Any] = [
        failed_event_context, processing_event_context, terminal_event_context,
        latest_failed_usage, task_parameters, activity_overview,
    ]

    stage = None
    for source in nested_sources:
        stage = clean_text(extract_nested_value(source, {"stage", "failed_stage", "failure_stage", "error_stage", "pipeline_stage"}))
        if stage:
            break

    explicit_error_type = None
    for source in nested_sources:
        explicit_error_type = clean_text(extract_nested_value(source, {"error_type", "exception_type", "exception_class"}))
        if explicit_error_type:
            break

    error_message = clean_text(latest_failed_row.error_message if latest_failed_row else None)
    if error_message is None:
        for source in nested_sources:
            error_message = clean_text(extract_nested_value(source, {"error_message", "message", "machai_error_message", "exception", "error", "detail"}))
            if error_message:
                break

    error_type = explicit_error_type or extract_exception_type(error_message)

    retry_count = None
    for source in nested_sources:
        retry_count = safe_int(extract_nested_value(source, {"retry_count", "retries", "retry_attempts", "attempt_count", "attempts"}))
        if retry_count is not None:
            break

    fallback_indicator = None
    for source in nested_sources:
        fallback_value = extract_nested_value(source, {"fallback", "fallback_used", "used_fallback", "fallback_model", "fallback_provider"})
        fallback_text = clean_text(fallback_value)
        if fallback_text is not None:
            fallback_indicator = fallback_text
            break
        if isinstance(fallback_value, bool):
            fallback_indicator = "true" if fallback_value else "false"
            break

    routes_map: dict[tuple[Optional[str], Optional[str]], int] = {}
    for row in token_metrics_rows:
        provider = clean_text(row.upstream_provider)
        model = clean_text(row.upstream_model) or clean_text(row.llm_model)
        if provider is None and model is None:
            continue
        key = (provider, model)
        routes_map[key] = routes_map.get(key, 0) + 1
    if not routes_map and isinstance(activity_overview, dict):
        models_payload = activity_overview.get("models")
        if isinstance(models_payload, dict):
            for model_key, model_stats in models_payload.items():
                provider, model = extract_provider_model_from_activity_key(model_key)
                if provider is None and model is None:
                    continue
                calls = safe_int(model_stats.get("calls")) if isinstance(model_stats, dict) else None
                routes_map[(provider, model)] = calls if calls and calls > 0 else 0

    routes = [
        {"provider": provider, "model": model, "calls": calls if calls > 0 else None}
        for (provider, model), calls in routes_map.items()
    ]
    routes.sort(key=lambda row: (-(row["calls"] or 0), row["provider"] or "", row["model"] or ""))

    provider_switch_indicator = None
    for source in nested_sources:
        provider_switch_indicator = clean_text(extract_nested_value(source, {"provider_switch", "provider_switched", "switched_provider", "provider_switch_count"}))
        if provider_switch_indicator:
            break

    unique_routes_count = len(routes)
    inferred_provider_switch_count = unique_routes_count - 1 if unique_routes_count > 1 else 0

    pending_to_processing_seconds = safe_float(processing_event_context.get("duration_between_pending_and_processing"))
    processing_to_terminal_seconds = safe_float(terminal_event_context.get("duration_between_processing_and_completion"))

    llm_duration_values = [safe_float(row.duration_seconds) for row in token_metrics_rows if row.duration_seconds is not None]
    llm_duration_values = [v for v in llm_duration_values if v is not None]
    llm_duration_total_seconds = sum(llm_duration_values) if llm_duration_values else None

    partial_output = None
    for source in [latest_failed_usage, failed_event_context, task_parameters]:
        partial_output = extract_nested_value(source, {"partial_output", "partial_response", "partial_result", "response_excerpt", "partial_text", "raw_partial_output"})
        if partial_output not in (None, "", [], {}):
            break

    if isinstance(partial_output, (dict, list)):
        try:
            partial_output = json.dumps(partial_output, indent=2, sort_keys=True)
        except Exception:
            partial_output = str(partial_output)
    else:
        partial_output = clean_text(partial_output)

    api_key_ids_in_trace = {row.api_key_id for row in token_metrics_rows if row.api_key_id}
    key_name_lookup: dict[str, str] = {}
    if api_key_ids_in_trace:
        for key_row in UserApiKey.query.filter(UserApiKey.id.in_(list(api_key_ids_in_trace))).all():
            key_name_lookup[str(key_row.id)] = key_row.name or f"{key_row.key_prefix}..."
    owner_display_name: Optional[str] = None
    try:
        owner_uuid = uuid.UUID(str(task.user_id))
        owner = db.session.get(UserAccount, owner_uuid)
        if owner:
            owner_display_name = owner.name or owner.given_name or owner.email or "Account"
            if getattr(owner, "is_admin", False):
                owner_display_name = "Admin"
    except (ValueError, AttributeError):
        owner_display_name = str(task.user_id) if task.user_id else None

    execution_attempts = []
    for row in token_metrics_rows:
        route_provider = clean_text(row.upstream_provider)
        route_model = clean_text(row.upstream_model) or clean_text(row.llm_model)
        success_state = True if row.success is True else False if row.success is False else None
        invoked_by = key_name_lookup.get(row.api_key_id) if row.api_key_id else owner_display_name
        execution_attempts.append({
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "provider": route_provider,
            "model": route_model,
            "duration_seconds": safe_float(row.duration_seconds),
            "success": success_state,
            "error_message": clean_text(row.error_message),
            "invoked_by": invoked_by,
        })

    inferred_retry_count = len(token_metrics_rows) - 1 if token_metrics_rows else None

    failure_trace: dict[str, Any] = {
        "task_id": task_id,
        "failure_reason": task.failure_reason,
        "failed_step": task.failed_step,
        "error_message": task.error_message,
        "recoverable": task.recoverable,
        "stage": stage,
        "error": {"type": error_type, "message": error_message},
        "retries": {
            "count": retry_count,
            "count_inferred_from_attempts": inferred_retry_count,
            "attempt_count": len(token_metrics_rows) if token_metrics_rows else None,
            "failed_attempts": len(failed_rows) if token_metrics_rows else None,
        },
        "fallback": {"indicator": fallback_indicator},
        "provider_switch": {
            "indicator": provider_switch_indicator,
            "inferred_count_from_routes": inferred_provider_switch_count if routes else None,
            "routes": routes,
        },
        "timing": {
            "pending_to_processing_seconds": pending_to_processing_seconds,
            "processing_to_terminal_seconds": processing_to_terminal_seconds,
            "llm_attempts_total_duration_seconds": llm_duration_total_seconds,
        },
        "partial_output": partial_output,
        "execution_trace": execution_attempts,
        "source_paths": {
            "events_table": "events.context.{task_id, duration_between_pending_and_processing, duration_between_processing_and_completion, machai_error_message}",
            "token_metrics_table": "token_metrics.{timestamp, upstream_provider, upstream_model, llm_model, duration_seconds, success, error_message, raw_usage_data}",
            "task_parameters": "taskitem.parameters",
            "activity_overview_json": "PlanItem.run_activity_overview_json (fallback: PlanItem.run_zip_snapshot -> */activity_overview.json)",
        },
    }
    failure_trace["has_data"] = any([
        failure_trace["failure_reason"] is not None,
        failure_trace["failed_step"] is not None,
        failure_trace["error_message"] is not None,
        failure_trace["recoverable"] is not None,
        failure_trace["stage"] is not None,
        failure_trace["error"]["type"] is not None,
        failure_trace["error"]["message"] is not None,
        failure_trace["retries"]["count"] is not None,
        failure_trace["retries"]["count_inferred_from_attempts"] is not None,
        failure_trace["fallback"]["indicator"] is not None,
        failure_trace["provider_switch"]["indicator"] is not None,
        failure_trace["provider_switch"]["inferred_count_from_routes"] is not None,
        failure_trace["timing"]["pending_to_processing_seconds"] is not None,
        failure_trace["timing"]["processing_to_terminal_seconds"] is not None,
        failure_trace["timing"]["llm_attempts_total_duration_seconds"] is not None,
        bool(failure_trace["execution_trace"]),
        failure_trace["partial_output"] is not None,
    ])
    return failure_trace


def _build_plan_telemetry_cache_key(task: PlanItem, include_raw: bool) -> Optional[tuple[str, str, bool, bool]]:
    state = task.state if isinstance(task.state, PlanState) else None
    if include_raw or state not in (PlanState.completed, PlanState.failed):
        return None
    return (str(task.id), state.name, bool(task.has_run_zip_snapshot), bool(getattr(task, "run_activity_overview_json", None)))


def _build_plan_telemetry(task: PlanItem, include_raw: bool = False, expose_raw_usage_data: bool = False) -> dict[str, Any]:
    cache_key = _build_plan_telemetry_cache_key(task, include_raw)
    telemetry_cache = current_app.config.get("PLAN_TELEMETRY_CACHE")
    if cache_key is not None and isinstance(telemetry_cache, dict):
        cached = telemetry_cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    task_id = str(task.id)
    token_metrics_rows = (
        TokenMetrics.query.filter_by(task_id=task_id)
        .order_by(TokenMetrics.timestamp.asc(), TokenMetrics.id.asc())
        .all()
    )
    token_summary = TokenMetricsSummary(task_id=task_id, metrics=token_metrics_rows)
    activity_overview = _read_activity_overview_from_task(task)

    has_prompt_tokens = any(row.input_tokens is not None for row in token_metrics_rows)
    has_completion_tokens = any(row.output_tokens is not None for row in token_metrics_rows)
    has_thinking_tokens = any(row.thinking_tokens is not None for row in token_metrics_rows)
    has_any_metric_tokens = has_prompt_tokens or has_completion_tokens or has_thinking_tokens

    activity_prompt_tokens = safe_int(activity_overview.get("total_input_tokens")) if isinstance(activity_overview, dict) else None
    activity_completion_tokens = safe_int(activity_overview.get("total_output_tokens")) if isinstance(activity_overview, dict) else None
    activity_thinking_tokens = safe_int(activity_overview.get("total_thinking_tokens")) if isinstance(activity_overview, dict) else None
    activity_total_tokens = safe_int(activity_overview.get("total_tokens")) if isinstance(activity_overview, dict) else None

    prompt_tokens = token_summary.total_input_tokens if has_prompt_tokens else activity_prompt_tokens
    completion_tokens = token_summary.total_output_tokens if has_completion_tokens else activity_completion_tokens
    thinking_tokens = token_summary.total_thinking_tokens if has_thinking_tokens else activity_thinking_tokens

    if has_any_metric_tokens:
        total_tokens = token_summary.total_tokens
    elif activity_total_tokens is not None:
        total_tokens = activity_total_tokens
    elif any(v is not None for v in [prompt_tokens, completion_tokens, thinking_tokens]):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0) + (thinking_tokens or 0)
    else:
        total_tokens = None

    metric_cost_values = [safe_float(row.cost_usd) for row in token_metrics_rows if row.cost_usd is not None]
    metric_cost_values = [v for v in metric_cost_values if v is not None]
    token_metrics_cost_usd = sum(metric_cost_values) if metric_cost_values else None
    activity_overview_cost_usd = safe_float(activity_overview.get("total_cost")) if isinstance(activity_overview, dict) else None

    provider_model_counts: dict[tuple[Optional[str], Optional[str]], int] = {}
    if token_metrics_rows:
        for row in token_metrics_rows:
            provider = clean_text(row.upstream_provider)
            model = clean_text(row.upstream_model) or clean_text(row.llm_model)
            if provider is None and model is None:
                continue
            key = (provider, model)
            provider_model_counts[key] = provider_model_counts.get(key, 0) + 1
    elif isinstance(activity_overview, dict):
        models_payload = activity_overview.get("models")
        if isinstance(models_payload, dict):
            for model_key, model_stats in models_payload.items():
                provider, model = extract_provider_model_from_activity_key(model_key)
                if provider is None and model is None:
                    continue
                calls = safe_int(model_stats.get("calls")) if isinstance(model_stats, dict) else None
                provider_model_counts[(provider, model)] = calls if calls and calls > 0 else 0

    routes = [
        {"provider": provider, "model": model, "calls": calls if calls > 0 else None}
        for (provider, model), calls in provider_model_counts.items()
    ]
    routes.sort(key=lambda row: (-(row["calls"] or 0), row["provider"] or "", row["model"] or ""))

    providers = sorted({row["provider"] for row in routes if row.get("provider")})
    models = sorted({row["model"] for row in routes if row.get("model")})

    if token_metrics_rows:
        total_calls = token_summary.total_calls
        successful_calls = token_summary.successful_calls
        failed_calls = token_summary.failed_calls
    else:
        total_calls = None
        successful_calls = None
        failed_calls = None
        if isinstance(activity_overview, dict):
            models_payload = activity_overview.get("models")
            if isinstance(models_payload, dict):
                total_calls = 0
                for model_stats in models_payload.values():
                    calls = safe_int(model_stats.get("calls")) if isinstance(model_stats, dict) else None
                    total_calls += calls or 0

    telemetry: dict[str, Any] = {
        "task_id": task_id,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "thinking_tokens": thinking_tokens,
            "total_tokens": total_tokens,
        },
        "cost": {
            "token_metrics_usd": token_metrics_cost_usd,
            "activity_overview_usd": activity_overview_cost_usd,
            "currency": "USD" if token_metrics_cost_usd is not None or activity_overview_cost_usd is not None else None,
        },
        "provider_model": {
            "providers": providers,
            "models": models,
            "routes": routes,
        },
        "calls": {
            "total": total_calls,
            "successful": successful_calls,
            "failed": failed_calls,
        },
        "source_paths": {
            "token_metrics_table": "token_metrics.{input_tokens, output_tokens, thinking_tokens, cost_usd, upstream_provider, upstream_model}",
            "activity_overview_json": "PlanItem.run_activity_overview_json (fallback: PlanItem.run_zip_snapshot -> */activity_overview.json)",
        },
        "source_availability": {
            "token_metrics_row_count": len(token_metrics_rows),
            "activity_overview_present": isinstance(activity_overview, dict),
        },
    }
    telemetry["has_data"] = any([
        telemetry["usage"]["prompt_tokens"] is not None,
        telemetry["usage"]["completion_tokens"] is not None,
        telemetry["usage"]["thinking_tokens"] is not None,
        telemetry["usage"]["total_tokens"] is not None,
        telemetry["cost"]["token_metrics_usd"] is not None,
        telemetry["cost"]["activity_overview_usd"] is not None,
        bool(telemetry["provider_model"]["routes"]),
        telemetry["calls"]["total"] is not None,
    ])

    if include_raw:
        raw_token_metrics_rows = []
        for row in token_metrics_rows:
            raw_token_metrics_rows.append({
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "task_id": row.task_id,
                "user_id": row.user_id,
                "llm_model": row.llm_model,
                "upstream_provider": row.upstream_provider,
                "upstream_model": row.upstream_model,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "thinking_tokens": row.thinking_tokens,
                "cost_usd": row.cost_usd,
                "duration_seconds": row.duration_seconds,
                "success": row.success,
                "error_message": row.error_message,
                "raw_usage_data": row.raw_usage_data if expose_raw_usage_data else None,
            })
        telemetry["source_data"] = {
            "activity_overview": activity_overview,
            "token_metrics": raw_token_metrics_rows,
        }

    if cache_key is not None and isinstance(telemetry_cache, dict):
        telemetry_cache[cache_key] = telemetry
        if len(telemetry_cache) > 512:
            telemetry_cache.pop(next(iter(telemetry_cache)))

    return telemetry


def _get_plan_view_mode_preference() -> str:
    user = _get_current_user_account()
    if user is None:
        return "view"
    config = coerce_json_dict(user.frontend_multi_user_config)
    plan_page = coerce_json_dict(config.get("plan_page"))
    return normalize_plan_view_mode(plan_page.get("selected_segment"))


def _set_plan_view_mode_preference(mode: str) -> None:
    user = _get_current_user_account()
    if user is None:
        return
    normalized_mode = normalize_plan_view_mode(mode)
    existing_config = coerce_json_dict(user.frontend_multi_user_config)
    config = dict(existing_config)
    existing_plan_page = coerce_json_dict(config.get("plan_page"))
    plan_page = dict(existing_plan_page)
    plan_page["selected_segment"] = normalized_mode
    config["plan_page"] = plan_page
    user.frontend_multi_user_config = config
    db.session.commit()


@plan_routes_bp.route("/run", methods=["GET", "POST"])
@login_required
@_nocache
def run():
    if request.method == "POST" and request.args:
        logger.error("endpoint /run. POST request with urlencoded parameters detected.")
        return jsonify({"error": "POST request with urlencoded parameters detected. This is not allowed."}), 400

    request_size_bytes: int = len(request.get_data())
    request_content_type: str = request.headers.get("Content-Type", "")

    request_form_or_args = request.form if request.method == "POST" else request.args
    prompt_param = request_form_or_args.get("prompt", "")
    user_id_param = request_form_or_args.get("user_id", "")
    nonce_param = request_form_or_args.get("nonce", "")
    parameters: dict[str, Any] | None = {key: value for key, value in request_form_or_args.items()}

    parameters.pop("prompt", None)
    parameters.pop("user_id", None)
    parameters.pop("nonce", None)
    if len(parameters) == 0:
        parameters = None

    if not isinstance(parameters, dict):
        parameters = {}
    raw_profile = parameters.get("model_profile")
    parameters["model_profile"] = normalize_model_profile(raw_profile).value
    parameters["pipeline_version"] = PIPELINE_VERSION

    prompt_param_bytes = len(prompt_param.encode("utf-8"))
    prompt_param_characters = len(prompt_param)

    log_prompt_info = prompt_param[:100]
    if len(prompt_param) > 100:
        log_prompt_info += "... (truncated)"
    logger.info(
        "endpoint /run (%s). Size: %s bytes. prompt=%r, user_id=%r, nonce=%r, parameters=%r",
        request.method, request_size_bytes, log_prompt_info, user_id_param, nonce_param, parameters,
    )

    if current_user.is_admin:
        admin_account = _get_current_user_account()
        user_id_param = str(admin_account.id) if admin_account else current_app.config["ADMIN_USERNAME"]
    else:
        user_id_param = str(current_user.id)

    if not nonce_param:
        logger.error("endpoint /run. No nonce provided")
        return jsonify({"error": "A unique request identifier (nonce) is required."}), 400

    context = {
        "user_agent": request.headers.get("User-Agent"),
        "ip_address": request.remote_addr,
        "prompt": prompt_param,
        "user_id": user_id_param,
    }
    nonce_item, is_new = NonceItem.get_or_create(nonce_key=nonce_param, context=context)
    if not is_new:
        logger.warning("endpoint /run. Replay detected for nonce '%s'. Request count: %s.", nonce_param, nonce_item.request_count)
        return jsonify({"error": "This action has already been performed. Reusing this link is not permitted."}), 409

    if not prompt_param:
        logger.error("endpoint /run. No prompt provided")
        return jsonify({"error": "No prompt provided"}), 400

    if not current_user.is_admin:
        user = db.session.get(UserAccount, uuid.UUID(str(current_user.id)))
        if not user:
            return jsonify({"error": "User not found"}), 400
        if not user.free_plan_used:
            user.free_plan_used = True
            db.session.commit()
            if not isinstance(parameters, dict):
                parameters = {}
            parameters["billing_skip_usage_charge"] = True
        else:
            if (user.credits_balance or 0) <= 0:
                return jsonify({"error": "No credits available"}), 402

    task = _new_model(
        PlanItem,
        state=PlanState.pending,
        prompt=prompt_param,
        progress_percentage=0.0,
        progress_message="Awaiting server to start\u2026",
        user_id=user_id_param,
        parameters=parameters,
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.id if hasattr(task, "id") else None
    logger.info("endpoint /run. Task received: %r", task_id)
    event_context = {
        "task_id": str(task_id),
        "request_size_bytes": request_size_bytes,
        "request_content_type": request_content_type,
        "prompt_param_bytes": prompt_param_bytes,
        "prompt_param_characters": prompt_param_characters,
        "prompt": prompt_param,
        "user_id": user_id_param,
        "parameters": parameters,
        "method": request.method,
    }
    event = _new_model(EventItem, event_type=EventType.TASK_PENDING, message="Enqueued task via /run endpoint", context=event_context)
    db.session.add(event)
    db.session.commit()
    return render_template("run_via_database.html", run_id=task_id)


@plan_routes_bp.route("/create_plan", methods=["POST"])
@login_required
@_nocache
def create_plan():
    if request.args:
        logger.error("endpoint /create_plan. POST request with urlencoded parameters detected.")
        return jsonify({"error": "POST request with urlencoded parameters detected. This is not allowed."}), 400

    request_size_bytes: int = len(request.get_data())
    request_content_type: str = request.headers.get("Content-Type", "")

    prompt_param = request.form.get("prompt", "")
    parameters: dict[str, Any] = {key: value for key, value in request.form.items()}
    parameters.pop("csrf_token", None)
    parameters.pop("prompt", None)
    parameters.pop("user_id", None)
    parameters.pop("nonce", None)
    parameters.pop("redirect_to_plan", None)

    if not parameters.get("start_date"):
        parameters.pop("start_date", None)

    raw_profile = parameters.get("model_profile")
    parameters["model_profile"] = normalize_model_profile(raw_profile).value

    prompt_param_bytes = len(prompt_param.encode("utf-8"))
    prompt_param_characters = len(prompt_param)
    log_prompt_info = prompt_param[:100]
    if len(prompt_param) > 100:
        log_prompt_info += "... (truncated)"

    if not prompt_param:
        logger.error("endpoint /create_plan. No prompt provided")
        return jsonify({"error": "No prompt provided"}), 400

    api_key_id_param: Optional[str] = None
    if current_user.is_admin:
        admin_account = _get_current_user_account()
        user_id_param = str(admin_account.id) if admin_account else current_app.config["ADMIN_USERNAME"]
    else:
        user_id_param = str(current_user.id)

    logger.info(
        "endpoint /create_plan (%s). Size: %s bytes. prompt=%r, user_id=%r, parameters=%r",
        request.method, request_size_bytes, log_prompt_info, user_id_param, parameters,
    )

    if current_user.is_admin:
        first_key = (
            UserApiKey.query
            .filter_by(user_id=uuid.UUID(user_id_param), revoked_at=None)
            .order_by(UserApiKey.created_at.asc())
            .first()
        )
        if first_key:
            api_key_id_param = str(first_key.id)
    else:
        user = db.session.get(UserAccount, uuid.UUID(str(current_user.id)))
        if not user:
            return jsonify({"error": "User not found"}), 400
        if to_credit_decimal(user.credits_balance) < Decimal("2"):
            return jsonify({"error": "Insufficient credits (minimum 2 required)"}), 402
        first_key = (
            UserApiKey.query
            .filter_by(user_id=user.id, revoked_at=None)
            .order_by(UserApiKey.created_at.asc())
            .first()
        )
        if first_key:
            api_key_id_param = str(first_key.id)

    task = _new_model(
        PlanItem,
        state=PlanState.pending,
        prompt=prompt_param,
        progress_percentage=0.0,
        progress_message="Awaiting server to start\u2026",
        user_id=user_id_param,
        api_key_id=api_key_id_param,
        parameters=parameters,
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.id if hasattr(task, "id") else None
    logger.info("endpoint /create_plan. Task received: %r", task_id)

    event_context = {
        "task_id": str(task_id),
        "request_size_bytes": request_size_bytes,
        "request_content_type": request_content_type,
        "prompt_param_bytes": prompt_param_bytes,
        "prompt_param_characters": prompt_param_characters,
        "prompt": prompt_param,
        "user_id": user_id_param,
        "parameters": parameters,
        "method": request.method,
    }
    event = _new_model(EventItem, event_type=EventType.TASK_PENDING, message="Enqueued task via /create_plan endpoint", context=event_context)
    db.session.add(event)
    db.session.commit()

    if task_id is None:
        return jsonify({"error": "Unable to create task"}), 500
    return redirect(url_for("plan_routes.plan", id=task_id))


@plan_routes_bp.route("/run_status")
@login_required
@_nocache
def run_status():
    run_id = request.args.get("id", "")
    task = db.session.get(PlanItem, run_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403
    return render_template("run_via_database.html", run_id=run_id)


@plan_routes_bp.route("/progress")
def get_progress():
    run_id = request.args.get("run_id", "")
    logger.debug("Progress endpoint received run_id: %r", run_id)
    task = db.session.get(PlanItem, run_id)
    if task is None:
        logger.error("Task not found for run_id: %r", run_id)
        return jsonify({"error": "Task not found"}), 400

    progress_percentage = float(task.progress_percentage) if task.progress_percentage is not None else 0.0
    progress_message = task.progress_message if task.progress_message is not None else ""
    if isinstance(task.state, PlanState):
        status = task.state.name
    else:
        status = f"unknown-{task.state}"

    try:
        task.last_seen_timestamp = datetime.now(UTC)
        db.session.commit()
    except Exception as e:
        logger.error("get_progress, error updating last_seen_timestamp for task %r: %s", run_id, e, exc_info=True)
        db.session.rollback()

    return jsonify({"progress_percentage": progress_percentage, "progress_message": progress_message, "status": status}), 200


@plan_routes_bp.route("/viewplan")
@login_required
def viewplan():
    run_id = request.args.get("run_id", "")
    logger.info("ViewPlan endpoint requested for run_id: %r", run_id)
    task = db.session.get(PlanItem, run_id)
    if task is None:
        logger.error("Task not found for run_id: %r", run_id)
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        logger.warning("Unauthorized report access attempt. run_id=%s user_id=%s", run_id, current_user.id)
        return jsonify({"error": "Forbidden"}), 403

    if SHOW_DEMO_PLAN:
        planexe_run_dir = current_app.config["PLANEXE_RUN_DIR"]
        run_id_val = "20250524_universal_manufacturing"
        run_id_dir = (planexe_run_dir / run_id_val).absolute()
        path_to_html_file = run_id_dir / FilenameEnum.REPORT.value
        if not path_to_html_file.exists():
            return jsonify({"error": "Demo report not found"}), 404
        return send_file(str(path_to_html_file), mimetype="text/html")

    if not task.generated_report_html:
        logger.error("Report HTML not found for run_id=%s", run_id)
        return jsonify({"error": "Report not available"}), 404

    response = make_response(task.generated_report_html)
    response.headers["Content-Type"] = "text/html"
    return response


@plan_routes_bp.route("/plan")
@login_required
def plan():
    from types import SimpleNamespace
    run_id = request.args.get("id", "").strip()

    if not run_id:
        user_id = str(current_user.id)
        uid_filter = (
            PlanItem.user_id.in_(_admin_user_ids())
            if current_user.is_admin
            else PlanItem.user_id == user_id
        )
        try:
            tasks = (
                db.session.query(
                    PlanItem.id, PlanItem.timestamp_created, PlanItem.state, PlanItem.stop_requested,
                    func.substr(PlanItem.prompt, 1, 240).label("prompt_preview"),
                )
                .filter(uid_filter)
                .order_by(PlanItem.timestamp_created.desc())
                .all()
            )
        except DataError:
            db.session.rollback()
            logger.warning("Detected invalid UTF-8 in task_item.prompt for user_id=%s; falling back.", user_id, exc_info=True)
            tasks = (
                db.session.query(PlanItem.id, PlanItem.timestamp_created, PlanItem.state, PlanItem.stop_requested)
                .filter(uid_filter)
                .order_by(PlanItem.timestamp_created.desc())
                .all()
            )
        rows = []
        for task in tasks:
            ts = task.timestamp_created
            created_compact = ts.strftime("%y%m%d-%H%M") if isinstance(ts, datetime) else "-"
            prompt_preview = getattr(task, "prompt_preview", None)
            if prompt_preview is None:
                prompt_text = _load_prompt_preview_safe(task.id)
            else:
                prompt_text = (prompt_preview or "").strip() or "[Prompt unavailable]"
            state_name = task.state.name if isinstance(task.state, PlanState) else "pending"
            rows.append({
                "id": str(task.id),
                "created_compact": created_compact,
                "created_relative": format_relative_time(ts),
                "status": state_name,
                "prompt": prompt_text,
            })
        return render_template("plan_list.html", plan_rows=rows)

    logger.info("Plan iframe wrapper requested for run_id: %r", run_id)
    task = db.session.get(PlanItem, run_id)
    if task is None:
        logger.error("Task not found for run_id: %r", run_id)
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        logger.warning("Unauthorized plan wrapper access attempt. run_id=%s user_id=%s", run_id, current_user.id)
        return jsonify({"error": "Forbidden"}), 403

    telemetry = _build_plan_telemetry(task, include_raw=False)
    failure_trace = _build_plan_failure_trace(task)
    preferred_plan_view_mode = _get_plan_view_mode_preference()
    parameters = task.parameters if isinstance(task.parameters, dict) else {}
    selected_model_profile = normalize_model_profile(parameters.get("model_profile")).value
    resume_error = request.args.get("resume_error", "")
    return render_template(
        "plan_iframe.html",
        run_id=run_id,
        task=task,
        telemetry=telemetry,
        failure_trace=failure_trace,
        preferred_plan_view_mode=preferred_plan_view_mode,
        selected_model_profile=selected_model_profile,
        resume_error=resume_error,
    )


@plan_routes_bp.route("/plan/stop", methods=["POST"])
@login_required
def plan_stop():
    run_id = request.form.get("id", "").strip()
    task = db.session.get(PlanItem, run_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403
    if task.state == PlanState.completed or bool(task.has_generated_report_html):
        logger.info("Ignoring stop request for already completed task %s", run_id)
        return redirect(url_for("plan_routes.plan", id=run_id))
    task.stop_requested = True
    task.stop_requested_timestamp = datetime.now(UTC)
    if task.state in (PlanState.pending, PlanState.processing):
        task.state = PlanState.stopped
        task.progress_message = "Stop requested by user."
    db.session.commit()
    return redirect(url_for("plan_routes.plan", id=run_id))


@plan_routes_bp.route("/plan/retry", methods=["POST"])
@login_required
def plan_retry():
    run_id = request.form.get("id", "").strip()
    task = db.session.get(PlanItem, run_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403
    if task.state not in (PlanState.failed, PlanState.stopped) and not bool(task.stop_requested):
        return jsonify({"error": "Task is not in a retryable state. Stop it first before retrying."}), 409

    raw_profile = request.form.get("model_profile")
    selected_model_profile = normalize_model_profile(raw_profile).value
    parameters = dict(task.parameters) if isinstance(task.parameters, dict) else {}
    parameters["model_profile"] = selected_model_profile
    parameters["pipeline_version"] = PIPELINE_VERSION
    task.parameters = parameters

    task.state = PlanState.pending
    task.stop_requested = False
    task.stop_requested_timestamp = None
    task.progress_percentage = 0.0
    task.progress_message = "Retry requested by user."
    task.generated_report_html = None
    task.run_zip_snapshot = None
    task.run_track_activity_jsonl = None
    task.run_track_activity_bytes = None
    task.run_activity_overview_json = None
    task.run_artifact_layout_version = None
    task.failure_reason = None
    task.failed_step = None
    task.error_message = None
    task.recoverable = None
    task.last_seen_timestamp = datetime.now(UTC)

    CreditHistory.query.filter_by(
        source="usage_billing_progress",
        external_id=str(task.id),
    ).update({"source": "usage_billing_settled"})

    db.session.commit()
    return redirect(url_for("plan_routes.plan", id=run_id))


@plan_routes_bp.route("/plan/resume", methods=["POST"])
@login_required
def plan_resume():
    from flask import abort
    run_id = request.form.get("id", "").strip()
    task = db.session.get(PlanItem, run_id)
    if task is None:
        abort(404)
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        abort(403)
    if task.state not in (PlanState.failed, PlanState.stopped):
        return redirect(url_for("plan_routes.plan", id=run_id))

    stored_params = task.parameters if isinstance(task.parameters, dict) else {}
    stored_version = stored_params.get("pipeline_version")
    if stored_version is not None and stored_version != PIPELINE_VERSION:
        return redirect(url_for("plan_routes.plan", id=run_id, resume_error="version_mismatch"))

    raw_profile = request.form.get("model_profile")
    selected_model_profile = normalize_model_profile(raw_profile).value
    parameters = dict(task.parameters) if isinstance(task.parameters, dict) else {}
    parameters["model_profile"] = selected_model_profile
    parameters["trigger_source"] = "frontend resume"
    parameters["resume"] = True
    parameters["resume_count"] = parameters.get("resume_count", 0) + 1
    task.parameters = parameters

    task.state = PlanState.pending
    task.progress_message = "Resume requested by user."
    task.stop_requested = False
    task.stop_requested_timestamp = None
    task.failure_reason = None
    task.failed_step = None
    task.error_message = None
    task.recoverable = None
    task.last_seen_timestamp = datetime.now(UTC)

    CreditHistory.query.filter_by(
        source="usage_billing_progress",
        external_id=str(task.id),
    ).update({"source": "usage_billing_settled"})

    db.session.commit()

    event_context = {
        "plan_id": str(task.id),
        "task_handle": str(task.id),
        "resume_of_plan_id": str(task.id),
        "model_profile": selected_model_profile,
        "resume_count": parameters["resume_count"],
    }
    event = EventItem()
    event.event_type = EventType.TASK_PENDING
    event.message = "Resumed failed task via frontend"
    event.context = event_context
    db.session.add(event)
    db.session.commit()

    return redirect(url_for("plan_routes.plan", id=run_id))


@plan_routes_bp.route("/plan/meta")
@login_required
def plan_meta():
    run_id = request.args.get("id", "").strip()
    task = db.session.get(PlanItem, run_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403

    state_name = task.state.name if isinstance(task.state, PlanState) else "pending"
    telemetry = _build_plan_telemetry(task, include_raw=False)
    failure_trace = _build_plan_failure_trace(task)
    return jsonify({
        "id": str(task.id),
        "state": state_name,
        "progress_percentage": float(task.progress_percentage) if task.progress_percentage is not None else 0.0,
        "progress_message": task.progress_message or "",
        "generated_report_html": bool(task.has_generated_report_html),
        "run_zip_snapshot": bool(task.has_run_zip_snapshot),
        "stop_requested": bool(task.stop_requested),
        "telemetry": telemetry,
        "failure_trace": failure_trace,
    }), 200


@plan_routes_bp.route("/plan/view-mode", methods=["POST"])
@login_required
def plan_view_mode():
    payload = request.get_json(silent=True) if request.is_json else request.form
    mode = normalize_plan_view_mode((payload or {}).get("mode"))
    _set_plan_view_mode_preference(mode)
    return jsonify({"status": "ok", "mode": mode}), 200


@plan_routes_bp.route("/plan/telemetry")
@login_required
def plan_telemetry():
    run_id = request.args.get("id", "").strip()
    task = db.session.get(PlanItem, run_id)
    if task is None:
        return jsonify({"error": "Task not found"}), 400
    if not current_user.is_admin and str(task.user_id) != str(current_user.id):
        return jsonify({"error": "Forbidden"}), 403
    telemetry = _build_plan_telemetry(task, include_raw=True, expose_raw_usage_data=True)
    return jsonify(telemetry), 200
