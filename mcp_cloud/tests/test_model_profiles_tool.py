import asyncio
import unittest
from unittest.mock import patch

from mcp_cloud.app import handle_list_tools, handle_model_profiles


class TestModelProfilesTool(unittest.TestCase):
    def test_model_profiles_tool_listed(self):
        tools = asyncio.run(handle_list_tools())
        tool_names = {tool.name for tool in tools}
        self.assertIn("model_profiles", tool_names)

    def test_model_profiles_returns_structured_content(self):
        payload = {
            "default_profile": "baseline",
            "profiles": [
                {
                    "profile": "baseline",
                    "title": "Baseline",
                    "summary": "Cheap and fast; recommended default for most runs.",
                    "available": True,
                    "model_count": 1,
                    "models": [
                        {
                            "key": "openrouter-gpt-oss-20b",
                            "provider_class": "OpenRouter",
                            "model": "openai/gpt-oss-20b",
                            "priority": 0,
                        }
                    ],
                }
            ],
            "message": "Use one of these profile values in task_create.model_profile.",
        }

        with patch("mcp_cloud.app._get_model_profiles_sync", return_value=payload):
            result = asyncio.run(handle_model_profiles({}))

        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["default_profile"], "baseline")
        self.assertEqual(result.structuredContent["profiles"][0]["profile"], "baseline")


if __name__ == "__main__":
    unittest.main()
