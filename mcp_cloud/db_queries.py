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


# ---------------------------------------------------------------------------
# Task lookup
# ---------------------------------------------------------------------------

def find_plan_by_task_id(task_id: str) -> Optional[PlanItem]:
    """Find PlanItem by MCP task_id (UUID), with legacy fallback."""
    task = get_task_by_id(task_id)
    if task is not None:
        return task

    def _query_legacy() -> Optional[PlanItem]:
        query = db.session.query(PlanItem)
        if db.engine.dialect.name == "postgresql":
            tasks = query.filter(
                cast(PlanItem.parameters, JSONB).contains({"_mcp_task_id": task_id})
            ).all()
        else:
            tasks = query.filter(
                PlanItem.parameters.contains({"_mcp_task_id": task_id})
            ).all()
        if tasks:
            return tasks[0]
        return None

    if has_app_context():
        legacy_task = _query_legacy()
    else:
        with app.app_context():
            legacy_task = _query_legacy()
    if legacy_task is not None:
        logger.debug("Resolved legacy MCP task id %s to task %s", task_id, legacy_task.id)
    return legacy_task

def get_task_by_id(task_id: str) -> Optional[PlanItem]:
    """Fetch a PlanItem by its UUID string."""
    def _query() -> Optional[PlanItem]:
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return None
        return db.session.get(PlanItem, task_uuid)

    if has_app_context():
        return _query()
    with app.app_context():
        return _query()

def resolve_task_for_task_id(task_id: str) -> Optional[PlanItem]:
    """Resolve a PlanItem from a task_id (UUID), with legacy fallback."""
    return find_plan_by_task_id(task_id)


# ---------------------------------------------------------------------------
# Sync operations called from handlers via asyncio.to_thread
# ---------------------------------------------------------------------------

def _create_task_sync(
    prompt: str,
    config: Optional[dict[str, Any]],
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    with app.app_context():
        parameters = dict(config or {})
        parameters["model_profile"] = normalize_model_profile(parameters.get("model_profile")).value
        parameters["trigger_source"] = "mcp plan_create"

        task = PlanItem(
            prompt=prompt,
            state=PlanState.pending,
            user_id=metadata.get("user_id", "admin") if metadata else "admin",
            parameters=parameters,
        )
        db.session.add(task)
        db.session.commit()

        task_id = str(task.id)
        event_context = {
            "task_id": task_id,
            "task_handle": task_id,
            "prompt": task.prompt,
            "user_id": task.user_id,
            "config": config,
            "metadata": metadata,
            "parameters": task.parameters,
        }
        event = EventItem(
            event_type=EventType.TASK_PENDING,
            message="Enqueued task via MCP",
            context=event_context,
        )
        db.session.add(event)
        db.session.commit()

        created_at = task.timestamp_created
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return {
            "task_id": task_id,
            "created_at": created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }

def _get_task_status_snapshot_sync(task_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        task = find_plan_by_task_id(task_id)
        if task is None:
            return None
        return {
            "id": str(task.id),
            "state": task.state,
            "stop_requested": bool(task.stop_requested),
            "progress_percentage": task.progress_percentage,
            "timestamp_created": task.timestamp_created,
        }

def _request_task_stop_sync(task_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        task = find_plan_by_task_id(task_id)
        if task is None:
            return None
        stop_requested = False
        if task.state in (PlanState.pending, PlanState.processing):
            task.stop_requested = True
            task.stop_requested_timestamp = datetime.now(UTC)
            task.progress_message = "Stop requested by user."
            db.session.commit()
            logger.info("Stop requested for task %s; stop flag set on task %s.", task_id, task.id)
            stop_requested = True
        return {
            "state": get_task_state_mapping(task.state),
            "stop_requested": stop_requested,
        }


def _retry_failed_task_sync(task_id: str, model_profile: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        task = find_plan_by_task_id(task_id)
        if task is None:
            return None
        if task.state != PlanState.failed:
            return {
                "error": {
                    "code": "TASK_NOT_FAILED",
                    "message": f"Task is not in failed state: {task_id}",
                }
            }

        normalized_profile = normalize_model_profile(model_profile).value
        now_utc = datetime.now(UTC)
        parameters = dict(task.parameters) if isinstance(task.parameters, dict) else {}
        parameters["model_profile"] = normalized_profile
        parameters["trigger_source"] = "mcp plan_retry"

        # Reset task state and clear prior run artifacts before requeueing.
        task.state = PlanState.pending
        task.timestamp_created = now_utc
        task.progress_percentage = 0.0
        task.progress_message = "Retry requested via MCP."
        task.stop_requested = False
        task.stop_requested_timestamp = None
        task.generated_report_html = None
        task.run_zip_snapshot = None
        task.run_track_activity_jsonl = None
        task.run_track_activity_bytes = None
        task.run_activity_overview_json = None
        task.run_artifact_layout_version = None
        task.parameters = parameters
        db.session.commit()

        event_context = {
            "task_id": str(task.id),
            "task_handle": str(task.id),
            "retry_of_task_id": task_id,
            "model_profile": normalized_profile,
            "parameters": task.parameters,
        }
        event = EventItem(
            event_type=EventType.TASK_PENDING,
            message="Retried failed task via MCP",
            context=event_context,
        )
        db.session.add(event)
        db.session.commit()

        return {
            "task_id": str(task.id),
            "state": get_task_state_mapping(task.state),
            "model_profile": normalized_profile,
            "retried_at": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


def _get_task_for_report_sync(task_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        task = resolve_task_for_task_id(task_id)
        if task is None:
            return None
        return {
            "id": str(task.id),
            "state": task.state,
            "progress_message": task.progress_message,
        }

def _list_tasks_sync(user_id: Optional[str], limit: int) -> list[dict[str, Any]]:
    with app.app_context():
        query = db.session.query(PlanItem)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        tasks = (
            query
            .order_by(PlanItem.timestamp_created.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )
        results = []
        for task in tasks:
            created_at = task.timestamp_created
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            results.append({
                "task_id": str(task.id),
                "state": get_task_state_mapping(task.state),
                "progress_percentage": float(task.progress_percentage or 0.0),
                "created_at": (
                    created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    if created_at else None
                ),
                "prompt_excerpt": (task.prompt or "")[:100],
            })
        return results


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_task_state_mapping(task_state: PlanState) -> str:
    """Map PlanState to MCP task state."""
    mapping = {
        PlanState.pending: "pending",
        PlanState.processing: "processing",
        PlanState.completed: "completed",
        PlanState.failed: "failed",
    }
    return mapping.get(task_state, "pending")

def _extract_task_create_metadata_overrides(arguments: dict[str, Any]) -> dict[str, Any]:
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

def _merge_task_create_config(
    config: Optional[dict[str, Any]],
    model_profile: Optional[str],
) -> Optional[dict[str, Any]]:
    merged = dict(config or {})
    if isinstance(model_profile, str):
        candidate_profile = model_profile.strip()
        if candidate_profile and "model_profile" not in merged:
            merged["model_profile"] = candidate_profile
    return merged or None
