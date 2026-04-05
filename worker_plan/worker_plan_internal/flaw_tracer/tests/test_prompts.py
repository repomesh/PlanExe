# worker_plan/worker_plan_internal/flaw_tracer/tests/test_prompts.py
import unittest
from llama_index.core.llms import ChatMessage, MessageRole
from worker_plan_internal.flaw_tracer.prompts import (
    IdentifiedFlaw,
    FlawIdentificationResult,
    UpstreamCheckResult,
    SourceCodeAnalysisResult,
    build_flaw_identification_messages,
    build_upstream_check_messages,
    build_source_code_analysis_messages,
)


class TestPydanticModels(unittest.TestCase):
    def test_identified_flaw_valid(self):
        flaw = IdentifiedFlaw(
            description="Budget figure is fabricated",
            evidence="The budget is CZK 500,000",
            severity="HIGH",
        )
        self.assertEqual(flaw.severity, "HIGH")

    def test_identified_flaw_rejects_invalid_severity(self):
        with self.assertRaises(Exception):
            IdentifiedFlaw(
                description="test",
                evidence="test",
                severity="CRITICAL",
            )

    def test_flaw_identification_result(self):
        result = FlawIdentificationResult(flaws=[
            IdentifiedFlaw(description="test", evidence="quote", severity="LOW"),
        ])
        self.assertEqual(len(result.flaws), 1)

    def test_upstream_check_result_found(self):
        result = UpstreamCheckResult(found=True, evidence="quote", explanation="precursor")
        self.assertTrue(result.found)
        self.assertEqual(result.evidence, "quote")

    def test_upstream_check_result_not_found(self):
        result = UpstreamCheckResult(found=False, evidence=None, explanation="clean")
        self.assertFalse(result.found)

    def test_source_code_analysis_result(self):
        result = SourceCodeAnalysisResult(
            likely_cause="prompt lacks validation",
            relevant_code_section="system_prompt = ...",
            suggestion="add grounding check",
        )
        self.assertIsInstance(result.likely_cause, str)


class TestBuildFlawIdentificationMessages(unittest.TestCase):
    def test_returns_chat_messages(self):
        messages = build_flaw_identification_messages(
            filename="030-report.html",
            file_content="<html>report content</html>",
            user_flaw_description="budget is wrong",
        )
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, MessageRole.SYSTEM)
        self.assertEqual(messages[1].role, MessageRole.USER)

    def test_user_message_contains_inputs(self):
        messages = build_flaw_identification_messages(
            filename="025-2-executive_summary.md",
            file_content="# Summary\nBudget: 500k",
            user_flaw_description="fabricated budget",
        )
        user_content = messages[1].content
        self.assertIn("025-2-executive_summary.md", user_content)
        self.assertIn("# Summary", user_content)
        self.assertIn("fabricated budget", user_content)


class TestBuildUpstreamCheckMessages(unittest.TestCase):
    def test_returns_chat_messages(self):
        messages = build_upstream_check_messages(
            flaw_description="Budget is fabricated",
            evidence_quote="CZK 500,000",
            upstream_filename="005-2-project_plan.md",
            upstream_file_content="# Project Plan\nBudget: 500k",
        )
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)

    def test_user_message_contains_flaw_and_upstream(self):
        messages = build_upstream_check_messages(
            flaw_description="Missing market sizing",
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
            flaw_description="Budget fabricated",
            evidence_quote="CZK 500,000",
            source_code_contents=[
                ("stages/make_assumptions.py", "class MakeAssumptionsTask: ..."),
                ("assume/make_assumptions.py", "def execute(llm, query): ..."),
            ],
        )
        self.assertIsInstance(messages, list)
        self.assertEqual(len(messages), 2)

    def test_user_message_contains_source_code(self):
        messages = build_source_code_analysis_messages(
            flaw_description="Missing analysis",
            evidence_quote="no data",
            source_code_contents=[
                ("my_stage.py", "SYSTEM_PROMPT = 'Generate assumptions'"),
            ],
        )
        user_content = messages[1].content
        self.assertIn("my_stage.py", user_content)
        self.assertIn("SYSTEM_PROMPT", user_content)
