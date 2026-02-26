"""PlanExe MCP Cloud – zip extraction, sanitization, and hashing utilities."""
import hashlib
import io
import logging
import zipfile
from io import BytesIO
from typing import Optional

from mcp_cloud.db_queries import get_plan_by_id

logger = logging.getLogger(__name__)


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

def fetch_report_from_db(plan_id: str) -> Optional[bytes]:
    """Fetch the report HTML stored in the PlanItem."""
    plan = get_plan_by_id(plan_id)
    if plan and plan.generated_report_html is not None:
        return plan.generated_report_html.encode("utf-8")
    return None

def fetch_zip_snapshot(plan_id: str) -> Optional[bytes]:
    """Fetch the zip snapshot stored in the PlanItem."""
    plan = get_plan_by_id(plan_id)
    if plan and plan.run_zip_snapshot is not None:
        return plan.run_zip_snapshot
    return None

def fetch_file_from_zip_snapshot(plan_id: str, file_path: str) -> Optional[bytes]:
    """Fetch a file from the PlanItem zip snapshot."""
    plan = get_plan_by_id(plan_id)
    if plan and plan.run_zip_snapshot is not None:
        return extract_file_from_zip_bytes(plan.run_zip_snapshot, file_path)
    return None

def list_files_from_zip_snapshot(plan_id: str) -> Optional[list[str]]:
    """List files from the PlanItem zip snapshot."""
    plan = get_plan_by_id(plan_id)
    if plan and plan.run_zip_snapshot is not None:
        return list_files_from_zip_bytes(plan.run_zip_snapshot)
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

def compute_sha256(content: str | bytes) -> str:
    """Compute SHA256 hash of content."""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()
