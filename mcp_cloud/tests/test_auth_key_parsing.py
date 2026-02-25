import unittest

import mcp_cloud.http_server as http_server


class _RequestStub:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class TestNormalizeApiKeyValue(unittest.TestCase):
    def test_plain_key_unchanged(self):
        self.assertEqual(http_server._normalize_api_key_value("pex_abc123"), "pex_abc123")

    def test_strips_whitespace(self):
        self.assertEqual(http_server._normalize_api_key_value("  pex_abc123  "), "pex_abc123")

    def test_bearer_prefix(self):
        self.assertEqual(http_server._normalize_api_key_value("Bearer pex_abc123"), "pex_abc123")

    def test_bearer_prefix_case_insensitive(self):
        self.assertEqual(http_server._normalize_api_key_value("BEARER pex_abc123"), "pex_abc123")

    def test_token_prefix(self):
        self.assertEqual(http_server._normalize_api_key_value("token pex_abc123"), "pex_abc123")

    def test_x_api_key_header_prefix(self):
        self.assertEqual(http_server._normalize_api_key_value("X-API-Key: pex_abc123"), "pex_abc123")

    def test_api_key_header_prefix(self):
        self.assertEqual(http_server._normalize_api_key_value("api-key: pex_abc123"), "pex_abc123")

    def test_authorization_header_prefix(self):
        self.assertEqual(http_server._normalize_api_key_value("Authorization: pex_abc123"), "pex_abc123")

    def test_double_quoted_key(self):
        self.assertEqual(http_server._normalize_api_key_value('"pex_abc123"'), "pex_abc123")

    def test_single_quoted_key(self):
        self.assertEqual(http_server._normalize_api_key_value("'pex_abc123'"), "pex_abc123")

    def test_none_returns_none(self):
        self.assertIsNone(http_server._normalize_api_key_value(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(http_server._normalize_api_key_value(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(http_server._normalize_api_key_value("   "))


class TestExtractApiKey(unittest.TestCase):
    def test_authorization_bearer(self):
        request = _RequestStub(headers={"Authorization": "Bearer pex_from_auth"})
        self.assertEqual(http_server._extract_api_key(request), "pex_from_auth")

    def test_x_api_key(self):
        request = _RequestStub(headers={"X-API-Key": "pex_from_x_header"})
        self.assertEqual(http_server._extract_api_key(request), "pex_from_x_header")

    def test_api_key_header(self):
        request = _RequestStub(headers={"API-Key": "pex_from_api_key_header"})
        self.assertEqual(http_server._extract_api_key(request), "pex_from_api_key_header")

    def test_x_api_key_with_pasted_prefix(self):
        # User accidentally pastes the full header line as the value.
        request = _RequestStub(headers={"X-API-Key": "X-API-Key: pex_from_x_header"})
        self.assertEqual(http_server._extract_api_key(request), "pex_from_x_header")

    def test_authorization_with_pasted_bearer(self):
        request = _RequestStub(headers={"Authorization": "Bearer pex_bearer_key"})
        self.assertEqual(http_server._extract_api_key(request), "pex_bearer_key")

    def test_no_headers_returns_none(self):
        request = _RequestStub(headers={})
        self.assertIsNone(http_server._extract_api_key(request))

    def test_empty_authorization_returns_none(self):
        request = _RequestStub(headers={"Authorization": ""})
        self.assertIsNone(http_server._extract_api_key(request))

    def test_authorization_takes_priority_over_x_api_key(self):
        request = _RequestStub(headers={
            "Authorization": "Bearer pex_from_auth",
            "X-API-Key": "pex_from_x_header",
        })
        self.assertEqual(http_server._extract_api_key(request), "pex_from_auth")


if __name__ == "__main__":
    unittest.main()
