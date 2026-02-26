import asyncio
import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from mcp.types import CallToolResult
from database_api.model_planitem import PlanState
from mcp_cloud.app import handle_plan_status as handle_task_status


class TestTaskStatusTool(unittest.TestCase):
    def test_task_status_returns_structured_content(self):
        task_id = str(uuid.uuid4())
        task_snapshot = {
            "id": task_id,
            "state": PlanState.completed,
            "stop_requested": False,
            "progress_percentage": 0.0,
            "timestamp_created": datetime.now(UTC),
        }
        with patch(
            "mcp_cloud.app._get_task_status_snapshot_sync",
            return_value=task_snapshot,
        ), patch(
            "mcp_cloud.app.fetch_file_list_from_worker_plan", new=AsyncMock(return_value=[])
        ):
            result = asyncio.run(handle_task_status({"task_id": task_id}))

        self.assertIsInstance(result, CallToolResult)
        self.assertIsInstance(result.structuredContent, dict)
        self.assertEqual(result.structuredContent["task_id"], task_id)
        self.assertIn("state", result.structuredContent)
        self.assertIn("progress_percentage", result.structuredContent)
        self.assertIsInstance(result.structuredContent["progress_percentage"], float)
        self.assertEqual(result.structuredContent["progress_percentage"], 100.0)

    def test_task_status_falls_back_to_zip_snapshot_files_when_primary_source_empty(self):
        task_id = str(uuid.uuid4())
        task_snapshot = {
            "id": task_id,
            "state": PlanState.processing,
            "stop_requested": False,
            "progress_percentage": 34.23,
            "timestamp_created": datetime.now(UTC),
        }
        with patch(
            "mcp_cloud.app._get_task_status_snapshot_sync",
            return_value=task_snapshot,
        ), patch(
            "mcp_cloud.app.fetch_file_list_from_worker_plan",
            new=AsyncMock(return_value=[]),
        ), patch(
            "mcp_cloud.app.list_files_from_zip_snapshot",
            return_value=["001-2-plan.txt", "log.txt"],
        ), patch(
            "mcp_cloud.app.list_files_from_local_run_dir",
            return_value=None,
        ):
            result = asyncio.run(handle_task_status({"task_id": task_id}))

        files = result.structuredContent["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "001-2-plan.txt")

    def test_task_status_uses_processing_state_name(self):
        task_id = str(uuid.uuid4())
        task_snapshot = {
            "id": task_id,
            "state": PlanState.processing,
            "stop_requested": True,
            "progress_percentage": 10.0,
            "timestamp_created": datetime.now(UTC),
        }
        with patch(
            "mcp_cloud.app._get_task_status_snapshot_sync",
            return_value=task_snapshot,
        ), patch(
            "mcp_cloud.app.fetch_file_list_from_worker_plan",
            new=AsyncMock(return_value=[]),
        ):
            result = asyncio.run(handle_task_status({"task_id": task_id}))

        self.assertEqual(result.structuredContent["state"], "processing")

    def test_task_status_returns_task_not_found_error(self):
        task_id = str(uuid.uuid4())
        with patch("mcp_cloud.app._get_task_status_snapshot_sync", return_value=None):
            result = asyncio.run(handle_task_status({"task_id": task_id}))

        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["error"]["code"], "TASK_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
