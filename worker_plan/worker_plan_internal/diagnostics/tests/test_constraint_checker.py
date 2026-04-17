"""
Tests for constraint_checker module.

Unit tests for ConstraintViolationItem, ConstraintCheckResult, and ConstraintChecker.
Integration tests that use a real LLM to verify constraint checking.

Unit tests (no LLM, safe for CI):
PROMPT> cd worker_plan && python -m pytest worker_plan_internal/diagnostics/tests/test_constraint_checker.py -v -k "not LLM"

LLM integration tests (requires RUN_LLM_TESTS=1, local development only):
PROMPT> cd worker_plan && RUN_LLM_TESTS=1 python -m pytest worker_plan_internal/diagnostics/tests/test_constraint_checker.py -v -k "LLM"
"""
import unittest
import os
import json

from worker_plan_internal.diagnostics.constraint_checker import (
    ConstraintViolationItem,
    ConstraintCheckResult,
    ConstraintChecker,
)


class TestConstraintViolationItemModel(unittest.TestCase):
    """Unit tests for the ConstraintViolationItem Pydantic model."""

    def test_satisfied_item(self):
        obj = ConstraintViolationItem(
            constraint_text="Do not use blockchain",
            constraint_classification="negative",
            status="satisfied",
            evidence="No mention of blockchain in the output.",
            explanation="The constraint is respected.",
        )
        self.assertEqual(obj.status, "satisfied")
        self.assertEqual(obj.constraint_classification, "negative")

    def test_violated_item(self):
        obj = ConstraintViolationItem(
            constraint_text="Do not use VR",
            constraint_classification="negative",
            status="violated",
            evidence="Option 1: 'VR immersion rooms'",
            explanation="VR appears as a recommended option despite being banned.",
        )
        self.assertEqual(obj.status, "violated")

    def test_unclear_item(self):
        obj = ConstraintViolationItem(
            constraint_text="Copenhagen",
            constraint_classification="positive",
            status="unclear",
            evidence="No location mentioned in lever output.",
            explanation="The lever stage does not address location.",
        )
        self.assertEqual(obj.status, "unclear")

    def test_invalid_status_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ConstraintViolationItem(
                constraint_text="test",
                constraint_classification="negative",
                status="maybe",
                evidence="none",
                explanation="test",
            )

    def test_invalid_classification_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ConstraintViolationItem(
                constraint_text="test",
                constraint_classification="neutral",
                status="satisfied",
                evidence="none",
                explanation="test",
            )

    def test_model_dump(self):
        obj = ConstraintViolationItem(
            constraint_text="Do not use NFT",
            constraint_classification="negative",
            status="violated",
            evidence="'NFT marketplace' lever",
            explanation="NFT appears as a lever name.",
        )
        d = obj.model_dump()
        self.assertEqual(d["status"], "violated")
        self.assertEqual(d["constraint_text"], "Do not use NFT")


class TestConstraintCheckResultModel(unittest.TestCase):
    """Unit tests for the ConstraintCheckResult Pydantic model."""

    def test_pass_result(self):
        obj = ConstraintCheckResult(
            constraint_violations=[],
            overall_status="pass",
            summary="No violations found.",
        )
        self.assertEqual(obj.overall_status, "pass")
        self.assertEqual(len(obj.constraint_violations), 0)

    def test_fail_result(self):
        items = [
            ConstraintViolationItem(
                constraint_text="Do not use VR",
                constraint_classification="negative",
                status="violated",
                evidence="VR mentioned",
                explanation="VR is recommended.",
            )
        ]
        obj = ConstraintCheckResult(
            constraint_violations=items,
            overall_status="fail",
            summary="1 violation found.",
        )
        self.assertEqual(obj.overall_status, "fail")
        self.assertEqual(len(obj.constraint_violations), 1)

    def test_invalid_overall_status_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ConstraintCheckResult(
                constraint_violations=[],
                overall_status="maybe",
                summary="test",
            )

    def test_model_dump(self):
        obj = ConstraintCheckResult(
            constraint_violations=[],
            overall_status="pass",
            summary="All good.",
        )
        d = obj.model_dump()
        self.assertIn("constraint_violations", d)
        self.assertIn("overall_status", d)
        self.assertIn("summary", d)

    def test_summary_is_optional(self):
        # Some models (e.g. openrouter-elephant-alpha) consistently omit
        # `summary` when producing structured output. summary is not consumed
        # downstream, so the field defaults to "" rather than raising.
        obj = ConstraintCheckResult.model_validate_json(
            '{"constraint_violations": [], "overall_status": "pass"}'
        )
        self.assertEqual(obj.summary, "")
        self.assertEqual(obj.overall_status, "pass")


class TestConstraintCheckerDataclass(unittest.TestCase):
    """Unit tests for the ConstraintChecker dataclass methods."""

    def _make_instance(self):
        return ConstraintChecker(
            system_prompt="system",
            user_prompt="user",
            response={
                "constraint_violations": [],
                "overall_status": "pass",
                "summary": "No violations.",
            },
            metadata={"duration": 1, "llm_classname": "MockLLM", "stage_name": "test"},
        )

    def test_to_dict_all(self):
        inst = self._make_instance()
        d = inst.to_dict()
        self.assertIn("constraint_violations", d)
        self.assertIn("overall_status", d)
        self.assertIn("metadata", d)
        self.assertIn("system_prompt", d)
        self.assertIn("user_prompt", d)

    def test_to_dict_exclude_metadata(self):
        inst = self._make_instance()
        d = inst.to_dict(include_metadata=False)
        self.assertNotIn("metadata", d)

    def test_to_dict_exclude_prompts(self):
        inst = self._make_instance()
        d = inst.to_dict(include_system_prompt=False, include_user_prompt=False)
        self.assertNotIn("system_prompt", d)
        self.assertNotIn("user_prompt", d)

    def test_metadata_has_stage_name(self):
        inst = self._make_instance()
        self.assertEqual(inst.metadata["stage_name"], "test")


def _get_test_llm():
    """Try to get a test LLM. Returns None if not available."""
    if not os.environ.get("RUN_LLM_TESTS"):
        return None
    try:
        from worker_plan_internal.llm_factory import get_llm
        llm_name = os.environ.get("TEST_LLM_NAME", "ollama-llama3.1")
        llm = get_llm(llm_name)
        return llm
    except Exception:
        return None


@unittest.skipUnless(_get_test_llm() is not None, "No LLM available for integration tests")
class TestConstraintCheckerWithLLM(unittest.TestCase):
    """Integration tests that use a real LLM."""

    @classmethod
    def setUpClass(cls):
        cls.llm = _get_test_llm()

    def test_detects_violation_in_stage_output(self):
        """Stage output containing banned words should be flagged as violated."""
        constraints = json.dumps({
            "constraints": [
                {"classification": "negative", "constraint_text": "Do not use VR"},
                {"classification": "negative", "constraint_text": "Do not use blockchain"},
                {"classification": "positive", "constraint_text": "Minecraft themed escape-room"},
            ]
        })
        stage_output = json.dumps({
            "levers": [
                {
                    "name": "Technology Integration",
                    "options": ["VR immersion rooms", "AR overlay guides", "Physical-only puzzles"],
                },
                {
                    "name": "Payment System",
                    "options": ["Blockchain-based tickets", "Traditional POS", "Mobile payments"],
                },
            ]
        })
        result = ConstraintChecker.execute(self.llm, constraints, stage_output, "test_levers")
        violations = result.response["constraint_violations"]

        # Should detect VR and blockchain violations
        violated_items = [v for v in violations if v["status"] == "violated"]
        violated_texts = " ".join(v["constraint_text"].lower() for v in violated_items)
        self.assertTrue("vr" in violated_texts, f"Expected VR violation, got: {violated_items}")
        self.assertTrue("blockchain" in violated_texts, f"Expected blockchain violation, got: {violated_items}")
        self.assertEqual(result.response["overall_status"], "fail")

    def test_clean_output_passes(self):
        """Stage output without banned words should pass."""
        constraints = json.dumps({
            "constraints": [
                {"classification": "negative", "constraint_text": "Do not use VR"},
                {"classification": "positive", "constraint_text": "Minecraft themed escape-room"},
            ]
        })
        stage_output = json.dumps({
            "levers": [
                {
                    "name": "Theme Design",
                    "options": ["Pixel art rooms", "Redstone puzzle mechanics", "Mob-themed challenges"],
                },
            ]
        })
        result = ConstraintChecker.execute(self.llm, constraints, stage_output, "test_levers")
        self.assertEqual(result.response["overall_status"], "pass")

    def test_response_structure(self):
        """Verify the response has the expected structure."""
        constraints = json.dumps({
            "constraints": [
                {"classification": "positive", "constraint_text": "Solar farm"},
            ]
        })
        stage_output = json.dumps({"levers": [{"name": "Energy Source", "options": ["Solar panels"]}]})
        result = ConstraintChecker.execute(self.llm, constraints, stage_output, "test_stage")
        self.assertIn("constraint_violations", result.response)
        self.assertIn("overall_status", result.response)
        self.assertIn("summary", result.response)
        self.assertIn(result.response["overall_status"], ["pass", "fail"])
        for v in result.response["constraint_violations"]:
            self.assertIn("constraint_text", v)
            self.assertIn("constraint_classification", v)
            self.assertIn("status", v)
            self.assertIn("evidence", v)
            self.assertIn("explanation", v)
        self.assertIn("stage_name", result.metadata)
        self.assertEqual(result.metadata["stage_name"], "test_stage")

    def test_detects_synonym_violations(self):
        """Banned concepts appearing under synonyms should still be flagged."""
        constraints = json.dumps({
            "constraints": [
                {"classification": "negative", "constraint_text": "Do not use blockchain"},
                {"classification": "negative", "constraint_text": "Do not use VR"},
            ]
        })
        # Uses synonyms: "distributed ledger" for blockchain, "virtual reality headset" for VR
        stage_output = json.dumps({
            "levers": [
                {
                    "name": "Transparency Layer",
                    "options": [
                        "Distributed ledger for audit trail",
                        "Traditional database with logging",
                        "Paper-based records",
                    ],
                },
                {
                    "name": "Immersive Experience",
                    "options": [
                        "Virtual reality headset stations",
                        "Large screen projections",
                        "Physical props only",
                    ],
                },
            ]
        })
        result = ConstraintChecker.execute(self.llm, constraints, stage_output, "test_synonyms")
        violations = result.response["constraint_violations"]

        violated_items = [v for v in violations if v["status"] == "violated"]
        self.assertTrue(
            len(violated_items) >= 2,
            f"Expected at least 2 synonym violations, got {len(violated_items)}: {violated_items}"
        )
        self.assertEqual(result.response["overall_status"], "fail")


if __name__ == "__main__":
    unittest.main()
