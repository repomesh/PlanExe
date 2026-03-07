import unittest

from mcp_cloud.http_utils import strip_redundant_content


class TestHttpUtils(unittest.TestCase):
    def test_strip_redundant_content_only_when_structured_present(self):
        payload = {"content": [{"text": "hi"}]}
        stripped, changed = strip_redundant_content(payload)
        self.assertFalse(changed)
        self.assertEqual(stripped, payload)

    def test_strip_redundant_content_removes_content(self):
        payload = {"content": [{"text": "hi"}], "structuredContent": {"result": []}}
        stripped, changed = strip_redundant_content(payload)
        self.assertTrue(changed)
        self.assertNotIn("content", stripped)
        self.assertIn("structuredContent", stripped)

    def test_strip_redundant_content_non_dict(self):
        payload = ["content"]
        stripped, changed = strip_redundant_content(payload)
        self.assertFalse(changed)
        self.assertEqual(stripped, payload)

    def test_strip_redundant_content_skips_jsonrpc_payload(self):
        """JSON-RPC envelopes must never be stripped — the MCP protocol owns them."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "hi"}],
                "structuredContent": {"ready": False, "reason": "processing"},
            },
            "content": [{"type": "text", "text": "hi"}],
            "structuredContent": {"ready": False, "reason": "processing"},
        }
        stripped, changed = strip_redundant_content(payload)
        self.assertFalse(changed)
        self.assertIn("content", stripped)
        self.assertIn("structuredContent", stripped)

    def test_strip_skips_jsonrpc_error_response(self):
        """JSON-RPC error responses with content keys must not be stripped."""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32001, "message": "auth failed"},
            "content": [{"type": "text", "text": "error"}],
            "structuredContent": {"error": {"code": "PLAN_NOT_FOUND"}},
        }
        stripped, changed = strip_redundant_content(payload)
        self.assertFalse(changed)
        self.assertEqual(stripped, payload)

    def test_strip_skips_jsonrpc_with_only_content_no_structured(self):
        """JSON-RPC with content but no structuredContent should still be skipped."""
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {},
            "content": [{"type": "text", "text": "hi"}],
        }
        stripped, changed = strip_redundant_content(payload)
        self.assertFalse(changed)
        self.assertIn("content", stripped)

    def test_strip_skips_jsonrpc_notification(self):
        """JSON-RPC notifications (no id) must also be guarded."""
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "content": [{"type": "text", "text": "x"}],
            "structuredContent": {"data": 1},
        }
        stripped, changed = strip_redundant_content(payload)
        self.assertFalse(changed)

    def test_strip_still_works_for_non_jsonrpc_dict(self):
        """Non-JSON-RPC dicts with both keys must still be stripped."""
        payload = {
            "content": [{"type": "text", "text": "hi"}],
            "structuredContent": {"ready": False, "reason": "processing"},
        }
        stripped, changed = strip_redundant_content(payload)
        self.assertTrue(changed)
        self.assertNotIn("content", stripped)
        self.assertIn("structuredContent", stripped)

    def test_strip_preserves_structuredContent_value(self):
        """After stripping, structuredContent value must be unchanged."""
        sc = {"ready": False, "reason": "processing"}
        payload = {
            "content": [{"type": "text", "text": "{}"}],
            "structuredContent": sc,
            "isError": False,
        }
        stripped, changed = strip_redundant_content(payload)
        self.assertTrue(changed)
        self.assertEqual(stripped["structuredContent"], sc)
        self.assertIn("isError", stripped)

if __name__ == "__main__":
    unittest.main()
