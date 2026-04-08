# worker_plan/worker_plan_internal/rca/tests/test_tracer.py
"""Tests for the root cause analyzer recursive algorithm.

Since ResponseMockLLM does NOT support as_structured_llm(), we mock the three
private LLM-calling methods (_identify_problems, _check_upstream,
_analyze_source_code) directly.  This tests the tracing logic — recursion,
deduplication, max depth — which is the important part.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from worker_plan_internal.rca.tracer import (
    RootCauseAnalyzer,
    RCAResult,
    TracedProblem,
    TraceEntry,
    OriginInfo,
)
from worker_plan_internal.rca.prompts import (
    ProblemIdentificationResult,
    IdentifiedProblem,
    UpstreamCheckResult,
)
from worker_plan_internal.llm_util.response_mockllm import ResponseMockLLM
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelWithInstance


def _make_executor() -> LLMExecutor:
    """Create a dummy LLMExecutor (won't actually be called when methods are mocked)."""
    llm = ResponseMockLLM(responses=["unused"])
    llm_models = LLMModelWithInstance.from_instances([llm])
    return LLMExecutor(llm_models=llm_models)


def _make_tracer(output_dir: Path, max_depth: int = 15, verbose: bool = False) -> RootCauseAnalyzer:
    """Create a RootCauseAnalyzer with a dummy executor."""
    executor = _make_executor()
    return RootCauseAnalyzer(
        output_dir=output_dir,
        llm_executor=executor,
        max_depth=max_depth,
        verbose=verbose,
    )


class TestRCAResult(unittest.TestCase):
    def test_dataclass_creation(self):
        result = RCAResult(
            starting_file="report.html",
            problem_description="test",
            output_dir="/tmp/test",
            problems=[],
            llm_calls_made=0,
        )
        self.assertEqual(result.starting_file, "report.html")
        self.assertEqual(len(result.problems), 0)
        self.assertEqual(result.llm_calls_made, 0)

    def test_dataclass_with_problems(self):
        problem = TracedProblem(
            id="problem_001",
            description="Budget fabricated",
            severity="HIGH",
            starting_evidence="CZK 500,000",
            trace=[TraceEntry(node="test", file="test.md", evidence="ev")],
        )
        result = RCAResult(
            starting_file="test.md",
            problem_description="test",
            output_dir="/tmp/test",
            problems=[problem],
            llm_calls_made=1,
        )
        self.assertEqual(len(result.problems), 1)
        self.assertEqual(result.problems[0].severity, "HIGH")


class TestTracedProblem(unittest.TestCase):
    def test_defaults(self):
        problem = TracedProblem(
            id="problem_001",
            description="test",
            severity="LOW",
            starting_evidence="ev",
            trace=[],
        )
        self.assertIsNone(problem.origin_node)
        self.assertIsNone(problem.origin)
        self.assertEqual(problem.depth, 0)
        self.assertTrue(problem.trace_complete)


class TestRootCauseAnalyzerPhase1(unittest.TestCase):
    """Test problem identification (Phase 1) with mocked LLM methods."""

    def test_identify_problems(self):
        """The analyzer should produce TracedProblem objects from Phase 1 identification."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Create a minimal output file
            report_file = output_dir / "executive_summary.md"
            report_file.write_text("# Summary\nBudget: CZK 500,000", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            # Mock Phase 1: identify problems
            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(
                        description="Budget is unvalidated",
                        evidence="CZK 500,000",
                        severity="HIGH",
                    )
                ]
            )

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_analyze_source_code') as mock_analyze:
                result = tracer.trace("executive_summary.md", "budget is unvalidated")

            self.assertIsInstance(result, RCAResult)
            self.assertGreaterEqual(len(result.problems), 1)
            problem = result.problems[0]
            self.assertEqual(problem.description, "Budget is unvalidated")
            self.assertEqual(problem.severity, "HIGH")

    def test_file_not_found_raises(self):
        """The tracer should raise FileNotFoundError for missing starting files."""
        with TemporaryDirectory() as d:
            tracer = _make_tracer(Path(d))
            with self.assertRaises(FileNotFoundError):
                tracer.trace("nonexistent.md", "test")


class TestRootCauseAnalyzerUpstreamTrace(unittest.TestCase):
    """Test upstream tracing (Phase 2) with a simple two-level chain."""

    def test_traces_problem_upstream(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Create files for a chain: executive_summary -> project_plan -> setup
            (output_dir / "executive_summary.md").write_text("Budget: CZK 500,000", encoding="utf-8")
            (output_dir / "project_plan.md").write_text("Budget: CZK 500,000", encoding="utf-8")
            (output_dir / "plan.txt").write_text("Open a tea shop", encoding="utf-8")
            # Create other upstream files that executive_summary depends on
            (output_dir / "strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            # Mock Phase 1: identify problems
            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(
                        description="Budget fabricated",
                        evidence="CZK 500,000",
                        severity="HIGH",
                    )
                ]
            )

            # Track upstream check calls to return different results per file
            upstream_call_count = 0
            upstream_responses = {}

            def mock_check_upstream(problem_desc, evidence, upstream_filename, upstream_content):
                nonlocal upstream_call_count
                upstream_call_count += 1
                # project_plan has the problem; others are clean
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

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("executive_summary.md", "budget is fabricated")

            self.assertEqual(len(result.problems), 1)
            problem = result.problems[0]
            # The trace should include at least executive_summary and project_plan
            trace_nodes = [entry.node for entry in problem.trace]
            self.assertIn("executive_summary", trace_nodes)
            self.assertIn("project_plan", trace_nodes)
            # Origin should be project_plan (problem found there but not in its upstream 'setup')
            self.assertEqual(problem.origin_node, "project_plan")

    def test_deduplication_works(self):
        """Stages already checked for the same problem should be skipped."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # executive_summary depends on strategic_decisions_markdown, scenarios_markdown, etc.
            # project_plan also depends on strategic_decisions_markdown, scenarios_markdown.
            # When we trace through project_plan, those shared upstreams should be skipped.
            (output_dir / "executive_summary.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "project_plan.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "plan.txt").write_text("Open a tea shop", encoding="utf-8")
            (output_dir / "strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="Budget fabricated", evidence="500k", severity="HIGH")
                ]
            )

            checked_stages = []

            def mock_check_upstream(problem_desc, evidence, upstream_filename, upstream_content):
                checked_stages.append(upstream_filename)
                if "project_plan" in upstream_filename:
                    return UpstreamCheckResult(found=True, evidence="500k", explanation="found here")
                return UpstreamCheckResult(found=False, evidence=None, explanation="clean")

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("executive_summary.md", "budget fabricated")

            # Count unique filenames checked — dedup should prevent re-checking
            # strategic_decisions and scenarios at the project_plan level
            unique_checked = set(checked_stages)
            # Each file should appear at most once
            self.assertEqual(len(checked_stages), len(unique_checked),
                             f"Dedup failed: checked {checked_stages}")


class TestRootCauseAnalyzerMaxDepth(unittest.TestCase):
    def test_respects_max_depth_zero(self):
        """With max_depth=0, no upstream tracing happens."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "executive_summary.md").write_text("Budget: 500k", encoding="utf-8")

            tracer = _make_tracer(output_dir, max_depth=0)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="test problem", evidence="500k", severity="LOW")
                ]
            )

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream') as mock_check, \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("executive_summary.md", "test")

            self.assertEqual(len(result.problems), 1)
            # With max_depth=0, no upstream tracing happens
            self.assertEqual(len(result.problems[0].trace), 1)  # only the starting file
            # _check_upstream should never have been called
            mock_check.assert_not_called()

    def test_max_depth_limits_recursion(self):
        """With max_depth=1, tracing should stop after one level of upstream."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "executive_summary.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "project_plan.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "plan.txt").write_text("plan", encoding="utf-8")
            (output_dir / "strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir, max_depth=1)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="problem", evidence="500k", severity="MEDIUM")
                ]
            )

            def always_found(problem_desc, evidence, upstream_filename, upstream_content):
                return UpstreamCheckResult(found=True, evidence="500k", explanation="found")

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=always_found), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("executive_summary.md", "test")

            self.assertEqual(len(result.problems), 1)
            problem = result.problems[0]
            # trace_complete should be False because max depth was hit
            self.assertFalse(problem.trace_complete)


class TestRootCauseAnalyzerSourceCodeAnalysis(unittest.TestCase):
    """Test that Phase 3 source code analysis is invoked at the origin node."""

    def test_source_code_analysis_called_at_origin(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "executive_summary.md").write_text("Budget: 500k", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="problem", evidence="500k", severity="HIGH")
                ]
            )

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_analyze_source_code') as mock_analyze:
                result = tracer.trace("executive_summary.md", "test")

            # _analyze_source_code should have been called once for the origin
            mock_analyze.assert_called_once()
            args = mock_analyze.call_args
            # First positional arg is the TracedProblem, second is the node name
            self.assertEqual(args[0][1], "executive_summary")

    def test_source_code_analysis_called_at_deep_origin(self):
        """Phase 3 should run when the origin is found at a deeper upstream node."""
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            # Create files for a chain: executive_summary -> project_plan (origin)
            (output_dir / "executive_summary.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "project_plan.md").write_text("Budget: 500k", encoding="utf-8")
            (output_dir / "plan.txt").write_text("Open a tea shop", encoding="utf-8")
            (output_dir / "strategic_decisions.md").write_text("decisions", encoding="utf-8")
            (output_dir / "scenarios.md").write_text("scenarios", encoding="utf-8")
            (output_dir / "consolidate_assumptions_full.md").write_text("assumptions", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="Budget fabricated", evidence="500k", severity="HIGH")
                ]
            )

            def mock_check_upstream(problem_desc, evidence, upstream_filename, upstream_content):
                # project_plan has the problem; others are clean
                if "project_plan" in upstream_filename:
                    return UpstreamCheckResult(
                        found=True, evidence="Budget: 500k", explanation="Budget originates here"
                    )
                return UpstreamCheckResult(found=False, evidence=None, explanation="clean")

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code') as mock_analyze:
                result = tracer.trace("executive_summary.md", "budget fabricated")

            # Phase 3 should have been called at the deep origin (project_plan)
            mock_analyze.assert_called_once()
            args = mock_analyze.call_args
            # Second positional arg is the origin node name
            self.assertEqual(args[0][1], "project_plan")


class TestRootCauseAnalyzerMultipleProblems(unittest.TestCase):
    """Test that multiple problems are traced independently."""

    def test_traces_multiple_problems(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "executive_summary.md").write_text("Budget: 500k\nTimeline: 2 months", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="Budget fabricated", evidence="500k", severity="HIGH"),
                    IdentifiedProblem(description="Timeline unrealistic", evidence="2 months", severity="MEDIUM"),
                ]
            )

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("executive_summary.md", "multiple issues")

            self.assertEqual(len(result.problems), 2)
            descriptions = {f.description for f in result.problems}
            self.assertIn("Budget fabricated", descriptions)
            self.assertIn("Timeline unrealistic", descriptions)
            # Each problem should have a unique ID
            ids = [f.id for f in result.problems]
            self.assertEqual(len(ids), len(set(ids)))


class TestRootCauseAnalyzerSortsByDepth(unittest.TestCase):
    """Test that results are sorted by depth (deepest origin first)."""

    def test_problems_sorted_by_depth_descending(self):
        with TemporaryDirectory() as d:
            output_dir = Path(d)
            (output_dir / "executive_summary.md").write_text("content", encoding="utf-8")
            (output_dir / "project_plan.md").write_text("content", encoding="utf-8")
            (output_dir / "strategic_decisions.md").write_text("content", encoding="utf-8")
            (output_dir / "scenarios.md").write_text("content", encoding="utf-8")
            (output_dir / "consolidate_assumptions_full.md").write_text("content", encoding="utf-8")

            tracer = _make_tracer(output_dir)

            mock_identification = ProblemIdentificationResult(
                problems=[
                    IdentifiedProblem(description="shallow problem", evidence="ev1", severity="LOW"),
                    IdentifiedProblem(description="deep problem", evidence="ev2", severity="HIGH"),
                ]
            )

            call_count = 0

            def mock_check_upstream(problem_desc, evidence, upstream_filename, upstream_content):
                nonlocal call_count
                call_count += 1
                # For "deep problem", find it in project_plan
                if "deep problem" in problem_desc and "project_plan" in upstream_filename:
                    return UpstreamCheckResult(found=True, evidence="ev2", explanation="found")
                return UpstreamCheckResult(found=False, evidence=None, explanation="clean")

            with patch.object(tracer, '_identify_problems', return_value=mock_identification), \
                 patch.object(tracer, '_check_upstream', side_effect=mock_check_upstream), \
                 patch.object(tracer, '_analyze_source_code'):
                result = tracer.trace("executive_summary.md", "test")

            self.assertEqual(len(result.problems), 2)
            # Deepest origin should be first
            self.assertGreaterEqual(result.problems[0].depth, result.problems[1].depth)


if __name__ == "__main__":
    unittest.main()
