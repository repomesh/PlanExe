import unittest

from pydantic import ValidationError

from mcp_cloud.app import (
    SPEED_VS_DETAIL_DEFAULT,
    TaskCreateRequest,
    _extract_task_create_metadata_overrides,
    _merge_task_create_config,
    resolve_speed_vs_detail,
)


class TestResolveSpeedVsDetail(unittest.TestCase):
    def test_default(self):
        self.assertEqual(resolve_speed_vs_detail(None), SPEED_VS_DETAIL_DEFAULT)

    def test_fast_alias(self):
        self.assertEqual(resolve_speed_vs_detail({"speed_vs_detail": "fast"}), "fast_but_skip_details")

    def test_all_alias(self):
        self.assertEqual(resolve_speed_vs_detail({"speed": "all"}), "all_details_but_slow")

    def test_ping_alias(self):
        self.assertEqual(resolve_speed_vs_detail({"speed_vs_detail": "ping"}), "ping_llm")

    def test_passthrough(self):
        self.assertEqual(resolve_speed_vs_detail({"speed_vs_detail": "ping_llm"}), "ping_llm")

    def test_merge_task_create_config_injects_speed(self):
        merged = _merge_task_create_config(None, "fast", "premium")
        self.assertEqual(merged, {"speed_vs_detail": "fast", "model_profile": "premium"})

    def test_merge_task_create_config_preserves_existing(self):
        merged = _merge_task_create_config({"speed_vs_detail": "all_details_but_slow", "model_profile": "frontier"}, "fast", "premium")
        self.assertEqual(merged, {"speed_vs_detail": "all_details_but_slow", "model_profile": "frontier"})

    def test_merge_task_create_config_ignores_blank(self):
        merged = _merge_task_create_config({}, "   ", "   ")
        self.assertIsNone(merged)


class TestTaskCreateRequest(unittest.TestCase):
    def test_model_profile_accepts_enum(self):
        for value in ("baseline", "premium", "frontier", "custom"):
            req = TaskCreateRequest(prompt="demo", model_profile=value)
            self.assertEqual(req.model_profile, value)

    def test_model_profile_rejects_invalid(self):
        with self.assertRaises(ValidationError):
            TaskCreateRequest(prompt="demo", model_profile="enterprise")


class TestTaskCreateMetadataOverrides(unittest.TestCase):
    def test_extracts_nested_task_create_metadata(self):
        overrides = _extract_task_create_metadata_overrides(
            {"metadata": {"task_create": {"speed_vs_detail": "fast"}}}
        )
        self.assertEqual(overrides.get("speed_vs_detail"), "fast")

    def test_extracts_top_level_metadata(self):
        overrides = _extract_task_create_metadata_overrides(
            {"_meta": {"speed": "all", "model_profile": "premium"}}
        )
        self.assertEqual(overrides.get("speed"), "all")
        self.assertEqual(overrides.get("model_profile"), "premium")

    def test_nested_namespace_overrides_top_level(self):
        overrides = _extract_task_create_metadata_overrides(
            {
                "metadata": {
                    "speed_vs_detail": "fast",
                    "task_create": {"speed_vs_detail": "ping"},
                }
            }
        )
        self.assertEqual(overrides.get("speed_vs_detail"), "ping")


if __name__ == "__main__":
    unittest.main()
