"""Tests for the report fallback chain in fetch_artifact_from_worker_plan."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from mcp_cloud.db_setup import REPORT_FILENAME
from mcp_cloud.worker_fetchers import fetch_artifact_from_worker_plan


class TestReportFallbackChain(unittest.TestCase):
    """Verify the DB-first fallback order: DB → zip → HTTP."""

    def _run(self, coro):
        return asyncio.run(coro)

    @patch("mcp_cloud.worker_fetchers.httpx.AsyncClient")
    @patch("mcp_cloud.worker_fetchers.fetch_file_from_zip_snapshot")
    @patch("mcp_cloud.worker_fetchers.fetch_report_from_db")
    def test_db_returns_report_no_other_fallbacks(
        self, mock_db, mock_zip, mock_client_cls
    ):
        """DB returns report → HTTP and zip not called."""
        mock_db.return_value = b"<html>from-db</html>"

        result = self._run(fetch_artifact_from_worker_plan("run-1", REPORT_FILENAME))

        self.assertEqual(result, b"<html>from-db</html>")
        mock_db.assert_called_once_with("run-1")
        mock_zip.assert_not_called()
        mock_client_cls.assert_not_called()

    @patch("mcp_cloud.worker_fetchers.httpx.AsyncClient")
    @patch("mcp_cloud.worker_fetchers.fetch_file_from_zip_snapshot")
    @patch("mcp_cloud.worker_fetchers.fetch_report_from_db")
    def test_db_empty_zip_returns_report_no_http(
        self, mock_db, mock_zip, mock_client_cls
    ):
        """DB empty, zip returns report → HTTP not called."""
        mock_db.return_value = None
        mock_zip.return_value = b"<html>from-zip</html>"

        result = self._run(fetch_artifact_from_worker_plan("run-2", REPORT_FILENAME))

        self.assertEqual(result, b"<html>from-zip</html>")
        mock_db.assert_called_once_with("run-2")
        mock_zip.assert_called_once_with("run-2", REPORT_FILENAME)
        mock_client_cls.assert_not_called()

    @patch("mcp_cloud.worker_fetchers.fetch_file_from_zip_snapshot")
    @patch("mcp_cloud.worker_fetchers.fetch_report_from_db")
    @patch("mcp_cloud.worker_fetchers.httpx.AsyncClient")
    def test_db_empty_zip_empty_http_200_returns_report(
        self, mock_client_cls, mock_db, mock_zip
    ):
        """DB empty, zip empty, HTTP returns 200 → report from HTTP."""
        mock_db.return_value = None
        mock_zip.return_value = None

        response = MagicMock()
        response.status_code = 200
        response.content = b"<html>from-http</html>"

        client = AsyncMock()
        client.get.return_value = response
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = client

        result = self._run(fetch_artifact_from_worker_plan("run-3", REPORT_FILENAME))

        self.assertEqual(result, b"<html>from-http</html>")
        mock_db.assert_called_once_with("run-3")
        mock_zip.assert_called_once_with("run-3", REPORT_FILENAME)

    @patch("mcp_cloud.worker_fetchers.fetch_file_from_zip_snapshot")
    @patch("mcp_cloud.worker_fetchers.fetch_report_from_db")
    @patch("mcp_cloud.worker_fetchers.httpx.AsyncClient")
    def test_all_fallbacks_fail_returns_none(
        self, mock_client_cls, mock_db, mock_zip
    ):
        """DB empty, zip empty, HTTP fails → returns None."""
        mock_db.return_value = None
        mock_zip.return_value = None

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = client

        result = self._run(fetch_artifact_from_worker_plan("run-4", REPORT_FILENAME))

        self.assertIsNone(result)
        mock_db.assert_called_once()
        mock_zip.assert_called_once()

    @patch("mcp_cloud.worker_fetchers.httpx.AsyncClient")
    @patch("mcp_cloud.worker_fetchers.fetch_file_from_zip_snapshot")
    @patch("mcp_cloud.worker_fetchers.fetch_report_from_db")
    def test_db_throws_zip_returns_report_no_http(
        self, mock_db, mock_zip, mock_client_cls
    ):
        """DB throws, zip returns report → HTTP not called."""
        mock_db.side_effect = RuntimeError("DB connection lost")
        mock_zip.return_value = b"<html>from-zip</html>"

        result = self._run(fetch_artifact_from_worker_plan("run-5", REPORT_FILENAME))

        self.assertEqual(result, b"<html>from-zip</html>")
        mock_db.assert_called_once_with("run-5")
        mock_zip.assert_called_once_with("run-5", REPORT_FILENAME)
        mock_client_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
