import io
import importlib.util
import json
import sys
import unittest
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = PROJECT_ROOT / "frontend_multi_user" / "src"
WORKER_PLAN_ROOT = PROJECT_ROOT / "worker_plan"

if str(FRONTEND_SRC) not in sys.path:
    sys.path.insert(0, str(FRONTEND_SRC))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(WORKER_PLAN_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_PLAN_ROOT))

from worker_plan_api.filenames import ExtraFilenameEnum  # noqa: E402


APP_MODULE_PATH = FRONTEND_SRC / "app.py"
APP_IMPORT_ERROR = None
APP_AVAILABLE = False
MyFlaskApp: Any = object
PlanState: Any = SimpleNamespace(processing="processing", completed="completed")
frontend_app_module = None
try:
    APP_SPEC = importlib.util.spec_from_file_location("frontend_multi_user_app", APP_MODULE_PATH)
    if APP_SPEC is None or APP_SPEC.loader is None:
        raise RuntimeError(f"Unable to load app module at {APP_MODULE_PATH}")
    frontend_app_module = importlib.util.module_from_spec(APP_SPEC)
    APP_SPEC.loader.exec_module(frontend_app_module)
    MyFlaskApp = frontend_app_module.MyFlaskApp
    PlanState = frontend_app_module.PlanState
    APP_AVAILABLE = True
except ModuleNotFoundError as exc:
    APP_IMPORT_ERROR = exc


@unittest.skipIf(not APP_AVAILABLE, f"frontend_multi_user app dependencies unavailable: {APP_IMPORT_ERROR}")
class TestPlanTelemetryHelpers(unittest.TestCase):
    class _DummyColumn:
        def asc(self):
            return self

    def setUp(self) -> None:
        self.app_obj = MyFlaskApp.__new__(MyFlaskApp)
        self.app_obj._plan_telemetry_cache = {}

    def _make_zip_snapshot(self, payload: dict) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                f"nested/{ExtraFilenameEnum.ACTIVITY_OVERVIEW_JSON.value}",
                json.dumps(payload),
            )
        buffer.seek(0)
        return buffer.getvalue()

    def _task(
        self,
        task_id: str = "task-1",
        run_zip_snapshot: bytes | None = None,
        run_activity_overview_json: dict | None = None,
        run_artifact_layout_version: int | None = None,
        state=None,
    ):
        if state is None and PlanState is not None:
            state = PlanState.processing
        return SimpleNamespace(
            id=task_id,
            run_zip_snapshot=run_zip_snapshot,
            run_activity_overview_json=run_activity_overview_json,
            run_artifact_layout_version=run_artifact_layout_version,
            state=state,
            generated_report_html=None,
        )

    def _row(self, **overrides):
        defaults = {
            "id": 1,
            "timestamp": datetime.now(UTC),
            "task_id": "task-1",
            "user_id": "user-1",
            "llm_model": "gpt-4o-mini",
            "upstream_provider": None,
            "upstream_model": None,
            "input_tokens": None,
            "output_tokens": None,
            "thinking_tokens": None,
            "cost_usd": None,
            "duration_seconds": 0.1,
            "success": True,
            "error_message": None,
            "raw_usage_data": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _patch_token_metrics_rows(self, rows):
        query = mock.Mock()
        query.filter_by.return_value = query
        query.order_by.return_value = query
        query.all.return_value = rows
        token_metrics_stub = SimpleNamespace(
            query=query,
            timestamp=self._DummyColumn(),
            id=self._DummyColumn(),
        )
        return mock.patch.object(frontend_app_module, "TokenMetrics", token_metrics_stub)

    def test_extract_provider_model_from_activity_key(self) -> None:
        provider, model = MyFlaskApp._extract_provider_model_from_activity_key("OpenRouter:gpt-4o-mini")
        self.assertEqual(provider, "OpenRouter")
        self.assertEqual(model, "gpt-4o-mini")

        provider, model = MyFlaskApp._extract_provider_model_from_activity_key("gpt-4o-mini")
        self.assertIsNone(provider)
        self.assertEqual(model, "gpt-4o-mini")

        provider, model = MyFlaskApp._extract_provider_model_from_activity_key("   ")
        self.assertIsNone(provider)
        self.assertIsNone(model)

    def test_read_activity_overview_from_run_zip(self) -> None:
        expected_payload = {
            "total_cost": 0.123,
            "total_input_tokens": 10,
            "models": {"OpenRouter:gpt-4o-mini": {"calls": 2}},
        }
        snapshot = self._make_zip_snapshot(expected_payload)
        actual_payload = self.app_obj._read_activity_overview_from_run_zip(snapshot)
        self.assertEqual(actual_payload, expected_payload)

    def test_read_inference_cost_from_run_zip(self) -> None:
        snapshot = self._make_zip_snapshot({"total_cost": "0.75"})
        cost = self.app_obj._read_inference_cost_from_run_zip(snapshot)
        self.assertEqual(cost, 0.75)

        invalid_cost = self.app_obj._read_inference_cost_from_run_zip(b"not-a-zip")
        self.assertIsNone(invalid_cost)

    def test_read_activity_overview_prefers_task_column(self) -> None:
        task = self._task(
            run_zip_snapshot=self._make_zip_snapshot({"total_cost": 99.0}),
            run_activity_overview_json={"total_cost": 1.25, "total_input_tokens": 12},
            run_artifact_layout_version=2,
        )
        payload = self.app_obj._read_activity_overview_from_task(task)
        self.assertEqual(payload, {"total_cost": 1.25, "total_input_tokens": 12})

    def test_sanitize_legacy_run_zip_for_download_removes_track_activity(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("report.html", "<html>ok</html>")
            archive.writestr("nested/track_activity.jsonl", "{\"event\":\"secret\"}\n")
        sanitized = self.app_obj._sanitize_legacy_run_zip_for_download(buffer.getvalue())
        self.assertIsNotNone(sanitized)
        assert sanitized is not None
        with zipfile.ZipFile(sanitized, "r") as archive:
            files = sorted(archive.namelist())
        self.assertIn("report.html", files)
        self.assertNotIn("nested/track_activity.jsonl", files)

    def test_build_plan_telemetry_uses_activity_overview_fallback_without_metrics(self) -> None:
        overview = {
            "total_cost": 0.42,
            "total_input_tokens": 12,
            "total_output_tokens": 8,
            "total_thinking_tokens": 4,
            "total_tokens": 24,
            "models": {
                "OpenRouter:gpt-4o-mini": {"calls": 3},
                "gpt-4.1-mini": {"calls": 2},
            },
        }
        task = self._task(run_zip_snapshot=self._make_zip_snapshot(overview))

        with self._patch_token_metrics_rows([]):
            telemetry = self.app_obj._build_plan_telemetry(task, include_raw=False)

        self.assertEqual(telemetry["usage"]["prompt_tokens"], 12)
        self.assertEqual(telemetry["usage"]["completion_tokens"], 8)
        self.assertEqual(telemetry["usage"]["thinking_tokens"], 4)
        self.assertEqual(telemetry["usage"]["total_tokens"], 24)
        self.assertEqual(telemetry["cost"]["token_metrics_usd"], None)
        self.assertEqual(telemetry["cost"]["activity_overview_usd"], 0.42)
        self.assertEqual(telemetry["calls"]["total"], 5)
        self.assertTrue(telemetry["has_data"])
        self.assertEqual(
            telemetry["provider_model"]["providers"],
            ["OpenRouter"],
        )
        self.assertEqual(
            telemetry["provider_model"]["models"],
            ["gpt-4.1-mini", "gpt-4o-mini"],
        )

    def test_build_plan_telemetry_empty_sources_reports_no_data(self) -> None:
        task = self._task(run_zip_snapshot=None)

        with self._patch_token_metrics_rows([]):
            telemetry = self.app_obj._build_plan_telemetry(task, include_raw=False)

        self.assertEqual(telemetry["usage"], {
            "prompt_tokens": None,
            "completion_tokens": None,
            "thinking_tokens": None,
            "total_tokens": None,
        })
        self.assertEqual(telemetry["cost"], {
            "token_metrics_usd": None,
            "activity_overview_usd": None,
            "currency": None,
        })
        self.assertEqual(telemetry["provider_model"]["routes"], [])
        self.assertEqual(telemetry["calls"]["total"], None)
        self.assertEqual(telemetry["source_availability"], {
            "token_metrics_row_count": 0,
            "activity_overview_present": False,
        })
        self.assertFalse(telemetry["has_data"])

    def test_build_plan_telemetry_handles_mixed_null_and_zero_values(self) -> None:
        overview = {
            "total_input_tokens": 7,
            "total_thinking_tokens": 5,
            "total_tokens": 12,
        }
        task = self._task(run_zip_snapshot=self._make_zip_snapshot(overview))
        rows = [
            self._row(id=1, input_tokens=None, output_tokens=0, thinking_tokens=None, cost_usd=0.0, success=True),
            self._row(id=2, input_tokens=None, output_tokens=None, thinking_tokens=None, cost_usd=None, success=False),
        ]

        with self._patch_token_metrics_rows(rows):
            telemetry = self.app_obj._build_plan_telemetry(task, include_raw=False)

        # prompt/thinking fall back to activity_overview because all metric rows are null,
        # while completion stays at metric value zero (valid, not "missing").
        self.assertEqual(telemetry["usage"]["prompt_tokens"], 7)
        self.assertEqual(telemetry["usage"]["completion_tokens"], 0)
        self.assertEqual(telemetry["usage"]["thinking_tokens"], 5)
        # Any metric token presence keeps total based on metric summary.
        self.assertEqual(telemetry["usage"]["total_tokens"], 0)
        self.assertEqual(telemetry["cost"]["token_metrics_usd"], 0.0)
        self.assertEqual(telemetry["calls"], {"total": 2, "successful": 1, "failed": 1})
        self.assertTrue(telemetry["has_data"])

    def test_build_plan_telemetry_caches_terminal_non_raw_results(self) -> None:
        task = self._task(
            task_id="task-cache",
            run_zip_snapshot=self._make_zip_snapshot({"total_input_tokens": 3}),
            state=PlanState.completed,
        )

        with self._patch_token_metrics_rows([]):
            with mock.patch.object(self.app_obj, "_read_activity_overview_from_run_zip", wraps=self.app_obj._read_activity_overview_from_run_zip) as read_zip:
                first = self.app_obj._build_plan_telemetry(task, include_raw=False)
                second = self.app_obj._build_plan_telemetry(task, include_raw=False)

        self.assertIs(first, second)
        self.assertEqual(read_zip.call_count, 1)


if __name__ == "__main__":
    unittest.main()
