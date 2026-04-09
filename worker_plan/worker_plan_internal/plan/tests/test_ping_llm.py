import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMModelWithInstance
from worker_plan_internal.llm_util.response_mockllm import ResponseMockLLM
from worker_plan_internal.plan.ping_llm import run_ping_llm_report


class TestPingLLMReport(unittest.TestCase):
    def test_ping_llm_report_fallback(self):
        with TemporaryDirectory() as temp_dir:
            run_id_dir = Path(temp_dir)
            (run_id_dir / FilenameEnum.START_TIME.value).write_text("{}", encoding="utf-8")
            (run_id_dir / FilenameEnum.INITIAL_PLAN_RAW.value).write_text('{"plan_prompt": "Ping test", "pretty_date": "1984-Apr-09"}', encoding="utf-8")

            bad_llm = ResponseMockLLM(responses=["raise:BAD"])
            good_llm = ResponseMockLLM(responses=["PONG ok"])
            llm_models = LLMModelWithInstance.from_instances([bad_llm, good_llm])

            result = run_ping_llm_report(run_id_dir=run_id_dir, llm_models=llm_models)

            self.assertIsNone(result.error_message)
            self.assertEqual(result.response_text, "PONG ok")
            self.assertEqual(len(result.attempts), 2)
            self.assertFalse(result.attempts[0].success)
            self.assertTrue(result.attempts[1].success)

            report_path = run_id_dir / FilenameEnum.REPORT.value
            self.assertTrue(report_path.exists())
            report_html = report_path.read_text(encoding="utf-8")
            self.assertIn("PONG ok", report_html)

            pipeline_complete_path = run_id_dir / FilenameEnum.PIPELINE_COMPLETE.value
            self.assertTrue(pipeline_complete_path.exists())


if __name__ == "__main__":
    unittest.main()
