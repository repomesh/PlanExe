import asyncio
import unittest
from unittest.mock import MagicMock, patch

import mcp_cloud.http_server as http_server
import mcp_cloud.server_boot as server_boot


def _fake_request(path: str, client_host: str = "10.0.0.1") -> MagicMock:
    request = MagicMock()
    request.url.path = path
    request.headers = {}
    request.client.host = client_host
    return request


class TestDownloadRateLimit(unittest.TestCase):
    def setUp(self):
        """Clear download rate buckets between tests."""
        http_server._download_rate_buckets.clear()

    def test_non_download_path_is_not_rate_limited(self):
        request = _fake_request("/mcp/tools/call")
        result = asyncio.run(http_server._enforce_download_rate_limit(request))
        self.assertIsNone(result)

    def test_download_path_is_rate_limited(self):
        request = _fake_request("/download/abc-123/report.html")
        for _ in range(http_server.DOWNLOAD_RATE_LIMIT_REQUESTS):
            result = asyncio.run(http_server._enforce_download_rate_limit(request))
            self.assertIsNone(result)
        # Next request should be rejected
        result = asyncio.run(http_server._enforce_download_rate_limit(request))
        self.assertIsNotNone(result)
        self.assertEqual(result.status_code, 429)

    def test_different_clients_have_separate_buckets(self):
        req_a = _fake_request("/download/abc/report.html", client_host="10.0.0.1")
        req_b = _fake_request("/download/abc/report.html", client_host="10.0.0.2")
        for _ in range(http_server.DOWNLOAD_RATE_LIMIT_REQUESTS):
            asyncio.run(http_server._enforce_download_rate_limit(req_a))
        # Client A is exhausted
        result_a = asyncio.run(http_server._enforce_download_rate_limit(req_a))
        self.assertIsNotNone(result_a)
        # Client B still has quota
        result_b = asyncio.run(http_server._enforce_download_rate_limit(req_b))
        self.assertIsNone(result_b)

    def test_disabled_when_limit_is_zero(self):
        request = _fake_request("/download/abc/report.html")
        original = server_boot.DOWNLOAD_RATE_LIMIT_REQUESTS
        try:
            server_boot.DOWNLOAD_RATE_LIMIT_REQUESTS = 0
            result = asyncio.run(http_server._enforce_download_rate_limit(request))
            self.assertIsNone(result)
        finally:
            server_boot.DOWNLOAD_RATE_LIMIT_REQUESTS = original


if __name__ == "__main__":
    unittest.main()
