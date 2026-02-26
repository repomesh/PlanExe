"""Tests for startup secret validation (4.1 fail-hard on missing secrets)."""
import unittest
from unittest.mock import patch

from mcp_cloud.auth import validate_api_key_secret
from mcp_cloud.download_tokens import validate_download_token_secret


class TestValidateApiKeySecret(unittest.TestCase):
    def test_raises_when_not_set(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                validate_api_key_secret()
            self.assertIn("PLANEXE_API_KEY_SECRET", str(ctx.exception))

    def test_passes_when_set(self):
        with patch.dict("os.environ", {"PLANEXE_API_KEY_SECRET": "my-secret"}):
            validate_api_key_secret()  # should not raise


class TestValidateDownloadTokenSecret(unittest.TestCase):
    def test_raises_when_neither_set(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                validate_download_token_secret()
            self.assertIn("PLANEXE_DOWNLOAD_TOKEN_SECRET", str(ctx.exception))

    def test_passes_with_download_token_secret(self):
        with patch.dict("os.environ", {"PLANEXE_DOWNLOAD_TOKEN_SECRET": "tok-secret"}, clear=True):
            validate_download_token_secret()

    def test_passes_with_api_key_secret(self):
        with patch.dict("os.environ", {"PLANEXE_API_KEY_SECRET": "api-secret"}, clear=True):
            validate_download_token_secret()


if __name__ == "__main__":
    unittest.main()
