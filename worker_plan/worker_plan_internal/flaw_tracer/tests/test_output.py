# worker_plan/worker_plan_internal/flaw_tracer/tests/test_output.py
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from worker_plan_internal.flaw_tracer.tracer import (
    FlawTraceResult,
    TracedFlaw,
    TraceEntry,
    OriginInfo,
)
from worker_plan_internal.flaw_tracer.output import write_json_report, write_markdown_report


def _make_sample_result() -> FlawTraceResult:
    """Create a sample FlawTraceResult for testing."""
    return FlawTraceResult(
        starting_file="025-2-executive_summary.md",
        flaw_description="Budget is unvalidated",
        output_dir="/tmp/test_output",
        flaws=[
            TracedFlaw(
                id="flaw_001",
                description="Budget of CZK 500,000 is unvalidated",
                severity="HIGH",
                starting_evidence="CZK 500,000",
                trace=[
                    TraceEntry(stage="executive_summary", file="025-2-executive_summary.md", evidence="CZK 500,000", is_origin=False),
                    TraceEntry(stage="project_plan", file="005-2-project_plan.md", evidence="Budget: 500k", is_origin=False),
                    TraceEntry(stage="make_assumptions", file="003-5-make_assumptions.md", evidence="Assume budget of 500k", is_origin=True),
                ],
                origin_stage="make_assumptions",
                origin=OriginInfo(
                    stage="make_assumptions",
                    file="003-5-make_assumptions.md",
                    source_code_files=["make_assumptions.py"],
                    category="prompt_fixable",
                    likely_cause="Prompt generates budget without data",
                    suggestion="Add validation step",
                ),
                depth=3,
            ),
            TracedFlaw(
                id="flaw_002",
                description="Missing market sizing",
                severity="MEDIUM",
                starting_evidence="growing Czech market",
                trace=[
                    TraceEntry(stage="executive_summary", file="025-2-executive_summary.md", evidence="growing Czech market", is_origin=True),
                ],
                origin_stage="executive_summary",
                depth=1,
            ),
        ],
        llm_calls_made=8,
    )


class TestWriteJsonReport(unittest.TestCase):
    def test_writes_valid_json(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.json"
            result = _make_sample_result()
            write_json_report(result, output_path)

            self.assertTrue(output_path.exists())
            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("input", data)
            self.assertIn("flaws", data)
            self.assertIn("summary", data)

    def test_json_contains_correct_summary(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.json"
            result = _make_sample_result()
            write_json_report(result, output_path)

            data = json.loads(output_path.read_text(encoding="utf-8"))
            summary = data["summary"]
            self.assertEqual(summary["total_flaws"], 2)
            self.assertEqual(summary["deepest_origin_stage"], "make_assumptions")
            self.assertEqual(summary["deepest_origin_depth"], 3)
            self.assertEqual(summary["llm_calls_made"], 8)

    def test_json_flaws_sorted_by_depth(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.json"
            result = _make_sample_result()
            write_json_report(result, output_path)

            data = json.loads(output_path.read_text(encoding="utf-8"))
            depths = [f["depth"] for f in data["flaws"]]
            self.assertEqual(depths, sorted(depths, reverse=True))


class TestWriteMarkdownReport(unittest.TestCase):
    def test_writes_markdown_file(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.md"
            result = _make_sample_result()
            write_markdown_report(result, output_path)

            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("# Flaw Trace Report", content)

    def test_markdown_contains_flaw_details(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.md"
            result = _make_sample_result()
            write_markdown_report(result, output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Budget of CZK 500,000 is unvalidated", content)
            self.assertIn("make_assumptions", content)
            self.assertIn("executive_summary", content)

    def test_markdown_contains_trace_table(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.md"
            result = _make_sample_result()
            write_markdown_report(result, output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("| Stage |", content)
            self.assertIn("| File |", content)

    def test_empty_result_produces_valid_markdown(self):
        with TemporaryDirectory() as d:
            output_path = Path(d) / "flaw_trace.md"
            result = FlawTraceResult(
                starting_file="030-report.html",
                flaw_description="test",
                output_dir="/tmp",
                flaws=[],
                llm_calls_made=1,
            )
            write_markdown_report(result, output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Flaws found:** 0", content)
