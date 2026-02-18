import io
import importlib.util
import json
import sys
import unittest
import zipfile
from pathlib import Path


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
MyFlaskApp = None
try:
    APP_SPEC = importlib.util.spec_from_file_location("frontend_multi_user_app", APP_MODULE_PATH)
    if APP_SPEC is None or APP_SPEC.loader is None:
        raise RuntimeError(f"Unable to load app module at {APP_MODULE_PATH}")
    frontend_app_module = importlib.util.module_from_spec(APP_SPEC)
    APP_SPEC.loader.exec_module(frontend_app_module)
    MyFlaskApp = frontend_app_module.MyFlaskApp
except ModuleNotFoundError as exc:
    APP_IMPORT_ERROR = exc


@unittest.skipIf(MyFlaskApp is None, f"frontend_multi_user app dependencies unavailable: {APP_IMPORT_ERROR}")
class TestPlanFailureTraceHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.app_obj = MyFlaskApp.__new__(MyFlaskApp)

    def _make_zip_snapshot(self, payload: dict) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                f"nested/{ExtraFilenameEnum.ACTIVITY_OVERVIEW_JSON.value}",
                json.dumps(payload),
            )
        buffer.seek(0)
        return buffer.getvalue()

    def test_extract_exception_type(self) -> None:
        self.assertEqual(MyFlaskApp._extract_exception_type("ValueError: bad value"), "ValueError")
        self.assertEqual(MyFlaskApp._extract_exception_type("httpx.ConnectError while calling endpoint"), "httpx.ConnectError")
        self.assertIsNone(MyFlaskApp._extract_exception_type("just a plain failure message"))

    def test_extract_nested_value(self) -> None:
        payload = {
            "outer": {
                "inner": {
                    "stage": "execute",
                    "error_type": "TimeoutError",
                }
            }
        }
        self.assertEqual(MyFlaskApp._extract_nested_value(payload, {"stage"}), "execute")
        self.assertEqual(MyFlaskApp._extract_nested_value(payload, {"error_type"}), "TimeoutError")
        self.assertIsNone(MyFlaskApp._extract_nested_value(payload, {"missing"}))

    def test_extract_provider_model_from_activity_key(self) -> None:
        provider, model = MyFlaskApp._extract_provider_model_from_activity_key("OpenRouter:gpt-4o-mini")
        self.assertEqual(provider, "OpenRouter")
        self.assertEqual(model, "gpt-4o-mini")

        provider, model = MyFlaskApp._extract_provider_model_from_activity_key("gpt-4o-mini")
        self.assertIsNone(provider)
        self.assertEqual(model, "gpt-4o-mini")

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


if __name__ == "__main__":
    unittest.main()
