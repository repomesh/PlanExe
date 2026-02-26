import asyncio
import unittest
import uuid
import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, patch

from database_api.model_planitem import PlanState
from mcp_cloud.app import (
    REPORT_FILENAME,
    ZIP_CONTENT_TYPE,
    _sanitize_legacy_zip_snapshot,
    extract_file_from_zip_bytes,
    handle_plan_file_info,
    handle_list_tools,
    list_files_from_zip_bytes,
)


class TestPlanFileInfoTool(unittest.TestCase):
    def test_plan_file_info_tool_listed(self):
        tools = asyncio.run(handle_list_tools())
        tool_names = {tool.name for tool in tools}
        self.assertIn("plan_file_info", tool_names)

    def test_zip_helpers(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(REPORT_FILENAME, "<html>ok</html>")
            zip_file.writestr("001-2-plan.txt", "Plan prompt")
        zip_bytes = buffer.getvalue()

        files = list_files_from_zip_bytes(zip_bytes)
        self.assertIn(REPORT_FILENAME, files)
        self.assertIn("001-2-plan.txt", files)

        report_bytes = extract_file_from_zip_bytes(zip_bytes, REPORT_FILENAME)
        self.assertEqual(report_bytes, b"<html>ok</html>")

    def test_report_read_defaults_to_metadata(self):
        task_id = str(uuid.uuid4())
        content_bytes = b"a" * 10
        task_snapshot = {
            "id": "task-id",
            "state": PlanState.completed,
            "progress_message": None,
        }
        with patch("mcp_cloud.handlers._get_task_for_report_sync", return_value=task_snapshot):
            with patch(
                "mcp_cloud.handlers.fetch_artifact_from_worker_plan",
                new=AsyncMock(return_value=content_bytes),
            ):
                result = asyncio.run(handle_plan_file_info({"task_id": task_id}))

        payload = result.structuredContent
        self.assertEqual(payload["download_size"], len(content_bytes))
        self.assertEqual(payload["content_type"], "text/html; charset=utf-8")
        self.assertNotIn("download_path", payload)
        self.assertNotIn("content", payload)
        self.assertNotIn("state", payload)

    def test_report_read_zip(self):
        task_id = str(uuid.uuid4())
        content_bytes = b"zipdata"
        task_snapshot = {
            "id": "task-id",
            "state": PlanState.completed,
            "progress_message": None,
        }
        with patch("mcp_cloud.handlers._get_task_for_report_sync", return_value=task_snapshot):
            with patch(
                "mcp_cloud.handlers.fetch_user_downloadable_zip",
                new=AsyncMock(return_value=content_bytes),
            ):
                result = asyncio.run(handle_plan_file_info({"task_id": task_id, "artifact": "zip"}))

        payload = result.structuredContent
        self.assertEqual(payload["download_size"], len(content_bytes))
        self.assertEqual(payload["content_type"], ZIP_CONTENT_TYPE)

    def test_report_read_zip_for_failed_task(self):
        task_id = str(uuid.uuid4())
        content_bytes = b"zipdata"
        task_snapshot = {
            "id": "task-id",
            "state": PlanState.failed,
            "progress_message": "Stopped",
        }
        with patch("mcp_cloud.handlers._get_task_for_report_sync", return_value=task_snapshot):
            with patch(
                "mcp_cloud.handlers.fetch_user_downloadable_zip",
                new=AsyncMock(return_value=content_bytes),
            ):
                result = asyncio.run(handle_plan_file_info({"task_id": task_id, "artifact": "zip"}))

        payload = result.structuredContent
        self.assertEqual(payload["download_size"], len(content_bytes))
        self.assertEqual(payload["content_type"], ZIP_CONTENT_TYPE)

    def test_plan_file_info_returns_empty_object_when_pending(self):
        task_id = str(uuid.uuid4())
        task_snapshot = {
            "id": "task-id",
            "state": PlanState.pending,
            "progress_message": None,
        }
        with patch("mcp_cloud.handlers._get_task_for_report_sync", return_value=task_snapshot):
            result = asyncio.run(handle_plan_file_info({"task_id": task_id}))

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent, {"ready": False, "reason": "processing"})

    def test_plan_file_info_returns_generation_failed_payload(self):
        task_id = str(uuid.uuid4())
        task_snapshot = {
            "id": "task-id",
            "state": PlanState.failed,
            "progress_message": "Pipeline failed",
        }
        with patch("mcp_cloud.handlers._get_task_for_report_sync", return_value=task_snapshot):
            result = asyncio.run(handle_plan_file_info({"task_id": task_id, "artifact": "report"}))

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["error"]["code"], "generation_failed")

    def test_sanitize_legacy_zip_snapshot_removes_track_activity_jsonl(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(REPORT_FILENAME, "<html>ok</html>")
            zip_file.writestr("nested/track_activity.jsonl", "{\"event\":\"secret\"}\n")
        sanitized = _sanitize_legacy_zip_snapshot(buffer.getvalue())
        self.assertIsNotNone(sanitized)
        assert sanitized is not None
        files = list_files_from_zip_bytes(sanitized)
        self.assertIn(REPORT_FILENAME, files)
        self.assertNotIn("nested/track_activity.jsonl", files)


if __name__ == "__main__":
    unittest.main()
