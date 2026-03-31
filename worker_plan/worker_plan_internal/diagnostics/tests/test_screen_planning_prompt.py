"""
Tests for screen_planning_prompt module.

Unit tests for compute_prompt_stats and PromptScreeningResult model.
Integration tests that use a real LLM to verify prompt screening.

Unit tests (no LLM, safe for CI):
PROMPT> cd worker_plan && python -m pytest worker_plan_internal/diagnostics/tests/test_screen_planning_prompt.py -v -k "not LLM"

LLM integration tests (requires RUN_LLM_TESTS=1, local development only):
PROMPT> cd worker_plan && RUN_LLM_TESTS=1 python -m pytest worker_plan_internal/diagnostics/tests/test_screen_planning_prompt.py -v -k "LLM"
"""
import unittest
import os

from worker_plan_internal.diagnostics.screen_planning_prompt import (
    compute_prompt_stats,
    PromptScreeningResult,
    ScreenPlanningPrompt,
)


class TestComputePromptStats(unittest.TestCase):
    """Unit tests for the compute_prompt_stats helper function."""

    def test_empty_string(self):
        result = compute_prompt_stats("")
        self.assertIn("Byte count: 0", result)
        self.assertIn("Character count: 0", result)
        self.assertIn("Word count: 0", result)
        self.assertIn("Line count: 0", result)
        self.assertIn("Symbol count: 0", result)

    def test_single_word(self):
        result = compute_prompt_stats("hello")
        self.assertIn("Byte count: 5", result)
        self.assertIn("Character count: 5", result)
        self.assertIn("Word count: 1", result)
        self.assertIn("Line count: 1", result)
        self.assertIn("Symbol count: 0", result)

    def test_multiline(self):
        result = compute_prompt_stats("line1\nline2\nline3")
        self.assertIn("Line count: 3", result)
        self.assertIn("Word count: 3", result)

    def test_symbols(self):
        result = compute_prompt_stats("hello! @world# $$$")
        self.assertIn("Symbol count: 6", result)

    def test_unicode(self):
        # Danish character ø is 2 bytes in UTF-8
        result = compute_prompt_stats("København")
        self.assertIn("Character count: 9", result)
        # ø is 2 bytes, so total = 8 + 2 = 10
        self.assertIn("Byte count: 10", result)

    def test_whitespace_only(self):
        result = compute_prompt_stats("   \n\n   ")
        self.assertIn("Word count: 0", result)
        self.assertIn("Line count: 3", result)
        self.assertIn("Symbol count: 0", result)

    def test_realistic_prompt(self):
        prompt = "Establish a solar farm in Denmark. Budget: $5M. Timeline: 18 months."
        result = compute_prompt_stats(prompt)
        self.assertIn("Word count: 11", result)
        self.assertIn("Line count: 1", result)


class TestPromptScreeningResultModel(unittest.TestCase):
    """Unit tests for the PromptScreeningResult Pydantic model."""

    def test_usable_verdict(self):
        obj = PromptScreeningResult(
            verdict="USABLE",
            reason="usable",
            confidence="high",
            rationale="This prompt describes a concrete project with location and budget.",
        )
        self.assertEqual(obj.verdict, "USABLE")
        self.assertEqual(obj.reason, "usable")

    def test_unusable_verdict(self):
        obj = PromptScreeningResult(
            verdict="UNUSABLE",
            reason="too_short",
            confidence="high",
            rationale="The prompt is only one word.",
        )
        self.assertEqual(obj.verdict, "UNUSABLE")
        self.assertEqual(obj.reason, "too_short")

    def test_all_reasons(self):
        reasons = [
            "usable",
            "too_short",
            "nonsensical",
            "placeholder_or_test",
            "no_actionable_goal",
            "vague_wishful_thinking",
            "fictional_or_impossible",
            "prompt_injection",
        ]
        for reason in reasons:
            obj = PromptScreeningResult(
                verdict="UNUSABLE" if reason != "usable" else "USABLE",
                reason=reason,
                confidence="medium",
                rationale="Test.",
            )
            self.assertEqual(obj.reason, reason)

    def test_model_dump(self):
        obj = PromptScreeningResult(
            verdict="USABLE",
            reason="usable",
            confidence="high",
            rationale="Good prompt.",
        )
        d = obj.model_dump()
        self.assertIn("verdict", d)
        self.assertIn("reason", d)
        self.assertIn("confidence", d)
        self.assertIn("rationale", d)

    def test_invalid_verdict_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PromptScreeningResult(
                verdict="MAYBE",
                reason="usable",
                confidence="high",
                rationale="Test.",
            )

    def test_invalid_reason_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            PromptScreeningResult(
                verdict="UNUSABLE",
                reason="unknown_reason",
                confidence="high",
                rationale="Test.",
            )


class TestConvertToMarkdown(unittest.TestCase):
    """Unit tests for the markdown conversion."""

    def test_usable_verdict_markdown(self):
        obj = PromptScreeningResult(
            verdict="USABLE",
            reason="usable",
            confidence="high",
            rationale="Concrete project with real location.",
        )
        md = ScreenPlanningPrompt.convert_to_markdown(obj)
        self.assertIn("USABLE", md)
        self.assertIn("Concrete project with real location.", md)
        # Should NOT have details table for USABLE
        self.assertNotIn("### Details", md)

    def test_unusable_verdict_markdown(self):
        obj = PromptScreeningResult(
            verdict="UNUSABLE",
            reason="too_short",
            confidence="high",
            rationale="The prompt is too brief.",
        )
        md = ScreenPlanningPrompt.convert_to_markdown(obj)
        self.assertIn("UNUSABLE", md)
        self.assertIn("### Details", md)
        self.assertIn("Too Short", md)
        self.assertIn("High", md)


class TestScreenPlanningPromptDataclass(unittest.TestCase):
    """Unit tests for the ScreenPlanningPrompt dataclass methods."""

    def _make_instance(self):
        return ScreenPlanningPrompt(
            system_prompt="system",
            user_prompt="user",
            response={"verdict": "USABLE", "reason": "usable", "confidence": "high", "rationale": "Good."},
            metadata={"duration": 1, "llm_classname": "MockLLM"},
            markdown="**Verdict:** USABLE",
        )

    def test_to_dict_all(self):
        inst = self._make_instance()
        d = inst.to_dict()
        self.assertIn("verdict", d)
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
    This prevents accidental LLM invocations in CI which would be costly.

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


def _get_good_prompts():
    """Get the 10 longest prompts from the catalog (should be classified as USABLE)."""
    from worker_plan_api.prompt_catalog import PromptCatalog
    pc = PromptCatalog()
    pc.load_simple_plan_prompts()
    items = pc.all()
    sorted_items = sorted(items, key=lambda x: len(x.prompt), reverse=True)
    return sorted_items[:10]


# The set of all known reason values — used to extract acceptable reasons from tags.
ALL_REASONS = {
    "usable", "too_short", "nonsensical", "placeholder_or_test",
    "no_actionable_goal", "vague_wishful_thinking", "fictional_or_impossible",
    "prompt_injection",
}


def _load_unusable_prompts():
    """Load unusable prompts from the JSONL catalog."""
    from worker_plan_api.prompt_catalog import PromptCatalog
    pc = PromptCatalog()
    pc.load_unusable_prompts()
    return pc


def _get_core_unusable_prompts():
    """Core tier: unambiguously unusable, assert both verdict and reason.

    Returns list of (prompt_text, acceptable_reasons_set) tuples.
    Acceptable reasons are extracted from tags by intersecting with ALL_REASONS.
    """
    pc = _load_unusable_prompts()
    items = pc.find_by_tag("core")
    result = []
    for item in items:
        acceptable_reasons = set(item.tags) & ALL_REASONS
        result.append((item.prompt, acceptable_reasons))
    return result


def _get_robustness_unusable_prompts():
    """Robustness tier: verdict should always be UNUSABLE, reason may vary.

    Returns list of prompt strings.
    """
    pc = _load_unusable_prompts()
    return [item.prompt for item in pc.find_by_tag("robustness")]


def _get_borderline_unusable_prompts():
    """Borderline tier: plausible but too vague. Tested separately.

    Returns list of prompt strings.
    """
    pc = _load_unusable_prompts()
    return [item.prompt for item in pc.find_by_tag("borderline")]


@unittest.skipUnless(_get_test_llm() is not None, "No LLM available for integration tests")
class TestScreenPlanningPromptWithLLM(unittest.TestCase):
    """Integration tests that use a real LLM."""

    @classmethod
    def setUpClass(cls):
        cls.llm = _get_test_llm()

    def test_good_prompts_are_usable(self):
        """The 10 longest prompts from simple_plan_prompts.jsonl should all be classified as USABLE."""
        good_prompts = _get_good_prompts()
        failures = []
        for item in good_prompts:
            try:
                result = ScreenPlanningPrompt.execute(self.llm, item.prompt)
                verdict = result.response["verdict"]
                if verdict != "USABLE":
                    failures.append(
                        f"Prompt {item.id} (len={len(item.prompt)}) was classified as "
                        f"{verdict} ({result.response['reason']}): "
                        f"{result.response['rationale']}"
                    )
            except Exception as e:
                failures.append(f"Prompt {item.id} raised exception: {e}")
        if failures:
            self.fail(
                f"{len(failures)} of {len(good_prompts)} good prompts were misclassified:\n"
                + "\n".join(failures)
            )

    def test_core_unusable_prompts_are_detected(self):
        """Core unusable prompts must be classified as UNUSABLE with an acceptable reason."""
        core_prompts = _get_core_unusable_prompts()
        failures = []
        for prompt_text, acceptable_reasons in core_prompts:
            try:
                result = ScreenPlanningPrompt.execute(self.llm, prompt_text)
                verdict = result.response["verdict"]
                actual_reason = result.response["reason"]
                if verdict != "UNUSABLE":
                    failures.append(
                        f"Prompt {prompt_text!r} was classified as {verdict} "
                        f"instead of UNUSABLE: {result.response['rationale']}"
                    )
                elif actual_reason not in acceptable_reasons:
                    failures.append(
                        f"Prompt {prompt_text!r} reason was {actual_reason!r} "
                        f"not in {acceptable_reasons!r}: {result.response['rationale']}"
                    )
            except Exception as e:
                failures.append(f"Prompt {prompt_text!r} raised exception: {e}")
        if failures:
            self.fail(
                f"{len(failures)} of {len(core_prompts)} core unusable prompts failed:\n"
                + "\n".join(failures)
            )

    def test_robustness_unusable_prompts_are_detected(self):
        """Robustness unusable prompts must be classified as UNUSABLE (reason may vary)."""
        robustness_prompts = _get_robustness_unusable_prompts()
        failures = []
        for prompt_text in robustness_prompts:
            try:
                result = ScreenPlanningPrompt.execute(self.llm, prompt_text)
                verdict = result.response["verdict"]
                if verdict != "UNUSABLE":
                    failures.append(
                        f"Prompt {prompt_text!r} was classified as {verdict} "
                        f"instead of UNUSABLE: {result.response['rationale']}"
                    )
            except Exception as e:
                failures.append(f"Prompt {prompt_text!r} raised exception: {e}")
        if failures:
            self.fail(
                f"{len(failures)} of {len(robustness_prompts)} robustness unusable prompts were misclassified:\n"
                + "\n".join(failures)
            )

    def test_borderline_unusable_prompts(self):
        """Borderline prompts — plausible but too vague. Tested separately to avoid masking regressions."""
        borderline_prompts = _get_borderline_unusable_prompts()
        failures = []
        for prompt_text in borderline_prompts:
            try:
                result = ScreenPlanningPrompt.execute(self.llm, prompt_text)
                verdict = result.response["verdict"]
                if verdict != "UNUSABLE":
                    failures.append(
                        f"Prompt {prompt_text!r} was classified as {verdict} "
                        f"instead of UNUSABLE: {result.response['rationale']}"
                    )
            except Exception as e:
                failures.append(f"Prompt {prompt_text!r} raised exception: {e}")
        if failures:
            self.fail(
                f"{len(failures)} of {len(borderline_prompts)} borderline unusable prompts were misclassified:\n"
                + "\n".join(failures)
            )

    def test_response_structure(self):
        """Verify the response has the expected structure."""
        result = ScreenPlanningPrompt.execute(self.llm, "blah")
        self.assertIn("verdict", result.response)
        self.assertIn("reason", result.response)
        self.assertIn("confidence", result.response)
        self.assertIn("rationale", result.response)
        self.assertIn("duration", result.metadata)
        self.assertIn("llm_classname", result.metadata)
        self.assertIsInstance(result.markdown, str)
        self.assertTrue(len(result.markdown) > 0)


if __name__ == "__main__":
    unittest.main()
