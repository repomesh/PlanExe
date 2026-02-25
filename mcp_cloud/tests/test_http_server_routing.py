import asyncio
import unittest

import mcp_cloud.http_server as http_server


class TestHttpServerRouting(unittest.TestCase):
    def test_mcp_no_trailing_slash_redirects_to_trailing_slash(self):
        response = asyncio.run(http_server.redirect_mcp_no_trailing_slash())
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers.get("location"), "/mcp/")

    def test_options_mcp_returns_ok(self):
        response = asyncio.run(http_server.options_mcp())
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
