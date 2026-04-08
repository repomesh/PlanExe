# worker_plan/worker_plan_internal/rca/tests/test_output.py
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from worker_plan_internal.rca.tracer import (
    RCAResult,
    TracedProblem,
    TraceEntry,
    OriginInfo,
)
from worker_plan_internal.rca.output import write_json_report, write_markdown_report


def _make_sample_result() -> RCAResult:
    """Create a sample RCAResult for testing."""
    return RCAResult(
        starting_file="025-2-executive_summary.md",
        problem_description="Budget is unvalidated",
        output_dir="/tmp/test_output",
        problems=[
            TracedProblem(
                id="problem_001",
                description="Budget of CZK 500,000 is unvalidated",
                severity="HIGH",
                starting_evidence="CZK 500,000",
                trace=[
                    TraceEntry(node="executive_summary", file="025-2-executive_summary.md", evidence="CZK 500,000", is_origin=False),
                    TraceEntry(node="project_plan", file="005-2-project_plan.md", evidence="Budget: 500k", is_origin=False),
                    TraceEntry(node="make_assumptions", file="003-5-make_assumptions.md", evidence="Assume budget of 500k", is_origin=True),
                ],
                origin_node="make_assumptions",
                origin=OriginInfo(
                    node="make_assumptions",
                    file="003-5-make_assumptions.md",
                    source_code_files=["make_assumptions.py"],
                    category="prompt_fixable",
                    likely_cause="Prompt generates budget without data",
                    suggestion="Add validation step",
                ),
                depth=3,
            ),
            TracedProblem(
                id="problem_002",
                description="Missing market sizing",
                severity="MEDIUM",
                starting_evidence="growing Czech market",
                trace=[
                    TraceEntry(node="executive_summary", file="025-2-executive_summary.md", evidence="growing Czech market", is_origin=True),
                ],
                origin_node="executive_summary",
                depth=1,
            ),
        ],
        llm_calls_made=8,
    )


class TestWriteJsonReport(unittest.TestCase):
    def test_writes_valid_json(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.json"
            result = _make_sample_result()
            write_json_report(result, output_path)

            self.assertTrue(output_path.exists())
            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("input", data)
            self.assertIn("problems", data)
            self.assertIn("summary", data)

    def test_json_contains_correct_summary(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.json"
            result = _make_sample_result()
            write_json_report(result, output_path)

            data = json.loads(output_path.read_text(encoding="utf-8"))
            summary = data["summary"]
            self.assertEqual(summary["total_problems"], 2)
            self.assertEqual(summary["deepest_origin_node"], "make_assumptions")
            self.assertEqual(summary["deepest_origin_depth"], 3)
            self.assertEqual(summary["llm_calls_made"], 8)

    def test_json_problems_sorted_by_depth(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.json"
            result = _make_sample_result()
            write_json_report(result, output_path)

            data = json.loads(output_path.read_text(encoding="utf-8"))
            depths = [f["depth"] for f in data["problems"]]
            self.assertEqual(depths, sorted(depths, reverse=True))


class TestWriteMarkdownReport(unittest.TestCase):
    def test_writes_markdown_file(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.md"
            result = _make_sample_result()
            write_markdown_report(result, output_path)

            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("# Root Cause Analysis Report", content)

    def test_markdown_contains_problem_details(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.md"
            result = _make_sample_result()
            write_markdown_report(result, output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Budget of CZK 500,000 is unvalidated", content)
            self.assertIn("make_assumptions", content)
            self.assertIn("executive_summary", content)

    def test_markdown_contains_trace_table(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.md"
            result = _make_sample_result()
            write_markdown_report(result, output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("| Node |", content)
            self.assertIn("| File |", content)

    def test_empty_result_produces_valid_markdown(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "root_cause_analysis.md"
            result = RCAResult(
                starting_file="030-report.html",
                problem_description="test",
                output_dir="/tmp",
                problems=[],
                llm_calls_made=1,
            )
            write_markdown_report(result, output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Problems found:** 0", content)
