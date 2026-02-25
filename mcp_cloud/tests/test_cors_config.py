import unittest
from unittest.mock import patch

import mcp_cloud.http_server as http_server


class _RequestStub:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class _ResponseStub:
    def __init__(self):
        self.headers: dict[str, str] = {}


class TestCorsEnvParsing(unittest.TestCase):
    def test_split_csv_env_strips_quotes(self):
        parsed = http_server._split_csv_env('"https://a.example.com", "https://b.example.com"')
        self.assertEqual(parsed, ["https://a.example.com", "https://b.example.com"])

    def test_split_csv_env_parses_json_array(self):
        parsed = http_server._split_csv_env('["https://a.example.com", "https://b.example.com"]')
        self.assertEqual(parsed, ["https://a.example.com", "https://b.example.com"])

    def test_split_csv_env_empty(self):
        self.assertEqual(http_server._split_csv_env(""), [])


class TestCorsHeaderAppending(unittest.TestCase):
    def test_append_cors_headers_with_wildcard(self):
        request = _RequestStub(headers={"origin": "http://localhost:6274"})
        response = _ResponseStub()
        with patch.object(http_server, "CORS_ORIGINS", ["*"]):
            updated = http_server._append_cors_headers(request, response)
        self.assertEqual(updated.headers.get("Access-Control-Allow-Origin"), "*")

    def test_append_cors_headers_with_allowed_specific_origin(self):
        origin = "http://localhost:6274"
        request = _RequestStub(
            headers={
                "origin": origin,
                "access-control-request-headers": "x-api-key,content-type",
            }
        )
        response = _ResponseStub()
        with patch.object(http_server, "CORS_ORIGINS", [origin]):
            updated = http_server._append_cors_headers(request, response)
        self.assertEqual(updated.headers.get("Access-Control-Allow-Origin"), origin)
        self.assertEqual(
            updated.headers.get("Access-Control-Allow-Headers"),
            "x-api-key,content-type",
        )
        self.assertEqual(updated.headers.get("Vary"), "Origin")

    def test_append_cors_headers_not_added_for_disallowed_origin(self):
        request = _RequestStub(headers={"origin": "https://unknown.example.com"})
        response = _ResponseStub()
        with patch.object(http_server, "CORS_ORIGINS", ["https://allowed.example.com"]):
            updated = http_server._append_cors_headers(request, response)
        self.assertNotIn("Access-Control-Allow-Origin", updated.headers)


if __name__ == "__main__":
    unittest.main()
