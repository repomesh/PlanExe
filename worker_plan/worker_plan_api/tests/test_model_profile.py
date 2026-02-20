import os
import unittest

from worker_plan_api.model_profile import (
    ModelProfileEnum,
    is_valid_llm_config_filename,
    normalize_model_profile,
    resolve_llm_config_filename,
)


class TestModelProfile(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_model_profile("premium"), ModelProfileEnum.PREMIUM)
        self.assertEqual(normalize_model_profile(" invalid "), ModelProfileEnum.BASELINE)

    def test_filename_validation(self):
        self.assertTrue(is_valid_llm_config_filename("llm_config.baseline.json"))
        self.assertTrue(is_valid_llm_config_filename("llm_config.premium.json"))
        self.assertTrue(is_valid_llm_config_filename("llm_config.hello_world.json"))
        self.assertTrue(is_valid_llm_config_filename("llm_config.123.json"))
        self.assertTrue(is_valid_llm_config_filename("llm_config.1234.json"))

        self.assertFalse(is_valid_llm_config_filename("llm_config.hello-world.json"))
        self.assertFalse(is_valid_llm_config_filename("llm_config..json"))
        self.assertFalse(is_valid_llm_config_filename("llm_config...json"))
        self.assertFalse(is_valid_llm_config_filename("llm_config.1.json"))
        self.assertFalse(is_valid_llm_config_filename("llm_config.12.json"))

        self.assertFalse(is_valid_llm_config_filename("../llm_config.baseline.json"))
        self.assertFalse(is_valid_llm_config_filename("/tmp/llm_config.baseline.json"))

    def test_resolve_custom_invalid_fallback(self):
        old_custom = os.environ.get("PLANEXE_LLM_CONFIG_CUSTOM_FILENAME")
        try:
            os.environ["PLANEXE_LLM_CONFIG_CUSTOM_FILENAME"] = "../bad.json"
            result = resolve_llm_config_filename(model_profile=ModelProfileEnum.CUSTOM)
            self.assertEqual(result, "llm_config.baseline.json")
        finally:
            if old_custom is None:
                os.environ.pop("PLANEXE_LLM_CONFIG_CUSTOM_FILENAME", None)
            else:
                os.environ["PLANEXE_LLM_CONFIG_CUSTOM_FILENAME"] = old_custom


if __name__ == "__main__":
    unittest.main()
