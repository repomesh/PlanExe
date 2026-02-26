"""PlanExe MCP Cloud – database query helpers."""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from flask import has_app_context
from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB
from worker_plan_api.model_profile import normalize_model_profile

from mcp_cloud.db_setup import app, db, PlanItem, PlanState, EventItem, EventType

logger = logging.getLogger(__name__)

PROMPT_EXCERPT_MAX_LENGTH = 100


# ---------------------------------------------------------------------------
# Plan lookup
# ---------------------------------------------------------------------------

def find_plan_by_task_id(task_id: str) -> Optional[PlanItem]:
    """Find PlanItem by MCP task_id (UUID), with legacy fallback."""
    plan = get_plan_by_id(task_id)
    if plan is not None:
        return plan

    def _query_legacy() -> Optional[PlanItem]:
        query = db.session.query(PlanItem)
        if db.engine.dialect.name == "postgresql":
            plans = query.filter(
                cast(PlanItem.parameters, JSONB).contains({"_mcp_task_id": task_id})
            ).all()
        else:
            plans = query.filter(
                PlanItem.parameters.contains({"_mcp_task_id": task_id})
            ).all()
        if plans:
            return plans[0]
        return None

    if has_app_context():
        legacy_plan = _query_legacy()
    else:
        with app.app_context():
            legacy_plan = _query_legacy()
    if legacy_plan is not None:
        logger.debug("Resolved legacy MCP task id %s to plan %s", task_id, legacy_plan.id)
    return legacy_plan

def get_plan_by_id(task_id: str) -> Optional[PlanItem]:
    """Fetch a PlanItem by its UUID string."""
    def _query() -> Optional[PlanItem]:
        try:
            plan_uuid = uuid.UUID(task_id)
        except ValueError:
            return None
        return db.session.get(PlanItem, plan_uuid)

    if has_app_context():
        return _query()
    with app.app_context():
        return _query()

def resolve_plan_for_task_id(task_id: str) -> Optional[PlanItem]:
    """Resolve a PlanItem from a task_id (UUID), with legacy fallback."""
    return find_plan_by_task_id(task_id)


# ---------------------------------------------------------------------------
# Sync operations called from handlers via asyncio.to_thread
# ---------------------------------------------------------------------------

def _create_plan_sync(
    prompt: str,
    config: Optional[dict[str, Any]],
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    with app.app_context():
        parameters = dict(config or {})
        parameters["model_profile"] = normalize_model_profile(parameters.get("model_profile")).value
        parameters["trigger_source"] = "mcp plan_create"

        plan = PlanItem(
            prompt=prompt,
            state=PlanState.pending,
            user_id=metadata.get("user_id", "admin") if metadata else "admin",
            parameters=parameters,
        )
        db.session.add(plan)
        db.session.commit()

        plan_id = str(plan.id)
        event_context = {
            "task_id": plan_id,
            "task_handle": plan_id,
            "prompt": plan.prompt,
            "user_id": plan.user_id,
            "config": config,
            "metadata": metadata,
            "parameters": plan.parameters,
        }
        event = EventItem(
            event_type=EventType.TASK_PENDING,
            message="Enqueued task via MCP",
            context=event_context,
        )
        db.session.add(event)
        db.session.commit()

        created_at = plan.timestamp_created
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return {
            "task_id": plan_id,
            "created_at": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

def _get_plan_status_snapshot_sync(task_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        plan = find_plan_by_task_id(task_id)
        if plan is None:
            return None
        return {
            "id": str(plan.id),
            "state": plan.state,
            "stop_requested": bool(plan.stop_requested),
            "progress_percentage": plan.progress_percentage,
            "timestamp_created": plan.timestamp_created,
        }

def _request_plan_stop_sync(task_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        plan = find_plan_by_task_id(task_id)
        if plan is None:
            return None
        stop_requested = False
        if plan.state in (PlanState.pending, PlanState.processing):
            plan.stop_requested = True
            plan.stop_requested_timestamp = datetime.now(UTC)
            plan.progress_message = "Stop requested by user."
            db.session.commit()
            logger.info("Stop requested for task %s; stop flag set on plan %s.", task_id, plan.id)
            stop_requested = True
        return {
            "state": get_plan_state_mapping(plan.state),
            "stop_requested": stop_requested,
        }


def _retry_failed_plan_sync(task_id: str, model_profile: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        plan = find_plan_by_task_id(task_id)
        if plan is None:
            return None
        if plan.state != PlanState.failed:
            return {
                "error": {
                    "code": "TASK_NOT_FAILED",
                    "message": f"Task is not in failed state: {task_id}",
                }
            }

        normalized_profile = normalize_model_profile(model_profile).value
        now_utc = datetime.now(UTC)
        parameters = dict(plan.parameters) if isinstance(plan.parameters, dict) else {}
        parameters["model_profile"] = normalized_profile
        parameters["trigger_source"] = "mcp plan_retry"

        # Reset plan state and clear prior run artifacts before requeueing.
        plan.state = PlanState.pending
        plan.timestamp_created = now_utc
        plan.progress_percentage = 0.0
        plan.progress_message = "Retry requested via MCP."
        plan.stop_requested = False
        plan.stop_requested_timestamp = None
        plan.generated_report_html = None
        plan.run_zip_snapshot = None
        plan.run_track_activity_jsonl = None
        plan.run_track_activity_bytes = None
        plan.run_activity_overview_json = None
        plan.run_artifact_layout_version = None
        plan.parameters = parameters
        db.session.commit()

        event_context = {
            "task_id": str(plan.id),
            "task_handle": str(plan.id),
            "retry_of_task_id": task_id,
            "model_profile": normalized_profile,
            "parameters": plan.parameters,
        }
        event = EventItem(
            event_type=EventType.TASK_PENDING,
            message="Retried failed task via MCP",
            context=event_context,
        )
        db.session.add(event)
        db.session.commit()

        return {
            "task_id": str(plan.id),
            "state": get_plan_state_mapping(plan.state),
            "model_profile": normalized_profile,
            "retried_at": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


def _get_plan_for_report_sync(task_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        plan = resolve_plan_for_task_id(task_id)
        if plan is None:
            return None
        return {
            "id": str(plan.id),
            "state": plan.state,
            "progress_message": plan.progress_message,
        }

def _list_plans_sync(user_id: Optional[str], limit: int) -> list[dict[str, Any]]:
    with app.app_context():
        query = db.session.query(PlanItem)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        plans = (
            query
            .order_by(PlanItem.timestamp_created.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )
        results = []
        for plan in plans:
            created_at = plan.timestamp_created
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            results.append({
                "task_id": str(plan.id),
                "state": get_plan_state_mapping(plan.state),
                "progress_percentage": float(plan.progress_percentage or 0.0),
                "created_at": (
                    created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    if created_at else None
                ),
                "prompt_excerpt": (plan.prompt or "")[:PROMPT_EXCERPT_MAX_LENGTH],
            })
        return results


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_plan_state_mapping(plan_state: PlanState) -> str:
    """Map PlanState to MCP task state."""
    mapping = {
        PlanState.pending: "pending",
        PlanState.processing: "processing",
        PlanState.completed: "completed",
        PlanState.failed: "failed",
    }
    return mapping.get(plan_state, "pending")

def _extract_plan_create_metadata_overrides(arguments: dict[str, Any]) -> dict[str, Any]:
    """Extract plan_create runtime overrides from hidden metadata containers.

    Supported hidden containers:
    - arguments.tool_metadata
    - arguments.metadata
    - arguments._meta

    If a container includes nested namespaces, these are checked first:
    - plan_create
    - task_create (legacy alias)
    - planexe_task_create (legacy alias)
    - planexe
    """
    merged: dict[str, Any] = {}
    metadata_candidates: list[dict[str, Any]] = []

    for key in ("tool_metadata", "metadata", "_meta"):
        candidate = arguments.get(key)
        if isinstance(candidate, dict):
            metadata_candidates.append(candidate)

    for candidate in metadata_candidates:
        merged.update(candidate)
        for nested_key in ("plan_create", "task_create", "planexe_task_create", "planexe"):
            nested = candidate.get(nested_key)
            if isinstance(nested, dict):
                merged.update(nested)

    return merged

def _merge_plan_create_config(
    config: Optional[dict[str, Any]],
    model_profile: Optional[str],
) -> Optional[dict[str, Any]]:
    merged = dict(config or {})
    if isinstance(model_profile, str):
        candidate_profile = model_profile.strip()
        if candidate_profile and "model_profile" not in merged:
            merged["model_profile"] = candidate_profile
    return merged or None
