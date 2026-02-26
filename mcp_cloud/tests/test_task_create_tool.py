import asyncio
import unittest
import uuid
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from mcp.types import CallToolResult
from mcp_cloud.app import handle_list_tools, handle_plan_create


class TestPlanCreateTool(unittest.TestCase):
    def test_plan_create_visible_schema_exposes_prompt_and_model_profile(self):
        tools = asyncio.run(handle_list_tools())
        plan_create_tool = next(tool for tool in tools if tool.name == "plan_create")
        properties = plan_create_tool.inputSchema.get("properties", {})
        self.assertIn("prompt", properties)
        self.assertIn("model_profile", properties)

    def test_plan_create_returns_structured_content(self):
        arguments = {"prompt": "xcv", "config": None, "metadata": None}
        fake_session = MagicMock()
        class StubPlanItem:
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
            "mcp_cloud.app.PlanItem", StubPlanItem
        ):
            result = asyncio.run(handle_plan_create(arguments))

        self.assertIsInstance(result, CallToolResult)
        self.assertIsInstance(result.structuredContent, dict)
        self.assertIn("task_id", result.structuredContent)
        self.assertIn("created_at", result.structuredContent)
        self.assertIsInstance(uuid.UUID(result.structuredContent["task_id"]), uuid.UUID)


if __name__ == "__main__":
    unittest.main()
