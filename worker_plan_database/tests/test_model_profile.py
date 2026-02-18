import unittest

from worker_plan_database.model_profile import resolve_model_profile
from worker_plan_api.model_profile import ModelProfileEnum


class TestModelProfile(unittest.TestCase):
    def test_default_baseline(self):
        self.assertEqual(resolve_model_profile(None), ModelProfileEnum.BASELINE)

    def test_accepts_model_profile(self):
        self.assertEqual(resolve_model_profile({"model_profile": "premium"}), ModelProfileEnum.PREMIUM)

    def test_accepts_legacy_llm_profile(self):
        self.assertEqual(resolve_model_profile({"llm_profile": "frontier"}), ModelProfileEnum.FRONTIER)

    def test_invalid_falls_back_to_baseline(self):
        self.assertEqual(resolve_model_profile({"model_profile": "unknown"}), ModelProfileEnum.BASELINE)


if __name__ == "__main__":
    unittest.main()
