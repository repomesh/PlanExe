"""
Tests for extract_constraints module.

Unit tests for ConstraintItem, ConstraintExtractionResult, and ExtractConstraints.
Integration tests that use a real LLM to verify constraint extraction.

Unit tests (no LLM, safe for CI):
PROMPT> cd worker_plan && python -m pytest worker_plan_internal/diagnostics/tests/test_extract_constraints.py -v -k "not LLM"

LLM integration tests (requires RUN_LLM_TESTS=1, local development only):
PROMPT> cd worker_plan && RUN_LLM_TESTS=1 python -m pytest worker_plan_internal/diagnostics/tests/test_extract_constraints.py -v -k "LLM"
"""
import unittest
import os

from worker_plan_internal.diagnostics.extract_constraints import (
    ConstraintItem,
    ConstraintExtractionResult,
    ExtractConstraints,
)


class TestConstraintItemModel(unittest.TestCase):
    """Unit tests for the ConstraintItem Pydantic model."""

    def test_positive_constraint(self):
        obj = ConstraintItem(classification="positive", constraint_text="Solar farm")
        self.assertEqual(obj.classification, "positive")
        self.assertEqual(obj.constraint_text, "Solar farm")

    def test_negative_constraint(self):
        obj = ConstraintItem(classification="negative", constraint_text="Do not use blockchain")
        self.assertEqual(obj.classification, "negative")
        self.assertEqual(obj.constraint_text, "Do not use blockchain")

    def test_invalid_classification_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ConstraintItem(classification="neutral", constraint_text="Something")

    def test_model_dump(self):
        obj = ConstraintItem(classification="positive", constraint_text="Denmark")
        d = obj.model_dump()
        self.assertEqual(d["classification"], "positive")
        self.assertEqual(d["constraint_text"], "Denmark")


class TestConstraintExtractionResultModel(unittest.TestCase):
    """Unit tests for the ConstraintExtractionResult Pydantic model."""

    def test_empty_constraints(self):
        obj = ConstraintExtractionResult(constraints=[])
        self.assertEqual(obj.constraints, [])

    def test_with_constraints(self):
        items = [
            ConstraintItem(classification="positive", constraint_text="Solar farm"),
            ConstraintItem(classification="negative", constraint_text="Do not use NFT"),
        ]
        obj = ConstraintExtractionResult(constraints=items)
        self.assertEqual(len(obj.constraints), 2)
        self.assertEqual(obj.constraints[0].classification, "positive")
        self.assertEqual(obj.constraints[1].classification, "negative")

    def test_model_dump(self):
        items = [
            ConstraintItem(classification="positive", constraint_text="Budget: $200K"),
        ]
        obj = ConstraintExtractionResult(constraints=items)
        d = obj.model_dump()
        self.assertIn("constraints", d)
        self.assertEqual(len(d["constraints"]), 1)
        self.assertEqual(d["constraints"][0]["classification"], "positive")


class TestConvertToMarkdown(unittest.TestCase):
    """Unit tests for the markdown conversion."""

    def test_empty_constraints(self):
        obj = ConstraintExtractionResult(constraints=[])
        md = ExtractConstraints.convert_to_markdown(obj)
        self.assertEqual(md, "No constraints identified.")

    def test_positive_only(self):
        obj = ConstraintExtractionResult(constraints=[
            ConstraintItem(classification="positive", constraint_text="Solar farm"),
            ConstraintItem(classification="positive", constraint_text="Denmark"),
        ])
        md = ExtractConstraints.convert_to_markdown(obj)
        self.assertIn("## Positive Constraints", md)
        self.assertIn("- Solar farm", md)
        self.assertIn("- Denmark", md)
        self.assertNotIn("## Negative Constraints", md)

    def test_negative_only(self):
        obj = ConstraintExtractionResult(constraints=[
            ConstraintItem(classification="negative", constraint_text="Do not use blockchain"),
        ])
        md = ExtractConstraints.convert_to_markdown(obj)
        self.assertIn("## Negative Constraints", md)
        self.assertIn("- Do not use blockchain", md)
        self.assertNotIn("## Positive Constraints", md)

    def test_mixed(self):
        obj = ConstraintExtractionResult(constraints=[
            ConstraintItem(classification="positive", constraint_text="Copenhagen"),
            ConstraintItem(classification="negative", constraint_text="Do not use AR/VR"),
        ])
        md = ExtractConstraints.convert_to_markdown(obj)
        self.assertIn("## Positive Constraints", md)
        self.assertIn("## Negative Constraints", md)
        self.assertIn("- Copenhagen", md)
        self.assertIn("- Do not use AR/VR", md)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            ExtractConstraints.convert_to_markdown("not a result object")


class TestExtractConstraintsDataclass(unittest.TestCase):
    """Unit tests for the ExtractConstraints dataclass methods."""

    def _make_instance(self):
        return ExtractConstraints(
            system_prompt="system",
            user_prompt="user",
            response={"constraints": [{"classification": "positive", "constraint_text": "Test"}]},
            metadata={"duration": 1, "llm_classname": "MockLLM"},
            markdown="## Positive Constraints\n\n- Test\n",
        )

    def test_to_dict_all(self):
        inst = self._make_instance()
        d = inst.to_dict()
        self.assertIn("constraints", d)
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


def _get_test_llm():
    """Try to get a test LLM. Returns None if not available.

    Requires RUN_LLM_TESTS=1 environment variable to be set.

    Usage:
        RUN_LLM_TESTS=1 python -m pytest ... -k "LLM"
    """
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
class TestExtractConstraintsWithLLM(unittest.TestCase):
    """Integration tests that use a real LLM."""

    @classmethod
    def setUpClass(cls):
        cls.llm = _get_test_llm()

    def test_prompt_with_banned_words(self):
        """Minecraft escape-room prompt should extract negative constraints for banned words."""
        from worker_plan_api.prompt_catalog import PromptCatalog
        pc = PromptCatalog()
        pc.load_simple_plan_prompts()
        item = pc.find("f717e0c0-73b4-4e12-8d1d-8ec426966122")
        self.assertIsNotNone(item, "Minecraft escape-room prompt not found in catalog")

        result = ExtractConstraints.execute(self.llm, item.prompt)
        constraints = result.response["constraints"]

        negative_texts = [
            c["constraint_text"].lower()
            for c in constraints
            if c["classification"] == "negative"
        ]
        negative_joined = " ".join(negative_texts)

        # Should have negative constraints for the banned words
        for banned in ["ar", "vr", "nft", "blockchain"]:
            self.assertTrue(
                banned in negative_joined,
                f"Expected banned word '{banned}' in negative constraints, got: {negative_texts}"
            )

        # Should have positive constraints too
        positive_texts = [
            c["constraint_text"].lower()
            for c in constraints
            if c["classification"] == "positive"
        ]
        self.assertTrue(len(positive_texts) > 0, "Expected at least one positive constraint")

    def test_prompt_with_dont_use(self):
        """HaaS prompt with 'Don't use blockchain/DAO' should extract negative constraints."""
        from worker_plan_api.prompt_catalog import PromptCatalog
        pc = PromptCatalog()
        pc.load_simple_plan_prompts()
        item = pc.find("3ae1bcb2-4a59-49a6-8414-65a92f588016")
        self.assertIsNotNone(item, "HaaS prompt not found in catalog")

        result = ExtractConstraints.execute(self.llm, item.prompt)
        constraints = result.response["constraints"]

        negative_texts = [
            c["constraint_text"].lower()
            for c in constraints
            if c["classification"] == "negative"
        ]
        negative_joined = " ".join(negative_texts)

        for banned in ["blockchain", "dao"]:
            self.assertTrue(
                banned in negative_joined,
                f"Expected '{banned}' in negative constraints, got: {negative_texts}"
            )

    def test_simple_prompt_positive_only(self):
        """'Establish a solar farm in Denmark' should produce positive constraints, no negative."""
        result = ExtractConstraints.execute(self.llm, "Establish a solar farm in Denmark")
        constraints = result.response["constraints"]

        positive_texts = [
            c["constraint_text"].lower()
            for c in constraints
            if c["classification"] == "positive"
        ]
        negative_texts = [
            c["constraint_text"]
            for c in constraints
            if c["classification"] == "negative"
        ]

        positive_joined = " ".join(positive_texts)
        self.assertTrue("solar" in positive_joined, f"Expected 'solar' in positive constraints, got: {positive_texts}")
        self.assertTrue("denmark" in positive_joined, f"Expected 'denmark' in positive constraints, got: {positive_texts}")
        self.assertEqual(len(negative_texts), 0, f"Expected no negative constraints, got: {negative_texts}")

    def test_response_structure(self):
        """Verify the response has the expected structure."""
        result = ExtractConstraints.execute(self.llm, "Build a factory in Cleveland. Budget: $10M.")
        self.assertIn("constraints", result.response)
        self.assertIsInstance(result.response["constraints"], list)
        for c in result.response["constraints"]:
            self.assertIn("classification", c)
            self.assertIn("constraint_text", c)
            self.assertIn(c["classification"], ["positive", "negative"])
        self.assertIn("duration", result.metadata)
        self.assertIn("llm_classname", result.metadata)
        self.assertIsInstance(result.markdown, str)
        self.assertTrue(len(result.markdown) > 0)


if __name__ == "__main__":
    unittest.main()
