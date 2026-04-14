import time
import unittest
from unittest.mock import patch

import mcp_cloud.app as cloud_app
import mcp_cloud.download_tokens as _dt_mod


class TestGenerateAndValidateDownloadToken(unittest.TestCase):
    def setUp(self):
        # Pin the secret so tests are deterministic regardless of env vars.
        self._secret_patch = patch.object(
            _dt_mod,
            "_get_download_token_secret",
            return_value=b"test-secret-for-unit-tests",
        )
        self._secret_patch.start()

    def tearDown(self):
        self._secret_patch.stop()

    def test_valid_token_accepted(self):
        token = cloud_app.generate_download_token("task-abc", "report.html")
        self.assertTrue(cloud_app.validate_download_token(token, "task-abc", "report.html"))

    def test_wrong_plan_id_rejected(self):
        token = cloud_app.generate_download_token("task-abc", "report.html")
        self.assertFalse(cloud_app.validate_download_token(token, "task-xyz", "report.html"))

    def test_wrong_filename_rejected(self):
        token = cloud_app.generate_download_token("task-abc", "report.html")
        self.assertFalse(cloud_app.validate_download_token(token, "task-abc", "run.zip"))

    def test_tampered_mac_rejected(self):
        token = cloud_app.generate_download_token("task-abc", "report.html")
        expiry, _ = token.split(".", 1)
        tampered = f"{expiry}.{'0' * 64}"
        self.assertFalse(cloud_app.validate_download_token(tampered, "task-abc", "report.html"))

    def test_expired_token_rejected(self):
        # Generate a token that expired 1 second ago.
        past_expiry = int(time.time()) - 1
        import hashlib, hmac
        message = f"task-abc:report.html:{past_expiry}".encode()
        mac = hmac.new(b"test-secret-for-unit-tests", message, hashlib.sha256).hexdigest()
        expired_token = f"{past_expiry}.{mac}"
        self.assertFalse(cloud_app.validate_download_token(expired_token, "task-abc", "report.html"))

    def test_malformed_token_rejected(self):
        for bad in ("", "nodot", "abc.def.extra", "notanint.abc"):
            with self.subTest(token=bad):
                self.assertFalse(cloud_app.validate_download_token(bad, "task-abc", "report.html"))

    def test_token_contains_expiry_and_mac(self):
        token = cloud_app.generate_download_token("task-abc", "report.html")
        parts = token.split(".")
        self.assertEqual(len(parts), 2)
        expiry_str, mac = parts
        self.assertTrue(expiry_str.isdigit())
        self.assertEqual(len(mac), 64)  # SHA-256 hex = 64 chars

    def test_expiry_is_in_the_future(self):
        token = cloud_app.generate_download_token("task-abc", "report.html")
        expiry = int(token.split(".")[0])
        self.assertGreater(expiry, int(time.time()))

    def test_different_tasks_get_different_tokens(self):
        t1 = cloud_app.generate_download_token("task-aaa", "report.html")
        t2 = cloud_app.generate_download_token("task-bbb", "report.html")
        self.assertNotEqual(t1, t2)

    def test_report_url_contains_token(self):
        with patch.object(_dt_mod, "_get_download_base_url", return_value="https://example.com"):
            url = cloud_app.build_report_download_url("task-abc")
        self.assertIsNotNone(url)
        self.assertIn("?token=", url)
        self.assertIn("/download/task-abc/report.html", url)

    def test_zip_url_contains_token(self):
        with patch.object(_dt_mod, "_get_download_base_url", return_value="https://example.com"):
            url = cloud_app.build_zip_download_url("task-abc")
        self.assertIsNotNone(url)
        self.assertIn("?token=", url)
        self.assertIn("/download/task-abc/run.zip", url)

    def test_token_embedded_in_report_url_is_valid(self):
        with patch.object(_dt_mod, "_get_download_base_url", return_value="https://example.com"):
            url = cloud_app.build_report_download_url("task-abc")
        token = url.split("?token=")[1]
        self.assertTrue(cloud_app.validate_download_token(token, "task-abc", "report.html"))

    def test_token_embedded_in_zip_url_is_valid(self):
        with patch.object(_dt_mod, "_get_download_base_url", return_value="https://example.com"):
            url = cloud_app.build_zip_download_url("task-abc")
        token = url.split("?token=")[1]
        self.assertTrue(cloud_app.validate_download_token(token, "task-abc", "run.zip"))


if __name__ == "__main__":
    unittest.main()
