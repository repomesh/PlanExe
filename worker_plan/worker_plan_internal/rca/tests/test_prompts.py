# worker_plan/worker_plan_internal/rca/tests/test_prompts.py
import unittest
from llama_index.core.llms import ChatMessage, MessageRole
from worker_plan_internal.rca.prompts import (
    IdentifiedProblem,
    ProblemIdentificationResult,
    UpstreamCheckResult,
    SourceCodeAnalysisResult,
    build_problem_identification_messages,
    build_upstream_check_messages,
    build_source_code_analysis_messages,
)


class TestPydanticModels(unittest.TestCase):
    def test_identified_problem_valid(self):
        problem = IdentifiedProblem(
            description="Budget figure is fabricated",
            evidence="The budget is CZK 500,000",
            severity="HIGH",
        )
        self.assertEqual(problem.severity, "HIGH")

    def test_identified_problem_rejects_invalid_severity(self):
        with self.assertRaises(Exception):
            IdentifiedProblem(
                description="test",
                evidence="test",
                severity="CRITICAL",
            )

    def test_problem_identification_result(self):
        result = ProblemIdentificationResult(problems=[
            IdentifiedProblem(description="test", evidence="quote", severity="LOW"),
        ])
        self.assertEqual(len(result.problems), 1)

    def test_upstream_check_result_found(self):
        result = UpstreamCheckResult(found=True, evidence="quote", explanation="precursor")
        self.assertTrue(result.found)
        self.assertEqual(result.evidence, "quote")

    def test_upstream_check_result_not_found(self):
        result = UpstreamCheckResult(found=False, evidence=None, explanation="clean")
        self.assertFalse(result.found)

    def test_source_code_analysis_result(self):
        result = SourceCodeAnalysisResult(
            category="prompt_fixable",
            likely_cause="prompt lacks validation",
            relevant_code_section="system_prompt = ...",
            suggestion="add grounding check",
        )
        self.assertEqual(result.category, "prompt_fixable")
        self.assertIsInstance(result.likely_cause, str)

    def test_source_code_analysis_rejects_invalid_category(self):
        with self.assertRaises(Exception):
            SourceCodeAnalysisResult(
                category="unknown_category",
                likely_cause="test",
                relevant_code_section="test",
                suggestion="test",
            )


class TestBuildProblemIdentificationMessages(unittest.TestCase):
    def test_returns_chat_messages(self):
        messages = build_problem_identification_messages(
            filename="030-report.html",
            file_content="<html>report content</html>",
            user_problem_description="budget is wrong",
        )
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, MessageRole.SYSTEM)
        self.assertEqual(messages[1].role, MessageRole.USER)

    def test_user_message_contains_inputs(self):
        messages = build_problem_identification_messages(
            filename="025-2-executive_summary.md",
            file_content="# Summary\nBudget: 500k",
            user_problem_description="fabricated budget",
        )
        user_content = messages[1].content
        self.assertIn("025-2-executive_summary.md", user_content)
        self.assertIn("# Summary", user_content)
        self.assertIn("fabricated budget", user_content)


class TestBuildUpstreamCheckMessages(unittest.TestCase):
    def test_returns_chat_messages(self):
        messages = build_upstream_check_messages(
            problem_description="Budget is fabricated",
            evidence_quote="CZK 500,000",
            upstream_filename="005-2-project_plan.md",
            upstream_file_content="# Project Plan\nBudget: 500k",
        )
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)

    def test_user_message_contains_problem_and_upstream(self):
        messages = build_upstream_check_messages(
            problem_description="Missing market sizing",
            evidence_quote="growing Czech market",
            upstream_filename="003-5-make_assumptions.md",
            upstream_file_content="# Assumptions\nMarket is growing",
        )
        user_content = messages[1].content
        self.assertIn("Missing market sizing", user_content)
        self.assertIn("growing Czech market", user_content)
        self.assertIn("003-5-make_assumptions.md", user_content)


class TestBuildSourceCodeAnalysisMessages(unittest.TestCase):
    def test_returns_chat_messages(self):
        messages = build_source_code_analysis_messages(
            problem_description="Budget fabricated",
            evidence_quote="CZK 500,000",
            source_code_contents=[
                ("nodes/make_assumptions.py", "class MakeAssumptionsTask: ..."),
                ("assume/make_assumptions.py", "def execute(llm, query): ..."),
            ],
        )
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)

    def test_user_message_contains_source_code(self):
        messages = build_source_code_analysis_messages(
            problem_description="Missing analysis",
            evidence_quote="no data",
            source_code_contents=[
                ("my_stage.py", "SYSTEM_PROMPT = 'Generate assumptions'"),
            ],
        )
        user_content = messages[1].content
        self.assertIn("my_stage.py", user_content)
        self.assertIn("SYSTEM_PROMPT", user_content)
