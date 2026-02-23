import asyncio
import unittest
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from mcp.types import CallToolResult
from mcp_cloud.app import handle_list_tools, handle_task_create


class TestTaskCreateTool(unittest.TestCase):
    def test_task_create_visible_schema_hides_speed_and_exposes_model_profile(self):
        tools = asyncio.run(handle_list_tools())
        task_create_tool = next(tool for tool in tools if tool.name == "task_create")
        properties = task_create_tool.inputSchema.get("properties", {})
        self.assertIn("prompt", properties)
        self.assertIn("model_profile", properties)
        self.assertNotIn("speed_vs_detail", properties)

    def test_task_create_returns_structured_content(self):
        arguments = {"prompt": "xcv", "config": None, "metadata": None}
        fake_session = MagicMock()
        class StubTaskItem:
            def __init__(self, prompt: str, state, user_id: str, parameters):
                self.id = uuid.uuid4()
                self.prompt = prompt
                self.state = state
                self.user_id = user_id
                self.parameters = parameters
                self.timestamp_created = datetime.now(UTC)

        with patch("mcp_cloud.app.app.app_context", return_value=nullcontext()), patch(
            "mcp_cloud.app.db.session", fake_session
        ), patch(
            "mcp_cloud.app.TaskItem", StubTaskItem
        ):
            result = asyncio.run(handle_task_create(arguments))

        self.assertIsInstance(result, CallToolResult)
        self.assertIsInstance(result.structuredContent, dict)
        self.assertIn("task_id", result.structuredContent)
        self.assertIn("created_at", result.structuredContent)
        self.assertIsInstance(uuid.UUID(result.structuredContent["task_id"]), uuid.UUID)

    def test_task_create_uses_hidden_metadata_speed_override(self):
        fake_response = {"task_id": str(uuid.uuid4()), "created_at": "2026-01-01T00:00:00Z"}
        with patch("mcp_cloud.app._create_task_sync", return_value=fake_response) as create_task_sync:
            result = asyncio.run(
                handle_task_create(
                    {
                        "prompt": "demo",
                        "metadata": {"task_create": {"speed_vs_detail": "ping"}},
                    }
                )
            )

        self.assertFalse(result.isError)
        _, merged_config, _ = create_task_sync.call_args.args
        self.assertEqual(merged_config, {"speed_vs_detail": "ping"})


if __name__ == "__main__":
    unittest.main()
