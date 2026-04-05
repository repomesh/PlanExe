# worker_plan/worker_plan_internal/flaw_tracer/tests/test_tracer.py
"""Tests for the flaw tracer recursive algorithm.

Since ResponseMockLLM does NOT support as_structured_llm(), we mock the three
private LLM-calling methods (_identify_flaws, _check_upstream,
_analyze_source_code) directly.  This tests the tracing logic — recursion,
deduplication, max depth — which is the important part.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from worker_plan_internal.flaw_tracer.tracer import (
    FlawTracer,
    FlawTraceResult,
    TracedFlaw,
    TraceEntry,
    OriginInfo,
)
from worker_plan_internal.flaw_tracer.prompts import (
    FlawIdentificationResult,
    IdentifiedFlaw,
    UpstreamCheckResult,
    SourceCodeAnalysisResult,
)
from worker_plan_internal.llm_util.response_mockllm import ResponseMockLLM
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelWithInstance


def _make_executor() -> LLMExecutor:
    """Create a dummy LLMExecutor (won't actually be called when methods are mocked)."""
    llm = ResponseMockLLM(responses=["unused"])
    llm_models = LLMModelWithInstance.from_instances([llm])
    return LLMExecutor(llm_models=llm_models)


def _make_tracer(output_dir: Path, max_depth: int = 15, verbose: bool = False) -> FlawTracer:
    """Create a FlawTracer with a dummy executor and a real source_code_base."""
    executor = _make_executor()
    source_base = Path(__file__).resolve().parent.parent.parent.parent  # worker_plan/
    return FlawTracer(
        output_dir=output_dir,
        llm_executor=executor,
        source_code_base=source_base,
        max_depth=max_depth,
        verbose=verbose,
    )


class TestFlawTraceResult(unittest.TestCase):
    def test_dataclass_creation(self):
        result = FlawTraceResult(
            starting_file="030-report.html",
            flaw_description="test",
            output_dir="/tmp/test",
            flaws=[],
            llm_calls_made=0,
        )
        self.assertEqual(result.starting_file, "030-report.html")
        self.assertEqual(len(result.flaws), 0)
        self.assertEqual(result.llm_calls_made, 0)

    def test_dataclass_with_flaws(self):
        flaw = TracedFlaw(
            id="flaw_001",
            description="Budget fabricated",
            severity="HIGH",
            starting_evidence="CZK 500,000",
            trace=[TraceEntry(stage="test", file="test.md", evidence="ev")],
        )
        result = FlawTraceResult(
            starting_file="test.md",
            flaw_description="test",
            output_dir="/tmp/test",
            flaws=[flaw],
            llm_calls_made=1,
        )
        self.assertEqual(len(result.flaws), 1)
        self.assertEqual(result.flaws[0].severity, "HIGH")


class TestTracedFlaw(unittest.TestCase):
    def test_defaults(self):
        flaw = TracedFlaw(
            id="flaw_001",
            description="test",
            severity="LOW",
            starting_evidence="ev",
            trace=[],
        )
        self.assertIsNone(flaw.origin_stage)
        self.assertIsNone(flaw.origin)
        self.assertEqual(flaw.depth, 0)
        self.assertTrue(flaw.trace_complete)


class TestFlawTracerPhase1(unittest.TestCase):
    """Test flaw identification (Phase 1) with mocked LLM methods."""

    def test_identify_flaws_returns_flaws(self):
        """The tracer should produce TracedFlaw objects from Phase 1 identification."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Create a minimal output file
            report_file = output_dir / "025-2-executive_summary.md"
            report_file.write_text("# Summary\nBudget: CZK 500,000", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            # Mock Phase 1: identify flaws
            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(
                        description="Budget is unvalidated",
                        evidence="CZK 500,000",
                        severity="HIGH",
                    )
                ]
            )

            # Mock Phase 2: upstream check — not found (no upstream files on disk)
            # Mock Phase 3: source code analysis
            mock_analysis = SourceCodeAnalysisResult(
                likely_cause="Prompt asks for budget without data",
                relevant_code_section="system_prompt = ...",
                suggestion="Add validation step",
            )

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_analyze_source_code') as mock_analyze:
                result = tracer.trace("025-2-executive_summary.md", "budget is unvalidated")

            self.assertIsInstance(result, FlawTraceResult)
            self.assertGreaterEqual(len(result.flaws), 1)
            flaw = result.flaws[0]
            self.assertEqual(flaw.description, "Budget is unvalidated")
            self.assertEqual(flaw.severity, "HIGH")

    def test_file_not_found_raises(self):
        """The tracer should raise FileNotFoundError for missing starting files."""
        with TemporaryDirectory() as d:
            tracer = _make_tracer(Path(d))
            with self.assertRaises(FileNotFoundError):
                tracer.trace("nonexistent.md", "test")


class TestFlawTracerUpstreamTrace(unittest.TestCase):
    """Test upstream tracing (Phase 2) with a simple two-level chain."""

    def test_traces_flaw_upstream(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Create files for a chain: executive_summary -> project_plan -> setup
            (output_dir / "025-2-executive_summary.md").write_text("Budget: CZK 500,000", encoding="utf-8")
            (output_dir / "005-2-project_plan.md").write_text("Budget: CZK 500,000", encoding="utf-8")
            (output_dir / "001-2-plan.txt").write_text("Open a tea shop", encoding="utf-8")
            # Create other upstream files that executive_summary depends on
            (output_dir / "002-14-strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "002-19-scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "003-10-consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            # Mock Phase 1: identify flaws
            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(
                        description="Budget fabricated",
                        evidence="CZK 500,000",
                        severity="HIGH",
                    )
                ]
            )

            # Track upstream check calls to return different results per file
            upstream_call_count = 0
            upstream_responses = {}

            def mock_check_upstream(flaw_desc, evidence, upstream_filename, upstream_content):
                nonlocal upstream_call_count
                upstream_call_count += 1
                # project_plan has the flaw; others are clean
                if "project_plan" in upstream_filename:
                    return UpstreamCheckResult(
                        found=True,
                        evidence="Budget: CZK 500,000",
                        explanation="Budget originates here",
                    )
                else:
                    return UpstreamCheckResult(
                        found=False,
                        evidence=None,
                        explanation="clean",
                    )

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("025-2-executive_summary.md", "budget is fabricated")

            self.assertEqual(len(result.flaws), 1)
            flaw = result.flaws[0]
            # The trace should include at least executive_summary and project_plan
            trace_stages = [entry.stage for entry in flaw.trace]
            self.assertIn("executive_summary", trace_stages)
            self.assertIn("project_plan", trace_stages)
            # Origin should be project_plan (flaw found there but not in its upstream 'setup')
            self.assertEqual(flaw.origin_stage, "project_plan")

    def test_deduplication_works(self):
        """Stages already checked for the same flaw should be skipped."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # executive_summary depends on strategic_decisions_markdown, scenarios_markdown, etc.
            # project_plan also depends on strategic_decisions_markdown, scenarios_markdown.
            # When we trace through project_plan, those shared upstreams should be skipped.
            (output_dir / "025-2-executive_summary.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "005-2-project_plan.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "001-2-plan.txt").write_text("Open a tea shop", encoding="utf-8")
            (output_dir / "002-14-strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "002-19-scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "003-10-consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(description="Budget fabricated", evidence="500k", severity="HIGH")
                ]
            )

            checked_stages = []

            def mock_check_upstream(flaw_desc, evidence, upstream_filename, upstream_content):
                checked_stages.append(upstream_filename)
                if "project_plan" in upstream_filename:
                    return UpstreamCheckResult(found=True, evidence="500k", explanation="found here")
                return UpstreamCheckResult(found=False, evidence=None, explanation="clean")

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("025-2-executive_summary.md", "budget fabricated")

            # Count unique filenames checked — dedup should prevent re-checking
            # strategic_decisions and scenarios at the project_plan level
            unique_checked = set(checked_stages)
            # Each file should appear at most once
            self.assertEqual(len(checked_stages), len(unique_checked),
                             f"Dedup failed: checked {checked_stages}")


class TestFlawTracerMaxDepth(unittest.TestCase):
    def test_respects_max_depth_zero(self):
        """With max_depth=0, no upstream tracing happens."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "025-2-executive_summary.md").write_text("Budget: 500k", encoding="utf-8")

            tracer = _make_tracer(output_dir, max_depth=0)

            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(description="test flaw", evidence="500k", severity="LOW")
                ]
            )

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream') as mock_check, \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("025-2-executive_summary.md", "test")

            self.assertEqual(len(result.flaws), 1)
            # With max_depth=0, no upstream tracing happens
            self.assertEqual(len(result.flaws[0].trace), 1)  # only the starting file
            # _check_upstream should never have been called
            mock_check.assert_not_called()

    def test_max_depth_limits_recursion(self):
        """With max_depth=1, tracing should stop after one level of upstream."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "025-2-executive_summary.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "005-2-project_plan.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "001-2-plan.txt").write_text("plan", encoding="utf-8")
            (output_dir / "002-14-strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "002-19-scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "003-10-consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir, max_depth=1)

            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(description="flaw", evidence="500k", severity="MEDIUM")
                ]
            )

            def always_found(flaw_desc, evidence, upstream_filename, upstream_content):
                return UpstreamCheckResult(found=True, evidence="500k", explanation="found")

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=always_found), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("025-2-executive_summary.md", "test")

            self.assertEqual(len(result.flaws), 1)
            flaw = result.flaws[0]
            # trace_complete should be False because max depth was hit
            self.assertFalse(flaw.trace_complete)


class TestFlawTracerSourceCodeAnalysis(unittest.TestCase):
    """Test that Phase 3 source code analysis is invoked at the origin stage."""

    def test_source_code_analysis_called_at_origin(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "025-2-executive_summary.md").write_text("Budget: 500k", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(description="flaw", evidence="500k", severity="HIGH")
                ]
            )

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_analyze_source_code') as mock_analyze:
                result = tracer.trace("025-2-executive_summary.md", "test")

            # _analyze_source_code should have been called once for the origin
            mock_analyze.assert_called_once()
            args = mock_analyze.call_args
            # First positional arg is the TracedFlaw, second is the stage name
            self.assertEqual(args[0][1], "executive_summary")


class TestFlawTracerMultipleFlaws(unittest.TestCase):
    """Test that multiple flaws are traced independently."""

    def test_traces_multiple_flaws(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "025-2-executive_summary.md").write_text("Budget: 500k\nTimeline: 2 months", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(description="Budget fabricated", evidence="500k", severity="HIGH"),
                    IdentifiedFlaw(description="Timeline unrealistic", evidence="2 months", severity="MEDIUM"),
                ]
            )

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("025-2-executive_summary.md", "multiple issues")

            self.assertEqual(len(result.flaws), 2)
            descriptions = {f.description for f in result.flaws}
            self.assertIn("Budget fabricated", descriptions)
            self.assertIn("Timeline unrealistic", descriptions)
            # Each flaw should have a unique ID
            ids = [f.id for f in result.flaws]
            self.assertEqual(len(ids), len(set(ids)))


class TestFlawTracerSortsByDepth(unittest.TestCase):
    """Test that results are sorted by depth (deepest origin first)."""

    def test_flaws_sorted_by_depth_descending(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "025-2-executive_summary.md").write_text("content", encoding="utf-8")
            (output_dir / "005-2-project_plan.md").write_text("content", encoding="utf-8")
            (output_dir / "002-14-strategic_decisions.md").write_text("content", encoding="utf-8")
            (output_dir / "002-19-scenarios.md").write_text("content", encoding="utf-8")
            (output_dir / "003-10-consolidate_assumptions_full.md").write_text("content", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = FlawIdentificationResult(
                flaws=[
                    IdentifiedFlaw(description="shallow flaw", evidence="ev1", severity="LOW"),
                    IdentifiedFlaw(description="deep flaw", evidence="ev2", severity="HIGH"),
                ]
            )

            call_count = 0

            def mock_check_upstream(flaw_desc, evidence, upstream_filename, upstream_content):
                nonlocal call_count
                call_count += 1
                # For "deep flaw", find it in project_plan
                if "deep flaw" in flaw_desc and "project_plan" in upstream_filename:
                    return UpstreamCheckResult(found=True, evidence="ev2", explanation="found")
                return UpstreamCheckResult(found=False, evidence=None, explanation="clean")

            with patch.object(tracer, '_identify_flaws', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("025-2-executive_summary.md", "test")

            self.assertEqual(len(result.flaws), 2)
            # Deepest origin should be first
            self.assertGreaterEqual(result.flaws[0].depth, result.flaws[1].depth)


if __name__ == "__main__":
    unittest.main()
