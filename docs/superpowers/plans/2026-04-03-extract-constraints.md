# Extract Constraints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new early-pipeline stage that extracts all explicit constraints from the user's prompt, classifying each as positive or negative, producing bullet-point-ready output for downstream LLM stages.

**Architecture:** Single structured LLM call following the same pattern as `physical_locations.py` — Pydantic models for structured output, `@dataclass` wrapper with `execute()` classmethod, pipeline stage wrapper extending `PlanTask`. Runs immediately after `screen_planning_prompt` in the pipeline.

**Tech Stack:** Python, Pydantic, llama_index, Luigi (via PlanTask)

**Spec:** `docs/superpowers/specs/2026-04-03-extract-constraints-design.md`

---

### Task 1: Create the diagnostic module with Pydantic models and dataclass

**Files:**
- Create: `worker_plan/worker_plan_internal/diagnostics/extract_constraints.py`

- [ ] **Step 1: Create the file with Pydantic models, system prompt, dataclass, and execute() method**

Create `worker_plan/worker_plan_internal/diagnostics/extract_constraints.py`:

```python
"""
Extract constraints from user prompt.

LLM-based extraction of explicit constraints from user prompts before plan
generation. Classifies each constraint as positive (things the user wants)
or negative (things the user wants to avoid). Output is a flat list of
self-contained, bullet-point-ready constraint items.

PROMPT> python -m worker_plan_internal.diagnostics.extract_constraints
"""
import time
from math import ceil
import logging
import json
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)


class ConstraintItem(BaseModel):
    """A single constraint extracted from the user's prompt."""
    classification: Literal["positive", "negative"] = Field(
        description=(
            "'positive' for things the user wants (goals, features, locations, budgets, timelines, technologies to use). "
            "'negative' for things the user wants to avoid (banned words, technologies to exclude, non-goals, hard limits)."
        )
    )
    constraint_text: str = Field(
        description=(
            "A short, self-contained bullet-point item describing the constraint. "
            "Must be understandable without the original prompt. "
            "For negative constraints, phrase as 'Do not use X' or 'Avoid X'."
        )
    )


class ConstraintExtractionResult(BaseModel):
    """Structured output for constraint extraction."""
    constraints: list[ConstraintItem] = Field(
        description="List of all explicit constraints found in the user's prompt. Empty list if none found."
    )


EXTRACT_CONSTRAINTS_SYSTEM_PROMPT = """
You are an expert at analyzing project descriptions to extract explicit constraints. Your job is to identify every constraint the user has stated in their prompt and classify it as positive or negative.

POSITIVE constraints are things the user WANTS in their project:
- Goals and objectives (e.g., "solar farm", "escape room")
- Locations (e.g., "Denmark", "Shanghai", "Silicon Valley")
- Target audiences (e.g., "kids aged 8-14")
- Budgets (e.g., "Budget: $200K", "$40 million USD")
- Timelines (e.g., "6 months", "24 months")
- Technologies or approaches to use (e.g., "open protocol")
- Specific requirements (e.g., "4 rooms", "60-90 min sessions")

NEGATIVE constraints are things the user wants to AVOID:
- Banned words or technologies (e.g., "Banned words: AR/VR/NFT/blockchain")
- Explicit prohibitions (e.g., "Don't use blockchain", "Don't use DAO")
- Non-goals (e.g., "MVP non-goals: multi-bloc federation, physical data centers")
- Hard limits not to violate (e.g., "No generic ROI fluff")
- Things to exclude (e.g., "avoid aggressive scenarios")

EXTRACTION RULES:
- Only extract constraints that are EXPLICITLY stated in the prompt. Do not infer or guess.
- For comma-separated lists like "Banned words: AR/VR/NFT/blockchain", extract each item as a SEPARATE negative constraint.
- Each constraint_text must be a short, self-contained bullet-point item that can be passed verbatim to another LLM as a checklist.
- For negative constraints, phrase as "Do not use X" or "Avoid X" so the intent is unambiguous.
- For positive constraints, use a short descriptive phrase.
- If the prompt contains no identifiable constraints, return an empty list.

Respond ONLY with a valid JSON object matching the ConstraintExtractionResult schema.
"""


@dataclass
class ExtractConstraints:
    """
    Extract and classify constraints from a user's project prompt.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str

    @classmethod
    def execute(cls, llm: LLM, user_prompt: str) -> "ExtractConstraints":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")

        logger.debug(f"User Prompt:\n{user_prompt}")

        system_prompt = EXTRACT_CONSTRAINTS_SYSTEM_PROMPT.strip()

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(ConstraintExtractionResult)
        start_time = time.perf_counter()
        try:
            chat_response = sllm.chat(chat_message_list)
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.debug(f"LLM chat interaction failed [{llm_error.error_id}]: {e}")
            logger.error(f"LLM chat interaction failed [{llm_error.error_id}]", exc_info=True)
            raise llm_error from e

        end_time = time.perf_counter()
        duration = int(ceil(end_time - start_time))
        raw_content = chat_response.message.content or ""
        response_byte_count = len(raw_content.encode('utf-8'))
        logger.info(
            f"LLM chat interaction completed in {duration} seconds. "
            f"Response byte count: {response_byte_count}"
        )

        pydantic_instance: ConstraintExtractionResult = chat_response.raw
        if pydantic_instance is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")
        json_response = pydantic_instance.model_dump()

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration"] = duration
        metadata["response_byte_count"] = response_byte_count

        markdown = cls.convert_to_markdown(pydantic_instance)

        return cls(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
            markdown=markdown,
        )

    def to_dict(
        self,
        include_metadata: bool = True,
        include_system_prompt: bool = True,
        include_user_prompt: bool = True,
    ) -> dict:
        d = self.response.copy()
        if include_metadata:
            d["metadata"] = self.metadata
        if include_system_prompt:
            d["system_prompt"] = self.system_prompt
        if include_user_prompt:
            d["user_prompt"] = self.user_prompt
        return d

    def save_raw(self, file_path: str) -> None:
        with open(file_path, 'w') as f:
            f.write(json.dumps(self.to_dict(), indent=2))

    @staticmethod
    def convert_to_markdown(extraction_result: ConstraintExtractionResult) -> str:
        if not isinstance(extraction_result, ConstraintExtractionResult):
            raise ValueError("Response must be a ConstraintExtractionResult object.")

        constraints = extraction_result.constraints
        if not constraints:
            return "No constraints identified."

        positive = [c for c in constraints if c.classification == "positive"]
        negative = [c for c in constraints if c.classification == "negative"]

        parts = []
        if positive:
            parts.append("## Positive Constraints\n")
            for c in positive:
                parts.append(f"- {c.constraint_text}")
            parts.append("")
        if negative:
            parts.append("## Negative Constraints\n")
            for c in negative:
                parts.append(f"- {c.constraint_text}")
            parts.append("")

        return "\n".join(parts)

    def save_markdown(self, file_path: str) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.markdown)


if __name__ == "__main__":
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_api.prompt_catalog import PromptCatalog

    llm = get_llm("ollama-llama3.1")

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()

    # Test with Minecraft escape-room prompt (has banned words)
    item = prompt_catalog.find_by_id("f717e0c0-73b4-4e12-8d1d-8ec426966122")
    if item:
        print(f"=== Prompt: {item.prompt[:80]}... ===")
        result = ExtractConstraints.execute(llm, item.prompt)
        json_response = result.to_dict(include_system_prompt=False, include_user_prompt=False, include_metadata=False)
        print(f"Response: {json.dumps(json_response, indent=2)}")
        print(f"\nMarkdown:\n{result.markdown}")

    # Test with simple prompt (no negative constraints)
    item = prompt_catalog.find_by_id("4dc34d55-0d0d-4e9d-92f4-23765f49dd29")
    if item:
        print(f"\n=== Prompt: {item.prompt} ===")
        result = ExtractConstraints.execute(llm, item.prompt)
        json_response = result.to_dict(include_system_prompt=False, include_user_prompt=False, include_metadata=False)
        print(f"Response: {json.dumps(json_response, indent=2)}")
        print(f"\nMarkdown:\n{result.markdown}")
```

- [ ] **Step 2: Verify the file is syntactically valid**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -c "import ast; ast.parse(open('worker_plan_internal/diagnostics/extract_constraints.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add worker_plan/worker_plan_internal/diagnostics/extract_constraints.py
git commit -m "Add extract_constraints diagnostic module with Pydantic models and system prompt"
```

---

### Task 2: Add unit tests for models, markdown conversion, and dataclass

**Files:**
- Create: `worker_plan/worker_plan_internal/diagnostics/tests/test_extract_constraints.py`

- [ ] **Step 1: Create the test file with unit tests**

Create `worker_plan/worker_plan_internal/diagnostics/tests/test_extract_constraints.py`:

```python
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
        item = pc.find_by_id("f717e0c0-73b4-4e12-8d1d-8ec426966122")
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
        item = pc.find_by_id("3ae1bcb2-4a59-49a6-8414-65a92f588016")
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
```

- [ ] **Step 2: Run unit tests to verify they pass**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/diagnostics/tests/test_extract_constraints.py -v -k "not LLM"`
Expected: All unit tests pass (TestConstraintItemModel, TestConstraintExtractionResultModel, TestConvertToMarkdown, TestExtractConstraintsDataclass)

- [ ] **Step 3: Run LLM integration tests**

Run: `cd worker_plan && RUN_LLM_TESTS=1 /opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/diagnostics/tests/test_extract_constraints.py -v -k "LLM"`
Expected: All LLM tests pass. If any fail, iterate on the system prompt in `extract_constraints.py` until they pass.

- [ ] **Step 4: Commit**

```bash
git add worker_plan/worker_plan_internal/diagnostics/tests/test_extract_constraints.py
git commit -m "Add unit and LLM integration tests for extract_constraints"
```

---

### Task 3: Register FilenameEnum entries

**Files:**
- Modify: `worker_plan/worker_plan_api/filenames.py:7-8` (insert after SCREEN_PLANNING_PROMPT entries)

- [ ] **Step 1: Add the two new enum entries**

In `worker_plan/worker_plan_api/filenames.py`, insert after line 8 (`SCREEN_PLANNING_PROMPT_MARKDOWN`):

```python
    EXTRACT_CONSTRAINTS_RAW = "002-0-extract_constraints_raw.json"
    EXTRACT_CONSTRAINTS_MARKDOWN = "002-0-extract_constraints.md"
```

- [ ] **Step 2: Verify syntax**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -c "from worker_plan_api.filenames import FilenameEnum; print(FilenameEnum.EXTRACT_CONSTRAINTS_RAW.value)"`
Expected: `002-0-extract_constraints_raw.json`

- [ ] **Step 3: Commit**

```bash
git add worker_plan/worker_plan_api/filenames.py
git commit -m "Add FilenameEnum entries for extract_constraints stage"
```

---

### Task 4: Create the pipeline stage wrapper

**Files:**
- Create: `worker_plan/worker_plan_internal/plan/nodes/extract_constraints.py`

- [ ] **Step 1: Create the stage file**

Create `worker_plan/worker_plan_internal/plan/nodes/extract_constraints.py`:

```python
"""Pipeline stage: extract constraints from user prompt."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.extract_constraints import ExtractConstraints
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask


class ExtractConstraintsTask(PlanTask):
    """
    Extract and classify constraints from the user's prompt.
    Produces a list of positive/negative constraint items.
    """
    def requires(self):
        return self.clone(SetupTask)

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.EXTRACT_CONSTRAINTS_RAW),
            'markdown': self.local_target(FilenameEnum.EXTRACT_CONSTRAINTS_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        with self.input().open("r") as f:
            plan_prompt = f.read()

        result = ExtractConstraints.execute(llm, plan_prompt)

        output_raw_path = self.output()['raw'].path
        result.save_raw(output_raw_path)
        output_markdown_path = self.output()['markdown'].path
        result.save_markdown(output_markdown_path)
```

- [ ] **Step 2: Verify syntax**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -c "import ast; ast.parse(open('worker_plan_internal/plan/nodes/extract_constraints.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/nodes/extract_constraints.py
git commit -m "Add ExtractConstraintsTask pipeline stage wrapper"
```

---

### Task 5: Wire into the full pipeline

**Files:**
- Modify: `worker_plan/worker_plan_internal/plan/nodes/full_plan_pipeline.py:10` (add import)
- Modify: `worker_plan/worker_plan_internal/plan/nodes/full_plan_pipeline.py:90-91` (add to requires dict)

- [ ] **Step 1: Add the import**

In `worker_plan/worker_plan_internal/plan/nodes/full_plan_pipeline.py`, add after line 10 (`from ... import ScreenPlanningPromptTask`):

```python
from worker_plan_internal.plan.nodes.extract_constraints import ExtractConstraintsTask
```

- [ ] **Step 2: Add to the requires() dict**

In the `requires()` method, add after the `'screen_planning_prompt'` entry (line 90):

```python
            'extract_constraints': self.clone(ExtractConstraintsTask),
```

- [ ] **Step 3: Verify syntax**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -c "from worker_plan_internal.plan.nodes.full_plan_pipeline import FullPlanPipeline; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/nodes/full_plan_pipeline.py
git commit -m "Register extract_constraints in the full plan pipeline"
```

---

### Task 6: Add to the report

**Files:**
- Modify: `worker_plan/worker_plan_internal/plan/nodes/report.py:28` (add import)
- Modify: `worker_plan/worker_plan_internal/plan/nodes/report.py:41-42` (add to requires dict)
- Modify: `worker_plan/worker_plan_internal/plan/nodes/report.py:90-91` (add append_markdown call)

- [ ] **Step 1: Add the import**

In `worker_plan/worker_plan_internal/plan/nodes/report.py`, add after line 28 (`from ... import ScreenPlanningPromptTask`):

```python
from worker_plan_internal.plan.nodes.extract_constraints import ExtractConstraintsTask
```

- [ ] **Step 2: Add to the requires() dict**

In the `requires()` method, add after the `'screen_planning_prompt'` entry (line 41):

```python
            'extract_constraints': self.clone(ExtractConstraintsTask),
```

- [ ] **Step 3: Add the report section**

In `run_inner()`, add after the Self Audit line (line 90, `rg.append_markdown_with_tables('Self Audit', ...)`):

```python
        rg.append_markdown('Constraints', self.input()['extract_constraints']['markdown'].path)
```

- [ ] **Step 4: Verify syntax**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -c "from worker_plan_internal.plan.nodes.report import ReportTask; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/nodes/report.py
git commit -m "Add extract_constraints to the HTML report"
```

---

### Task 7: Run all tests and verify end-to-end

**Files:** (no changes, verification only)

- [ ] **Step 1: Run unit tests**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/diagnostics/tests/test_extract_constraints.py -v -k "not LLM"`
Expected: All unit tests pass.

- [ ] **Step 2: Run LLM integration tests**

Run: `cd worker_plan && RUN_LLM_TESTS=1 /opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/diagnostics/tests/test_extract_constraints.py -v`
Expected: All tests pass (unit + LLM integration).

- [ ] **Step 3: Run the existing screen_planning_prompt tests to verify no regressions**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/diagnostics/tests/test_screen_planning_prompt.py -v -k "not LLM"`
Expected: All 18 unit tests pass.

- [ ] **Step 4: Run the diagnostic module directly to see output**

Run: `cd worker_plan && /opt/homebrew/bin/python3.11 -m worker_plan_internal.diagnostics.extract_constraints`
Expected: Prints extracted constraints for the Minecraft escape-room prompt (with negative constraints for AR/VR/NFT/blockchain) and the solar farm prompt (positive constraints only).
