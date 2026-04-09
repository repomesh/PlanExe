# worker_plan/worker_plan_internal/diagnostics/tests/test_prompt_adherence.py
import unittest
from worker_plan_internal.diagnostics.prompt_adherence import (
    DirectiveType,
    Directive,
    DirectiveExtractionResult,
    AdherenceCategory,
    AdherenceResult,
    AdherenceScoreResult,
    PromptAdherence,
)


class TestDirectiveModel(unittest.TestCase):
    def test_directive_valid(self):
        d = Directive(
            directive_id="D1",
            directive_type=DirectiveType.CONSTRAINT,
            text="Budget: DKK 500M",
            importance_5=5,
        )
        self.assertEqual(d.directive_id, "D1")
        self.assertEqual(d.directive_type, DirectiveType.CONSTRAINT)
        self.assertEqual(d.importance_5, 5)

    def test_directive_extraction_result(self):
        result = DirectiveExtractionResult(
            directives=[
                Directive(directive_id="D1", directive_type=DirectiveType.CONSTRAINT, text="Budget: DKK 500M", importance_5=5),
                Directive(directive_id="D2", directive_type=DirectiveType.STATED_FACT, text="East Wing demolished", importance_5=5),
            ]
        )
        self.assertEqual(len(result.directives), 2)


class TestAdherenceResultModel(unittest.TestCase):
    def test_adherence_result_valid(self):
        r = AdherenceResult(
            directive_id="D1",
            adherence_5=3,
            category=AdherenceCategory.SOFTENED,
            evidence="Budget adjusted to DKK 800M",
            explanation="The plan increased the budget beyond the stated constraint.",
        )
        self.assertEqual(r.adherence_5, 3)
        self.assertEqual(r.category, AdherenceCategory.SOFTENED)

    def test_adherence_score_result(self):
        result = AdherenceScoreResult(
            results=[
                AdherenceResult(
                    directive_id="D1", adherence_5=5,
                    category=AdherenceCategory.FULLY_HONORED,
                    evidence="Budget: DKK 500M", explanation="Honored exactly.",
                ),
                AdherenceResult(
                    directive_id="D2", adherence_5=1,
                    category=AdherenceCategory.CONTRADICTED,
                    evidence="Demolition permit required", explanation="Plan ignores stated fact.",
                ),
            ]
        )
        self.assertEqual(len(result.results), 2)


class TestPromptAdherenceMarkdown(unittest.TestCase):
    def test_convert_to_markdown_produces_report(self):
        directives = DirectiveExtractionResult(
            directives=[
                Directive(directive_id="D1", directive_type=DirectiveType.CONSTRAINT, text="Budget: DKK 500M", importance_5=5),
                Directive(directive_id="D2", directive_type=DirectiveType.STATED_FACT, text="East Wing demolished", importance_5=5),
            ]
        )
        scores = AdherenceScoreResult(
            results=[
                AdherenceResult(
                    directive_id="D1", adherence_5=5,
                    category=AdherenceCategory.FULLY_HONORED,
                    evidence="Budget: DKK 500M", explanation="Honored.",
                ),
                AdherenceResult(
                    directive_id="D2", adherence_5=1,
                    category=AdherenceCategory.CONTRADICTED,
                    evidence="Demolition permit required",
                    explanation="Plan contradicts stated fact.",
                ),
            ]
        )
        markdown = PromptAdherence.convert_to_markdown(directives, scores)
        self.assertIn("# Prompt Adherence Report", markdown)
        self.assertIn("Budget: DKK 500M", markdown)
        self.assertIn("contradicted", markdown)
        self.assertIn("Overall Adherence", markdown)

    def test_overall_score_calculation(self):
        directives = DirectiveExtractionResult(
            directives=[
                Directive(directive_id="D1", directive_type=DirectiveType.CONSTRAINT, text="A", importance_5=5),
                Directive(directive_id="D2", directive_type=DirectiveType.STATED_FACT, text="B", importance_5=5),
            ]
        )
        scores = AdherenceScoreResult(
            results=[
                AdherenceResult(directive_id="D1", adherence_5=5, category=AdherenceCategory.FULLY_HONORED, evidence="", explanation=""),
                AdherenceResult(directive_id="D2", adherence_5=1, category=AdherenceCategory.CONTRADICTED, evidence="", explanation=""),
            ]
        )
        score = PromptAdherence.calculate_overall_score(directives, scores)
        self.assertEqual(score, 60)

    def test_overall_score_empty(self):
        directives = DirectiveExtractionResult(directives=[])
        scores = AdherenceScoreResult(results=[])
        score = PromptAdherence.calculate_overall_score(directives, scores)
        self.assertEqual(score, 100)
