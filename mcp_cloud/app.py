"""
PlanExe MCP Cloud

Implements the Model Context Protocol interface for PlanExe as specified in
 docs/mcp/planexe_mcp_interface.md. Communicates with worker_plan_database via the shared
database_api models.
"""
import asyncio
import contextvars
import hashlib
import io
import json
import logging
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import quote_plus
from io import BytesIO
import httpx
from sqlalchemy import cast, text
from sqlalchemy.dialects.postgresql import JSONB
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool, TextContent
from pydantic import BaseModel
from worker_plan_api.model_profile import (
    ModelProfileEnum,
    default_filename_for_profile,
    normalize_model_profile,
    resolve_model_profile_from_env,
)
from worker_plan_api.planexe_config import PlanExeConfig
from worker_plan_api.llm_class_filter import (
    ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES,
    is_llm_class_allowed,
    parse_llm_class_whitelist,
)

from mcp_cloud.dotenv_utils import load_planexe_dotenv
_dotenv_loaded, _dotenv_paths = load_planexe_dotenv(Path(__file__).parent)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
if not _dotenv_loaded:
    logger.warning(
        "No .env file found; searched: %s",
        ", ".join(str(path) for path in _dotenv_paths),
    )

from database_api.planexe_db_singleton import db
from database_api.model_taskitem import TaskItem, TaskState
from database_api.model_event import EventItem, EventType
from database_api.model_user_account import UserAccount
from database_api.model_user_api_key import UserApiKey
from flask import Flask, has_app_context
from mcp_cloud.tool_models import (
    ModelProfilesInput,
    ModelProfilesOutput,
    PromptExamplesInput,
    PromptExamplesOutput,
    TaskCreateInput,
    TaskCreateOutput,
    TaskStopOutput,
    TaskStatusInput,
    TaskStopInput,
    TaskFileInfoInput,
    TaskStatusSuccess,
    TaskFileInfoReadyOutput,
    ErrorDetail,
)

app = Flask(__name__)
app.config.from_pyfile('config.py')

def build_postgres_uri_from_env(env: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Construct a SQLAlchemy URI for Postgres using environment variables."""
    host = env.get("PLANEXE_POSTGRES_HOST") or "database_postgres"
    port = str(env.get("PLANEXE_POSTGRES_PORT") or "5432")
    dbname = env.get("PLANEXE_POSTGRES_DB") or "planexe"
    user = env.get("PLANEXE_POSTGRES_USER") or "planexe"
    password = env.get("PLANEXE_POSTGRES_PASSWORD") or "planexe"
    uri = f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{dbname}"
    safe_config = {"host": host, "port": port, "dbname": dbname, "user": user}
    return uri, safe_config

sqlalchemy_database_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
if sqlalchemy_database_uri is None:
    sqlalchemy_database_uri, db_settings = build_postgres_uri_from_env(os.environ)
    logger.info(f"SQLALCHEMY_DATABASE_URI not set. Using Postgres defaults: {db_settings}")
else:
    logger.info("Using SQLALCHEMY_DATABASE_URI from environment.")

app.config['SQLALCHEMY_DATABASE_URI'] = sqlalchemy_database_uri
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}
db.init_app(app)

def ensure_taskitem_stop_columns() -> None:
    statements = (
        "ALTER TABLE task_item ADD COLUMN IF NOT EXISTS run_track_activity_jsonl TEXT",
        "ALTER TABLE task_item ADD COLUMN IF NOT EXISTS run_track_activity_bytes INTEGER",
        "ALTER TABLE task_item ADD COLUMN IF NOT EXISTS run_activity_overview_json JSON",
        "ALTER TABLE task_item ADD COLUMN IF NOT EXISTS run_artifact_layout_version INTEGER",
        "ALTER TABLE task_item ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN",
        "ALTER TABLE task_item ADD COLUMN IF NOT EXISTS stop_requested_timestamp TIMESTAMP",
    )
    with db.engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception as exc:
                logger.warning("Schema update failed for %s: %s", statement, exc, exc_info=True)

with app.app_context():
    ensure_taskitem_stop_columns()

# Shown in MCP initialize (e.g. Inspector) so clients know what PlanExe does.
PLANEXE_SERVER_INSTRUCTIONS = (
    "PlanExe generates rough-draft project plans from a natural-language prompt. "
    "Use PlanExe for substantial multi-phase projects with constraints, stakeholders, budgets, and timelines. "
    "Do not use PlanExe for tiny one-shot outputs (for example: 'give me a 5-point checklist'); use a normal LLM response for that. "
    "The planning pipeline is fixed end-to-end; callers cannot select individual internal pipeline steps to run. "
    "Required interaction order: call prompt_examples first. "
    "Optional before task_create: call model_profiles to see profile guidance and available models in each profile. "
    "Then perform a non-tool step: draft a strong prompt and get user approval. "
    "Only after approval, call task_create. "
    "Each task_create call creates a new task_id; the server does not enforce a global per-client concurrency limit. "
    "Then poll task_status (about every 5 minutes); use task_file_info when complete. To stop, call task_stop with the task_id from task_create. "
    "Tool errors use {error:{code,message}}. task_file_info returns {} while output is not ready. "
    "task_file_info download_url is absolute when PLANEXE_MCP_PUBLIC_BASE_URL is configured or request host is available. "
    "If download_url is missing, configure PLANEXE_MCP_PUBLIC_BASE_URL on the server. "
    "task_status state contract: pending/processing => keep polling; completed => download is ready; failed => terminal error. "
    "Troubleshooting: if task_status stays in pending for longer than 5 minutes, the task was likely queued but not picked up by a worker (server issue). "
    "If task_status is in processing and output files do not change for longer than 20 minutes, the task_create likely failed/stalled. "
    "In both cases, report the issue to PlanExe developers on GitHub: https://github.com/PlanExeOrg/PlanExe/issues . "
    "Main output: large HTML report (~700KB) and zip of intermediary files (md, json, csv)."
)

mcp_cloud = Server("planexe-mcp-cloud", instructions=PLANEXE_SERVER_INSTRUCTIONS)

# Base directory for run artifacts (not used directly, fetched via worker_plan HTTP API)
BASE_DIR_RUN = Path(os.environ.get("PLANEXE_RUN_DIR", Path(__file__).parent.parent / "run")).resolve()

WORKER_PLAN_URL = os.environ.get("PLANEXE_WORKER_PLAN_URL", "http://worker_plan:8000")

REPORT_FILENAME = "030-report.html"
REPORT_CONTENT_TYPE = "text/html; charset=utf-8"
ZIP_FILENAME = "run.zip"
ZIP_CONTENT_TYPE = "application/zip"
ZIP_SNAPSHOT_MAX_BYTES = 100_000_000

SPEED_VS_DETAIL_DEFAULT = "ping_llm"
SPEED_VS_DETAIL_DEFAULT_ALIAS = "ping"
SPEED_VS_DETAIL_VALUES = (
    "ping_llm",
    "fast_but_skip_details",
    "all_details_but_slow",
)
ModelProfileInput = Literal[
    "baseline",
    "premium",
    "frontier",
    "custom",
]
SPEED_VS_DETAIL_ALIASES = {
    "ping": "ping_llm",
    "fast": "fast_but_skip_details",
    "all": "all_details_but_slow",
}
MODEL_PROFILE_TITLES = {
    ModelProfileEnum.BASELINE.value: "Baseline",
    ModelProfileEnum.PREMIUM.value: "Premium",
    ModelProfileEnum.FRONTIER.value: "Frontier",
    ModelProfileEnum.CUSTOM.value: "Custom",
}
MODEL_PROFILE_SUMMARIES = {
    ModelProfileEnum.BASELINE.value: "Cheap and fast; recommended default when creating a plan.",
    ModelProfileEnum.PREMIUM.value: "Higher-cost profile tuned for stronger output quality.",
    ModelProfileEnum.FRONTIER.value: "Most capable models first; usually slowest/most expensive.",
    ModelProfileEnum.CUSTOM.value: "User-managed profile file for custom model ordering.",
}

class TaskCreateRequest(BaseModel):
    prompt: str
    model_profile: Optional[ModelProfileInput] = None
    user_api_key: Optional[str] = None

class TaskStatusRequest(BaseModel):
    task_id: str

class TaskStopRequest(BaseModel):
    task_id: str

class TaskFileInfoRequest(BaseModel):
    task_id: str
    artifact: Optional[str] = None


class ModelProfilesRequest(BaseModel):
    """No input parameters."""
    pass

# Helper functions
def find_task_by_task_id(task_id: str) -> Optional[TaskItem]:
    """Find TaskItem by MCP task_id (UUID), with legacy fallback."""
    task = get_task_by_id(task_id)
    if task is not None:
        return task

    def _query_legacy() -> Optional[TaskItem]:
        query = db.session.query(TaskItem)
        if db.engine.dialect.name == "postgresql":
            tasks = query.filter(
                cast(TaskItem.parameters, JSONB).contains({"_mcp_task_id": task_id})
            ).all()
        else:
            tasks = query.filter(
                TaskItem.parameters.contains({"_mcp_task_id": task_id})
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

def get_task_by_id(task_id: str) -> Optional[TaskItem]:
    """Fetch a TaskItem by its UUID string."""
    def _query() -> Optional[TaskItem]:
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return None
        return db.session.get(TaskItem, task_uuid)

    if has_app_context():
        return _query()
    with app.app_context():
        return _query()

def resolve_task_for_task_id(task_id: str) -> Optional[TaskItem]:
    """Resolve a TaskItem from a task_id (UUID), with legacy fallback."""
    return find_task_by_task_id(task_id)

def _hash_user_api_key(raw_key: str) -> str:
    secret = os.environ.get("PLANEXE_API_KEY_SECRET", "dev-api-key-secret")
    if secret == "dev-api-key-secret":
        logger.warning("PLANEXE_API_KEY_SECRET not set. Using dev secret for API key hashing.")
    return hashlib.sha256(f"{secret}:{raw_key}".encode("utf-8")).hexdigest()

def _resolve_user_from_api_key(raw_key: str) -> Optional[dict[str, Any]]:
    if not raw_key:
        return None
    key_hash = _hash_user_api_key(raw_key)
    with app.app_context():
        api_key = UserApiKey.query.filter_by(key_hash=key_hash, revoked_at=None).first()
        if not api_key:
            return None
        user = db.session.get(UserAccount, api_key.user_id)
        if not user:
            return None

        user_context = {
            "user_id": str(user.id),
            "credits_balance": float(user.credits_balance or 0),
        }
        api_key.last_used_at = datetime.now(UTC)
        db.session.commit()
        return user_context

def _create_task_sync(
    prompt: str,
    config: Optional[dict[str, Any]],
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    with app.app_context():
        parameters = dict(config or {})
        parameters["speed_vs_detail"] = resolve_speed_vs_detail(parameters)
        parameters["model_profile"] = normalize_model_profile(parameters.get("model_profile")).value
        parameters["trigger_source"] = "mcp task_create"

        task = TaskItem(
            prompt=prompt,
            state=TaskState.pending,
            user_id=metadata.get("user_id", "mcp_user") if metadata else "mcp_user",
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
        task = find_task_by_task_id(task_id)
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
        task = find_task_by_task_id(task_id)
        if task is None:
            return None
        stop_requested = False
        if task.state in (TaskState.pending, TaskState.processing):
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

def list_files_from_zip_bytes(zip_bytes: bytes) -> list[str]:
    """List file entries from an in-memory zip archive."""
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_file:
            files = [name for name in zip_file.namelist() if not name.endswith("/")]
            return sorted(files)
    except Exception as exc:
        logger.warning("Unable to list files from zip snapshot: %s", exc)
        return []

def extract_file_from_zip_bytes(zip_bytes: bytes, file_path: str) -> Optional[bytes]:
    """Extract a file from an in-memory zip archive."""
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_file:
            file_path_normalized = file_path.lstrip('/')
            try:
                return zip_file.read(file_path_normalized)
            except KeyError:
                return None
    except Exception as exc:
        logger.warning("Unable to read %s from zip snapshot: %s", file_path, exc)
        return None

def extract_file_from_zip_file(file_handle: io.BufferedIOBase, file_path: str) -> Optional[bytes]:
    """Extract a file from a seekable zip file handle."""
    try:
        with zipfile.ZipFile(file_handle, 'r') as zip_file:
            file_path_normalized = file_path.lstrip('/')
            try:
                return zip_file.read(file_path_normalized)
            except KeyError:
                return None
    except Exception as exc:
        logger.warning("Unable to read %s from zip stream: %s", file_path, exc)
        return None

def fetch_report_from_db(task_id: str) -> Optional[bytes]:
    """Fetch the report HTML stored in the TaskItem."""
    task = get_task_by_id(task_id)
    if task and task.generated_report_html is not None:
        return task.generated_report_html.encode("utf-8")
    return None

def fetch_zip_snapshot(task_id: str) -> Optional[bytes]:
    """Fetch the zip snapshot stored in the TaskItem."""
    task = get_task_by_id(task_id)
    if task and task.run_zip_snapshot is not None:
        return task.run_zip_snapshot
    return None

def fetch_file_from_zip_snapshot(task_id: str, file_path: str) -> Optional[bytes]:
    """Fetch a file from the TaskItem zip snapshot."""
    task = get_task_by_id(task_id)
    if task and task.run_zip_snapshot is not None:
        return extract_file_from_zip_bytes(task.run_zip_snapshot, file_path)
    return None

def list_files_from_zip_snapshot(task_id: str) -> Optional[list[str]]:
    """List files from the TaskItem zip snapshot."""
    task = get_task_by_id(task_id)
    if task and task.run_zip_snapshot is not None:
        return list_files_from_zip_bytes(task.run_zip_snapshot)
    return None

async def fetch_artifact_from_worker_plan(run_id: str, file_path: str) -> Optional[bytes]:
    """Fetch an artifact file from worker_plan via HTTP."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # For report.html, use the dedicated report endpoint (most efficient)
            if (
                file_path == "report.html"
                or file_path.endswith("/report.html")
                or file_path == REPORT_FILENAME
                or file_path.endswith(f"/{REPORT_FILENAME}")
            ):
                report_response = await client.get(f"{WORKER_PLAN_URL}/runs/{run_id}/report")
                if report_response.status_code == 200:
                    return report_response.content
                logger.warning(f"Worker plan returned {report_response.status_code} for report: {run_id}")
                report_from_db = await asyncio.to_thread(fetch_report_from_db, run_id)
                if report_from_db is not None:
                    return report_from_db
                report_from_zip = await asyncio.to_thread(
                    fetch_file_from_zip_snapshot, run_id, REPORT_FILENAME
                )
                if report_from_zip is not None:
                    return report_from_zip
                return None
            
            # For other files, fetch the zip and extract the file
            # This is less efficient but works without a file serving endpoint
            async with client.stream("GET", f"{WORKER_PLAN_URL}/runs/{run_id}/zip") as zip_response:
                if zip_response.status_code != 200:
                    logger.warning(f"Worker plan returned {zip_response.status_code} for zip: {run_id}")
                else:
                    zip_too_large = False
                    content_length = zip_response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > ZIP_SNAPSHOT_MAX_BYTES:
                                logger.warning(
                                    "Zip snapshot too large (%s bytes) for run %s; skipping.",
                                    content_length,
                                    run_id,
                                )
                                zip_too_large = True
                        except ValueError:
                            logger.warning(
                                "Invalid Content-Length for zip snapshot: %s", content_length
                            )
                    if not zip_too_large:
                        with tempfile.TemporaryFile() as tmp_file:
                            size = 0
                            async for chunk in zip_response.aiter_bytes():
                                size += len(chunk)
                                if size > ZIP_SNAPSHOT_MAX_BYTES:
                                    logger.warning(
                                        "Zip snapshot exceeded max size (%s bytes) for run %s; skipping.",
                                        ZIP_SNAPSHOT_MAX_BYTES,
                                        run_id,
                                    )
                                    zip_too_large = True
                                    break
                                tmp_file.write(chunk)
                            if not zip_too_large:
                                tmp_file.seek(0)
                                file_data = extract_file_from_zip_file(tmp_file, file_path)
                                if file_data is not None:
                                    return file_data

            snapshot_file = await asyncio.to_thread(fetch_file_from_zip_snapshot, run_id, file_path)
            if snapshot_file is not None:
                return snapshot_file
            return None
            
    except Exception as e:
        logger.error(f"Error fetching artifact from worker_plan: {e}", exc_info=True)
        return None

async def fetch_file_list_from_worker_plan(run_id: str) -> Optional[list[str]]:
    """Fetch the list of files from worker_plan via HTTP."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{WORKER_PLAN_URL}/runs/{run_id}/files")
            if response.status_code == 200:
                data = response.json()
                files = data.get("files", [])
                if files:
                    return files
                fallback_files = await asyncio.to_thread(list_files_from_zip_snapshot, run_id)
                if fallback_files:
                    return fallback_files
                return files
            logger.warning(f"Worker plan returned {response.status_code} for files list: {run_id}")
            fallback_files = await asyncio.to_thread(list_files_from_zip_snapshot, run_id)
            if fallback_files is not None:
                return fallback_files
            return None
    except Exception as e:
        logger.error(f"Error fetching file list from worker_plan: {e}", exc_info=True)
        return None


def list_files_from_local_run_dir(run_id: str) -> Optional[list[str]]:
    """
    List files from local run directory when this service shares PLANEXE_RUN_DIR
    with the worker (e.g., Docker compose).
    """
    run_dir = (BASE_DIR_RUN / run_id).resolve()
    try:
        if not run_dir.is_relative_to(BASE_DIR_RUN):
            return None
    except ValueError:
        return None
    if not run_dir.exists() or not run_dir.is_dir():
        return None
    try:
        return sorted([path.name for path in run_dir.iterdir() if path.is_file()])
    except Exception as exc:
        logger.warning("Unable to list local run dir files for %s: %s", run_id, exc)
        return None

async def fetch_zip_from_worker_plan(run_id: str) -> Optional[bytes]:
    """Fetch the zip snapshot from worker_plan via HTTP."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", f"{WORKER_PLAN_URL}/runs/{run_id}/zip") as response:
                if response.status_code != 200:
                    logger.warning("Worker plan returned %s for zip: %s", response.status_code, run_id)
                else:
                    zip_too_large = False
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > ZIP_SNAPSHOT_MAX_BYTES:
                                logger.warning(
                                    "Zip snapshot too large (%s bytes) for run %s; skipping.",
                                    content_length,
                                    run_id,
                                )
                                zip_too_large = True
                        except ValueError:
                            logger.warning(
                                "Invalid Content-Length for zip snapshot: %s", content_length
                            )
                    if not zip_too_large:
                        buffer = BytesIO()
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > ZIP_SNAPSHOT_MAX_BYTES:
                                logger.warning(
                                    "Zip snapshot exceeded max size (%s bytes) for run %s; skipping.",
                                    ZIP_SNAPSHOT_MAX_BYTES,
                                    run_id,
                                )
                                zip_too_large = True
                                break
                            buffer.write(chunk)
                        if not zip_too_large:
                            return buffer.getvalue()

            snapshot_bytes = await asyncio.to_thread(fetch_zip_snapshot, run_id)
            if snapshot_bytes is not None:
                return snapshot_bytes
            return None
    except Exception as e:
        logger.error(f"Error fetching zip from worker_plan: {e}", exc_info=True)
        return None


def _sanitize_legacy_zip_snapshot(zip_bytes: bytes) -> Optional[bytes]:
    """Remove internal track_activity.jsonl files from legacy zip snapshots."""
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as in_zip:
            entries = [name for name in in_zip.namelist() if not name.endswith("/")]
            if not any(name.endswith("/track_activity.jsonl") or name == "track_activity.jsonl" for name in entries):
                return zip_bytes
            out_buffer = BytesIO()
            with zipfile.ZipFile(out_buffer, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
                for name in entries:
                    if name.endswith("/track_activity.jsonl") or name == "track_activity.jsonl":
                        continue
                    out_zip.writestr(name, in_zip.read(name))
            return out_buffer.getvalue()
    except Exception as exc:
        logger.warning("Unable to sanitize legacy run zip snapshot: %s", exc)
        return None


async def fetch_user_downloadable_zip(task_id: str) -> Optional[bytes]:
    """
    Fetch a user-downloadable zip for a task.
    New layout snapshots are served directly from TaskItem.run_zip_snapshot.
    Legacy/task-dir fallbacks are sanitized to remove track_activity.jsonl.
    """
    task = await asyncio.to_thread(get_task_by_id, task_id)
    if task is None:
        return None

    snapshot_bytes = task.run_zip_snapshot if task.run_zip_snapshot is not None else None
    layout_version = task.run_artifact_layout_version or 0
    if snapshot_bytes is not None:
        if layout_version >= 2:
            return snapshot_bytes
        return _sanitize_legacy_zip_snapshot(snapshot_bytes)

    worker_plan_zip = await fetch_zip_from_worker_plan(str(task.id))
    if worker_plan_zip is None:
        return None
    return _sanitize_legacy_zip_snapshot(worker_plan_zip)

def compute_sha256(content: str | bytes) -> str:
    """Compute SHA256 hash of content."""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()

def get_task_state_mapping(task_state: TaskState) -> str:
    """Map TaskState to MCP task state."""
    mapping = {
        TaskState.pending: "pending",
        TaskState.processing: "processing",
        TaskState.completed: "completed",
        TaskState.failed: "failed",
    }
    return mapping.get(task_state, "pending")

def resolve_speed_vs_detail(config: Optional[dict[str, Any]]) -> str:
    value: Optional[str] = None
    if isinstance(config, dict):
        raw_value = config.get("speed_vs_detail") or config.get("speed")
        if isinstance(raw_value, str):
            value = raw_value.strip().lower()
    if value in SPEED_VS_DETAIL_ALIASES:
        return SPEED_VS_DETAIL_ALIASES[value]
    if value in SPEED_VS_DETAIL_VALUES:
        return value
    return SPEED_VS_DETAIL_DEFAULT


def _extract_task_create_metadata_overrides(arguments: dict[str, Any]) -> dict[str, Any]:
    """Extract task_create runtime overrides from hidden metadata containers.

    Supported hidden containers:
    - arguments.tool_metadata
    - arguments.metadata
    - arguments._meta

    If a container includes nested namespaces, these are checked first:
    - task_create
    - planexe_task_create
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
        for nested_key in ("task_create", "planexe_task_create", "planexe"):
            nested = candidate.get(nested_key)
            if isinstance(nested, dict):
                merged.update(nested)

    return merged

def _merge_task_create_config(
    config: Optional[dict[str, Any]],
    speed_vs_detail: Optional[str],
    model_profile: Optional[str],
) -> Optional[dict[str, Any]]:
    merged = dict(config or {})
    if isinstance(speed_vs_detail, str):
        candidate = speed_vs_detail.strip()
        if candidate and "speed_vs_detail" not in merged and "speed" not in merged:
            merged["speed_vs_detail"] = candidate
    if isinstance(model_profile, str):
        candidate_profile = model_profile.strip()
        if candidate_profile and "model_profile" not in merged:
            merged["model_profile"] = candidate_profile
    return merged or None


def _sort_llm_config_entries(items: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    def sort_key(item: tuple[str, Any]) -> tuple[int, str]:
        key, model_data = item
        priority = None
        if isinstance(model_data, dict):
            maybe_priority = model_data.get("priority")
            if isinstance(maybe_priority, int):
                priority = maybe_priority
        if priority is None:
            priority = 999999
        return priority, key

    return sorted(items, key=sort_key)


def _extract_model_profile_entries(
    model_map: dict[str, Any],
    whitelist: Optional[set[str]],
) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []

    for model_key, model_data in _sort_llm_config_entries(list(model_map.items())):
        class_name = model_data.get("class") if isinstance(model_data, dict) else None
        if not is_llm_class_allowed(class_name, whitelist):
            continue

        model_name = None
        priority = None
        if isinstance(model_data, dict):
            arguments = model_data.get("arguments")
            if isinstance(arguments, dict):
                maybe_model = arguments.get("model")
                if isinstance(maybe_model, str):
                    model_name = maybe_model
            maybe_priority = model_data.get("priority")
            if isinstance(maybe_priority, int):
                priority = maybe_priority
            elif isinstance(model_data.get("prio"), int):
                priority = model_data["prio"]

        models.append(
            {
                "key": model_key,
                "provider_class": class_name if isinstance(class_name, str) else None,
                "model": model_name,
                "priority": priority,
            }
        )

    return models


def _profile_models_payload(
    profile: ModelProfileEnum,
    whitelist: Optional[set[str]],
) -> dict[str, Any]:
    config_filename = default_filename_for_profile(profile)
    planexe_config_path = PlanExeConfig.resolve_planexe_config_path()
    config_path = PlanExeConfig.find_file_in_search_order(config_filename, planexe_config_path)
    if config_path is None:
        return {
            "profile": profile.value,
            "title": MODEL_PROFILE_TITLES[profile.value],
            "summary": MODEL_PROFILE_SUMMARIES[profile.value],
            "model_count": 0,
            "models": [],
        }

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            model_map = json.load(fh)
    except Exception as exc:
        logger.warning(
            "Unable to read profile config %s for model profile %s: %s",
            config_filename,
            profile.value,
            exc,
        )
        return {
            "profile": profile.value,
            "title": MODEL_PROFILE_TITLES[profile.value],
            "summary": MODEL_PROFILE_SUMMARIES[profile.value],
            "model_count": 0,
            "models": [],
        }

    if not isinstance(model_map, dict):
        return {
            "profile": profile.value,
            "title": MODEL_PROFILE_TITLES[profile.value],
            "summary": MODEL_PROFILE_SUMMARIES[profile.value],
            "model_count": 0,
            "models": [],
        }

    models = _extract_model_profile_entries(model_map, whitelist)
    return {
        "profile": profile.value,
        "title": MODEL_PROFILE_TITLES[profile.value],
        "summary": MODEL_PROFILE_SUMMARIES[profile.value],
        "model_count": len(models),
        "models": models,
    }


def _get_model_profiles_sync() -> dict[str, Any]:
    raw_whitelist = os.environ.get(ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES)
    whitelist = parse_llm_class_whitelist(raw_whitelist)
    default_profile = resolve_model_profile_from_env().value
    profiles_all = [
        _profile_models_payload(profile, whitelist)
        for profile in ModelProfileEnum
    ]
    profiles = [profile for profile in profiles_all if int(profile.get("model_count") or 0) > 0]

    return {
        "default_profile": default_profile,
        "profiles": profiles,
        "message": (
            "Use one of these profile values in task_create.model_profile. "
            "Model lists show what is currently available in each profile."
        ),
    }

# Context var set by HTTP server so download URLs use the request's host when
# PLANEXE_MCP_PUBLIC_BASE_URL is not set (avoids localhost for remote clients).
_download_base_url_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "download_base_url", default=None
)


def set_download_base_url(base_url: Optional[str]) -> None:
    """Set the base URL used for download links for this request (e.g. from HTTP Request).
    Cleared automatically when the request ends. Used when PLANEXE_MCP_PUBLIC_BASE_URL is unset."""
    if base_url is not None:
        _download_base_url_ctx.set(base_url.rstrip("/"))
    else:
        try:
            _download_base_url_ctx.set("")
        except LookupError:
            pass


def clear_download_base_url() -> None:
    """Clear the request-scoped base URL (call when request ends)."""
    try:
        _download_base_url_ctx.set("")
    except LookupError:
        pass


def _get_download_base_url() -> Optional[str]:
    """Return base URL for download links: env var, then request context, then None."""
    base_url = os.environ.get("PLANEXE_MCP_PUBLIC_BASE_URL")
    if base_url:
        return base_url.rstrip("/")
    try:
        ctx_url = _download_base_url_ctx.get()
        return ctx_url if ctx_url else None
    except LookupError:
        return None


def build_report_download_path(task_id: str) -> str:
    return f"/download/{task_id}/{REPORT_FILENAME}"


def build_report_download_url(task_id: str) -> Optional[str]:
    base_url = _get_download_base_url()
    if not base_url:
        return None
    return f"{base_url}{build_report_download_path(task_id)}"


def build_zip_download_path(task_id: str) -> str:
    return f"/download/{task_id}/{ZIP_FILENAME}"


def build_zip_download_url(task_id: str) -> Optional[str]:
    base_url = _get_download_base_url()
    if not base_url:
        return None
    return f"{base_url}{build_zip_download_path(task_id)}"


def _load_mcp_example_prompts() -> list[str]:
    """Load prompts from the catalog that are marked as MCP examples (mcp_example or mcp-example-prompt true).

    Uses worker_plan_api.PromptCatalog the same way as frontend_single_user and frontend_multi_user
    (no env var). Tries repo-root import first, then adds worker_plan to sys.path so worker_plan_api
    is top-level (same as frontends). Falls back to built-in examples if the catalog is unavailable.
    """
    catalog = None
    try:
        from worker_plan.worker_plan_api.prompt_catalog import PromptCatalog

        catalog = PromptCatalog()
        catalog.load_simple_plan_prompts()
    except Exception:
        try:
            # Same as frontends when worker_plan exists; when not (e.g. Docker), repo_root has worker_plan_api
            import sys

            repo_root = Path(__file__).resolve().parent.parent
            worker_plan_dir = repo_root / "worker_plan"
            path_to_add = str(worker_plan_dir if worker_plan_dir.exists() else repo_root)
            if path_to_add not in sys.path:
                sys.path.insert(0, path_to_add)
            from worker_plan_api.prompt_catalog import PromptCatalog

            catalog = PromptCatalog()
            catalog.load_simple_plan_prompts()
        except Exception as e:
            logger.warning(
                "Prompt catalog unavailable (%s); using built-in examples.",
                e,
            )
            return _builtin_mcp_example_prompts()

    if catalog is None:
        return _builtin_mcp_example_prompts()

    samples: list[str] = []
    for item in catalog.all():
        if item.extras.get("mcp_example") is True or item.extras.get("mcp-example-prompt") is True:
            samples.append(item.prompt)
    if not samples:
        return _builtin_mcp_example_prompts()
    return samples


def _builtin_mcp_example_prompts() -> list[str]:
    """Fallback example prompts when the catalog file is missing or has no mcp_example entries."""
    return [
        (
            "Vegan Butcher Shop. That sells artificial meat (Plant-Based). Location Kødbyen, Copenhagen. "
            "Sell sandwiches and sausages. Provocative marketing. Budget: 10 million DKK. Grand Opening in month 3. "
            "Profitability Goal: month 12. Create a signature item that is a social media hit. "
            "Pick a realistic scenario. I already have negotiated a 2 year lease inside Kødbyen. "
            "Banned words: blockchain, VR, AR, AI, Robots."
        ),
        (
            "Start a dental clinic in Copenhagen with 3 treatment rooms, targeting families and children. "
            "Budget 2.5M DKK. Open within 12 months. Include equipment, staffing, permits, and marketing. "
            "Pick a realistic scenario; avoid overly ambitious timelines."
        ),
    ]


TASK_CREATE_INPUT_SCHEMA = TaskCreateInput.model_json_schema()
TASK_CREATE_OUTPUT_SCHEMA = TaskCreateOutput.model_json_schema()
TASK_STATUS_SUCCESS_SCHEMA = TaskStatusSuccess.model_json_schema()
TASK_STATUS_OUTPUT_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"error": ErrorDetail.model_json_schema()},
            "required": ["error"],
        },
        TASK_STATUS_SUCCESS_SCHEMA,
    ]
}
TASK_STOP_OUTPUT_SCHEMA = TaskStopOutput.model_json_schema()
TASK_FILE_INFO_READY_OUTPUT_SCHEMA = TaskFileInfoReadyOutput.model_json_schema()
TASK_FILE_INFO_OUTPUT_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"error": ErrorDetail.model_json_schema()},
            "required": ["error"],
        },
        {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        TASK_FILE_INFO_READY_OUTPUT_SCHEMA,
    ]
}
TASK_STATUS_INPUT_SCHEMA = TaskStatusInput.model_json_schema()
TASK_STOP_INPUT_SCHEMA = TaskStopInput.model_json_schema()
TASK_FILE_INFO_INPUT_SCHEMA = TaskFileInfoInput.model_json_schema()

PROMPT_EXAMPLES_INPUT_SCHEMA = PromptExamplesInput.model_json_schema()
PROMPT_EXAMPLES_OUTPUT_SCHEMA = PromptExamplesOutput.model_json_schema()
MODEL_PROFILES_INPUT_SCHEMA = ModelProfilesInput.model_json_schema()
MODEL_PROFILES_OUTPUT_SCHEMA = ModelProfilesOutput.model_json_schema()

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: Optional[dict[str, Any]] = None

TOOL_DEFINITIONS = [
    ToolDefinition(
        name="prompt_examples",
        description=(
            "Call this first. Returns example prompts that define what a good prompt looks like. "
            "Do NOT call task_create yet. Optional before task_create: call model_profiles to choose model_profile. "
            "Next is a non-tool step: formulate a prompt (use examples as a baseline, similar structure) and get user approval. "
            "Then call task_create. "
            "PlanExe is not for tiny one-shot outputs like a 5-point checklist; and it does not support selecting only some internal pipeline steps."
        ),
        input_schema=PROMPT_EXAMPLES_INPUT_SCHEMA,
        output_schema=PROMPT_EXAMPLES_OUTPUT_SCHEMA,
    ),
    ToolDefinition(
        name="model_profiles",
        description=(
            "Optional helper before task_create. Returns model_profile options with plain-language guidance "
            "and currently available models in each profile."
        ),
        input_schema=MODEL_PROFILES_INPUT_SCHEMA,
        output_schema=MODEL_PROFILES_OUTPUT_SCHEMA,
    ),
    ToolDefinition(
        name="task_create",
        description=(
            "Call only after prompt_examples and after you have completed prompt drafting/approval (non-tool step). "
            "PlanExe turns the approved prompt into a structured strategic-plan draft (executive summary, Gantt, risk register, governance, etc.) in ~15–20 min. "
            "Returns task_id (UUID); use it for task_status, task_stop, and task_file_info. "
            "Each task_create call creates a new task_id (no server-side dedup). "
            "If you are unsure which model_profile to choose, call model_profiles first. "
            "If your deployment uses credits, include user_api_key to charge the correct account. "
            "Common error codes: INVALID_USER_API_KEY, USER_API_KEY_REQUIRED, INSUFFICIENT_CREDITS. "
            "Optional runtime overrides such as speed_vs_detail are intentionally hidden from the visible tool schema "
            "and can be provided via tool-specific metadata by developers."
        ),
        input_schema=TASK_CREATE_INPUT_SCHEMA,
        output_schema=TASK_CREATE_OUTPUT_SCHEMA,
    ),
    ToolDefinition(
        name="task_status",
        description=(
            "Returns status and progress of the plan currently being created. "
            "Poll at reasonable intervals only (e.g. every 5 minutes): plan generation takes 15–20+ minutes "
            "and frequent polling is unnecessary. "
            "State contract: pending/processing => keep polling; completed => download is ready; failed => terminal error. "
            "Unknown task_id returns error code TASK_NOT_FOUND. "
            "Troubleshooting: pending for >5 minutes likely means queued but not picked up by a worker. "
            "processing with no file-output changes for >20 minutes likely means failed/stalled. "
            "Report these issues to https://github.com/PlanExeOrg/PlanExe/issues ."
        ),
        input_schema=TASK_STATUS_INPUT_SCHEMA,
        output_schema=TASK_STATUS_OUTPUT_SCHEMA,
    ),
    ToolDefinition(
        name="task_stop",
        description=(
            "Request the plan generation to stop. Pass the task_id (the UUID returned by task_create). "
            "Call task_stop with that task_id."
        ),
        input_schema=TASK_STOP_INPUT_SCHEMA,
        output_schema=TASK_STOP_OUTPUT_SCHEMA,
    ),
    ToolDefinition(
        name="task_file_info",
        description=(
            "Returns file metadata (content_type, download_url, download_size) for the report or zip. "
            "If your client exposes task_download (e.g. mcp_local), use that to save the file locally; "
            "otherwise use this tool to get download_url and fetch the file yourself. "
            "download_url is generated from PLANEXE_MCP_PUBLIC_BASE_URL (or request host when available). "
            "Returns {} while artifact is not ready. Terminal tool-level error payloads use codes generation_failed or content_unavailable."
        ),
        input_schema=TASK_FILE_INFO_INPUT_SCHEMA,
        output_schema=TASK_FILE_INFO_OUTPUT_SCHEMA,
    ),
]

@mcp_cloud.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name=definition.name,
            description=definition.description,
            outputSchema=definition.output_schema,
            inputSchema=definition.input_schema,
        )
        for definition in TOOL_DEFINITIONS
    ]

@mcp_cloud.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    """Dispatch MCP tool calls and return structured JSON errors for unknown tools."""
    try:
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            response = {"error": {"code": "INVALID_TOOL", "message": f"Unknown tool: {name}"}}
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response))],
                structuredContent=response,
                isError=True,
            )
        return await handler(arguments)
    except Exception as e:
        logger.error(f"Error handling tool {name}: {e}", exc_info=True)
        response = {"error": {"code": "INTERNAL_ERROR", "message": str(e)}}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )

async def handle_task_create(arguments: dict[str, Any]) -> CallToolResult:
    """Create a new PlanExe task and enqueue it for processing.

    Examples:
        - {"prompt": "Start a dental clinic in Copenhagen with 3 treatment rooms, targeting families and children. Budget 2.5M DKK. Open within 12 months."} → returns task_id (UUID) + created_at
        - {"prompt": "Launch a bike repair shop in Amsterdam with retail sales, service bays, and mobile repair van. Budget 150k EUR. Profitability goal: month 18.", "metadata": {"task_create": {"speed_vs_detail": "fast"}}} → faster run

    Args:
        - prompt: What the plan should cover (goal, context, constraints).
        - model_profile: Optional profile ("baseline" | "premium" | "frontier" | "custom"). Call model_profiles to inspect options.
        - speed_vs_detail: Optional hidden runtime override via tool-specific metadata.

    Returns:
        - content: JSON string matching structuredContent.
        - structuredContent: {"task_id": "<uuid>", "created_at": ...}
        - isError: False on success.
    """
    req = TaskCreateRequest(**arguments)
    metadata_overrides = _extract_task_create_metadata_overrides(arguments)
    metadata_model_profile = metadata_overrides.get("model_profile")
    model_profile = req.model_profile
    if model_profile is None and isinstance(metadata_model_profile, str):
        model_profile = metadata_model_profile

    speed_vs_detail = metadata_overrides.get("speed_vs_detail")
    if not isinstance(speed_vs_detail, str):
        speed_alias = metadata_overrides.get("speed")
        if isinstance(speed_alias, str):
            speed_vs_detail = speed_alias
        else:
            # Backward-compatible hidden override when callers still send legacy top-level args.
            legacy_speed = arguments.get("speed_vs_detail")
            if isinstance(legacy_speed, str):
                speed_vs_detail = legacy_speed
            elif isinstance(arguments.get("speed"), str):
                speed_vs_detail = arguments.get("speed")

    merged_config = _merge_task_create_config(None, speed_vs_detail, model_profile)
    require_user_key = os.environ.get("PLANEXE_MCP_REQUIRE_USER_KEY", "false").lower() in ("1", "true", "yes", "on")
    user_context = None
    if req.user_api_key:
        user_context = _resolve_user_from_api_key(req.user_api_key.strip())
        if not user_context:
            response = {"error": {"code": "INVALID_USER_API_KEY", "message": "Invalid user_api_key."}}
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response))],
                structuredContent=response,
                isError=True,
            )
    elif require_user_key:
        response = {"error": {"code": "USER_API_KEY_REQUIRED", "message": "user_api_key is required for task_create."}}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )

    if user_context and float(user_context.get("credits_balance", 0.0)) <= 0.0:
        response = {"error": {"code": "INSUFFICIENT_CREDITS", "message": "Not enough credits."}}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )

    response = await asyncio.to_thread(
        _create_task_sync,
        req.prompt,
        merged_config,
        {"user_id": str(user_context["user_id"])} if user_context else None,
    )
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(response))],
        structuredContent=response,
        isError=False,
    )


async def handle_prompt_examples(arguments: dict[str, Any]) -> CallToolResult:
    """Return curated prompts from the catalog (mcp_example true) so LLMs can see example detail."""
    samples = _load_mcp_example_prompts()
    payload = {
        "samples": samples,
        "message": (
            "Next: complete the non-tool step by drafting a good prompt using these as a baseline (similar structure), then get user approval. "
            "Only after approval, call task_create. "
            "Do not use PlanExe for tiny one-shot requests (e.g., rewrite this email, summarize this document). "
            "PlanExe always runs the full fixed planning pipeline; callers cannot run only selected internal steps."
        ),
    }
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=False,
    )


async def handle_model_profiles(arguments: dict[str, Any]) -> CallToolResult:
    """Return model profile options and currently available models in each profile."""
    _ = ModelProfilesRequest(**(arguments or {}))
    payload = await asyncio.to_thread(_get_model_profiles_sync)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=False,
    )


async def handle_task_status(arguments: dict[str, Any]) -> CallToolResult:
    """Fetch the current task status, progress, and recent files for a task.

    Examples:
        - {"task_id": "uuid"} → state/progress/timing + recent files

    Args:
        - task_id: Task UUID returned by task_create.

    Returns:
        - content: JSON string matching structuredContent.
        - structuredContent: status payload or error.
        - isError: True only when task_id is unknown.
    """
    req = TaskStatusRequest(**arguments)
    task_id = req.task_id

    task_snapshot = await asyncio.to_thread(_get_task_status_snapshot_sync, task_id)
    if task_snapshot is None:
        response = {
            "error": {
                "code": "TASK_NOT_FOUND",
                "message": f"Task not found: {task_id}",
            }
        }
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )

    progress_percentage = float(task_snapshot.get("progress_percentage") or 0.0)

    task_state = task_snapshot["state"]
    state = get_task_state_mapping(task_state)
    if task_state == TaskState.completed:
        progress_percentage = 100.0

    # Collect files from worker_plan
    task_uuid = task_snapshot["id"]
    files = []
    if task_uuid:
        files_list = await fetch_file_list_from_worker_plan(task_uuid)
        if not files_list:
            files_list = await asyncio.to_thread(list_files_from_zip_snapshot, task_uuid)
        if not files_list:
            files_list = await asyncio.to_thread(list_files_from_local_run_dir, task_uuid)
        if files_list:
            for file_name in files_list[:10]:  # Limit to 10 most recent
                if file_name != "log.txt":
                    updated_at = datetime.now(UTC).replace(microsecond=0)
                    files.append({
                        "path": file_name,
                        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),  # Approximate
                    })

    created_at = task_snapshot["timestamp_created"]
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    response = {
        "task_id": task_uuid,
        "state": state,
        "progress_percentage": progress_percentage,
        "timing": {
            "started_at": (
                created_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                if created_at
                else None
            ),
            "elapsed_sec": (datetime.now(UTC) - created_at).total_seconds() if created_at else 0,
        },
        "files": files[:10],  # Limit to 10 most recent
    }

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(response))],
        structuredContent=response,
        isError=False,
    )

async def handle_task_stop(arguments: dict[str, Any]) -> CallToolResult:
    """Request an active task to stop.

    Examples:
        - {"task_id": "uuid"} → stop request accepted

    Args:
        - task_id: Task UUID returned by task_create.

    Returns:
        - content: JSON string matching structuredContent.
        - structuredContent: {"state": "pending|processing|completed|failed", "stop_requested": bool} or error payload.
        - isError: True only when task_id is unknown.
    """
    req = TaskStopRequest(**arguments)
    task_id = req.task_id

    stop_result = await asyncio.to_thread(_request_task_stop_sync, task_id)
    if stop_result is None:
        response = {
            "error": {
                "code": "TASK_NOT_FOUND",
                "message": f"Task not found: {task_id}",
            }
        }
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )

    response = stop_result

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(response))],
        structuredContent=response,
        isError=False,
    )

async def handle_task_file_info(arguments: dict[str, Any]) -> CallToolResult:
    """Return download metadata for a task's report or zip artifact.

    Examples:
        - {"task_id": "uuid"} → report metadata (default)
        - {"task_id": "uuid", "artifact": "zip"} → zip metadata

    Args:
        - task_id: Task UUID returned by task_create.
        - artifact: Optional "report" or "zip".

    Returns:
        - content: JSON string matching structuredContent.
        - structuredContent: metadata (content_type, sha256, download_size,
          optional download_url) or {} if not ready, or error payload.
        - isError: True only when task_id is unknown.
    """
    req = TaskFileInfoRequest(**arguments)
    task_id = req.task_id
    artifact = req.artifact.strip().lower() if isinstance(req.artifact, str) else "report"
    if artifact not in ("report", "zip"):
        artifact = "report"
    task_snapshot = await asyncio.to_thread(_get_task_for_report_sync, task_id)
    if task_snapshot is None:
        response = {
            "error": {
                "code": "TASK_NOT_FOUND",
                "message": f"Task not found: {task_id}",
            }
        }
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )

    run_id = task_snapshot["id"]
    if artifact == "zip":
        content_bytes = await fetch_user_downloadable_zip(run_id)
        if content_bytes is None:
            task_state = task_snapshot["state"]
            if task_state in (TaskState.pending, TaskState.processing) or task_state is None:
                response = {}
            else:
                response = {
                    "error": {
                        "code": "content_unavailable",
                        "message": "zip content_bytes is None",
                    },
                }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response))],
                structuredContent=response,
                isError=False,
            )

        total_size = len(content_bytes)
        content_hash = compute_sha256(content_bytes)
        response = {
            "content_type": ZIP_CONTENT_TYPE,
            "sha256": content_hash,
            "download_size": total_size,
        }
        download_url = build_zip_download_url(run_id)
        if download_url:
            response["download_url"] = download_url

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=False,
        )

    task_state = task_snapshot["state"]
    if task_state in (TaskState.pending, TaskState.processing) or task_state is None:
        response = {}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=False,
        )
    if task_state == TaskState.failed:
        message = task_snapshot["progress_message"] or "Plan generation failed."
        response = {"error": {"code": "generation_failed", "message": message}}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=False,
        )

    content_bytes = await fetch_artifact_from_worker_plan(run_id, REPORT_FILENAME)
    if content_bytes is None:
        response = {
            "error": {
                "code": "content_unavailable",
                "message": "content_bytes is None",
            },
        }
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=False,
        )

    total_size = len(content_bytes)
    content_hash = compute_sha256(content_bytes)
    response = {
        "content_type": REPORT_CONTENT_TYPE,
        "sha256": content_hash,
        "download_size": total_size,
    }
    download_url = build_report_download_url(run_id)
    if download_url:
        response["download_url"] = download_url

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(response))],
        structuredContent=response,
        isError=False,
    )

TOOL_HANDLERS = {
    "task_create": handle_task_create,
    "task_status": handle_task_status,
    "task_stop": handle_task_stop,
    "task_file_info": handle_task_file_info,
    "prompt_examples": handle_prompt_examples,
    "model_profiles": handle_model_profiles,
}

async def main():
    """Main entry point for MCP server."""
    logger.info("Starting PlanExe MCP Cloud...")
    
    with app.app_context():
        db.create_all()
        logger.info("Database initialized")
    
    async with stdio_server() as streams:
        await mcp_cloud.run(
            streams[0],
            streams[1],
            mcp_cloud.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
