# Prompt Adherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pipeline step that checks the final plan against the original user prompt and produces a scored report showing which user directives were honored, softened, or ignored.

**Architecture:** Two-phase LLM approach (extract directives, then score each against the plan). Follows the same pattern as `premortem.py`: Pydantic structured output, `LLMExecutor` for model fallback, dataclass for results with `save_raw`/`save_markdown` methods. Luigi task wired after `self_audit`, before `report`.

**Tech Stack:** Python 3.13, llama-index (structured LLM output), Pydantic v2, Luigi

---

## File Structure

```
worker_plan/worker_plan_internal/
    diagnostics/
        prompt_adherence.py              — Phase 1 + Phase 2 logic, Pydantic models, markdown generation
        tests/
            test_prompt_adherence.py      — Unit tests for Pydantic models and markdown generation
    plan/nodes/
        prompt_adherence.py              — Luigi task (PromptAdherenceTask)
worker_plan/worker_plan_api/
    filenames.py                         — Add PROMPT_ADHERENCE_RAW, PROMPT_ADHERENCE_MARKDOWN
```

---

### Task 1: FilenameEnum entries

**Files:**
- Modify: `worker_plan/worker_plan_api/filenames.py`

- [ ] **Step 1: Add filename entries**

Add after the `SELF_AUDIT_MARKDOWN` line:

```python
    PROMPT_ADHERENCE_RAW = "prompt_adherence_raw.json"
    PROMPT_ADHERENCE_MARKDOWN = "prompt_adherence.md"
```

- [ ] **Step 2: Verify import works**

Run: `cd worker_plan && .venv/bin/python -c "from worker_plan_api.filenames import FilenameEnum; print(FilenameEnum.PROMPT_ADHERENCE_RAW.value)"`
Expected: `prompt_adherence_raw.json`

- [ ] **Step 3: Commit**

```bash
git add worker_plan/worker_plan_api/filenames.py
git commit -m "feat: add FilenameEnum entries for prompt adherence"
```

---

### Task 2: Pydantic models and prompt logic

**Files:**
- Create: `worker_plan/worker_plan_internal/diagnostics/prompt_adherence.py`
- Create: `worker_plan/worker_plan_internal/diagnostics/tests/test_prompt_adherence.py`

- [ ] **Step 1: Write the failing tests**

```python
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
        # D1: importance=5, adherence=5 -> weighted=25
        # D2: importance=5, adherence=1 -> weighted=5
        # total weighted = 30, max = 50, score = 60%
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker_plan && .venv/bin/python -m pytest worker_plan_internal/diagnostics/tests/test_prompt_adherence.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement prompt_adherence.py**

```python
# worker_plan/worker_plan_internal/diagnostics/prompt_adherence.py
"""
Prompt Adherence: check how faithfully the final plan follows the original user prompt.

Phase 1: Extract directives (constraints, stated facts, requirements, banned words, intent) from plan.txt.
Phase 2: Score each directive against the final plan artifacts.

PROMPT> python -m worker_plan_internal.diagnostics.prompt_adherence
"""
import json
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)


# -- Pydantic models for Phase 1: Directive Extraction -------------------------

class DirectiveType(str, Enum):
    CONSTRAINT = "constraint"
    STATED_FACT = "stated_fact"
    REQUIREMENT = "requirement"
    BANNED = "banned"
    INTENT = "intent"


class Directive(BaseModel):
    directive_id: str = Field(description="Enumerate as 'D1', 'D2', 'D3', etc.")
    directive_type: DirectiveType = Field(description=(
        "constraint: explicit numeric or scope limits (budget, timeline, capacity). "
        "stated_fact: things the user says are already true about the world. "
        "requirement: what must be built or done. "
        "banned: words, approaches, or technologies the user explicitly prohibits. "
        "intent: the user's posture, tone, or implied expectations about execution vs. study."
    ))
    text: str = Field(description="The user's words — short quote or close paraphrase (under 100 chars).")
    importance_5: int = Field(description="1 (minor detail) to 5 (core requirement). Rate how central this is to the user's request.")


class DirectiveExtractionResult(BaseModel):
    directives: List[Directive] = Field(description="5-15 directives extracted from the user's prompt.")


# -- Pydantic models for Phase 2: Adherence Scoring ---------------------------

class AdherenceCategory(str, Enum):
    FULLY_HONORED = "fully_honored"
    PARTIALLY_HONORED = "partially_honored"
    SOFTENED = "softened"
    IGNORED = "ignored"
    CONTRADICTED = "contradicted"
    UNSOLICITED_CAVEAT = "unsolicited_caveat"


class AdherenceResult(BaseModel):
    directive_id: str = Field(description="References a directive from Phase 1.")
    adherence_5: int = Field(description="1 (ignored/contradicted) to 5 (fully honored).")
    category: AdherenceCategory = Field(description=(
        "fully_honored: plan respects this exactly. "
        "partially_honored: plan addresses it but incompletely. "
        "softened: plan weakens the requirement. "
        "ignored: plan doesn't address it at all. "
        "contradicted: plan says the opposite. "
        "unsolicited_caveat: plan adds qualifications the user didn't ask for."
    ))
    evidence: str = Field(description="Direct quote from the plan (under 200 chars).")
    explanation: str = Field(description="How the plan handled this directive and why this score was given.")


class AdherenceScoreResult(BaseModel):
    results: List[AdherenceResult] = Field(description="One scoring result per directive from Phase 1.")


# -- System prompts ------------------------------------------------------------

EXTRACT_DIRECTIVES_SYSTEM_PROMPT = """\
You are analyzing the original user prompt for a project planning pipeline.

Your job is to extract the user's directives — the things the plan MUST respect. \
These are the user's stated constraints, facts about the world, requirements, \
banned items, and implied intent.

Focus on things that are easy for a planning pipeline to dilute:
- Stated facts about the current state of the world (e.g., "the building is already demolished")
- Hard numeric constraints (budget, timeline, capacity)
- Explicit scope boundaries (what to build, what NOT to build)
- Banned words or approaches
- The user's posture: are they saying "execute this" or "study whether to do this"?

Extract 5-15 directives. Prioritize specificity over quantity. \
Rate importance from 1 (minor detail) to 5 (core requirement).

Do NOT extract generic project management advice. \
Only extract what the USER specifically stated or clearly implied.
"""

SCORE_ADHERENCE_SYSTEM_PROMPT = """\
You are checking whether a project plan faithfully follows the user's original directives.

You will receive:
1. The user's original prompt
2. A list of extracted directives (what the user asked for)
3. The final plan artifacts

For each directive, score how well the plan honored it:
- adherence_5: 1 (ignored or contradicted) to 5 (fully honored)
- category: what happened to this directive in the plan
- evidence: quote from the plan (under 200 chars) showing how it was handled
- explanation: why you gave this score

Be strict. The user wrote their prompt for a reason. If the plan softens \
"100% renewable" to "aim for 60-80%", that is SOFTENED, not PARTIALLY_HONORED. \
If the user says "the East Wing is already demolished" and the plan includes \
demolition permitting, that is CONTRADICTED.

Plans that add feasibility studies, risk disclaimers, or scope reductions that \
the user didn't ask for should be flagged as UNSOLICITED_CAVEAT.

Plans that use generic project management boilerplate instead of addressing \
the specific problem should score low on adherence.
"""


# -- Business logic ------------------------------------------------------------

@dataclass
class PromptAdherence:
    system_prompt_phase1: str
    system_prompt_phase2: str
    user_prompt: str
    directives: dict
    scores: dict
    metadata: dict
    markdown: str

    @classmethod
    def execute(cls, llm_executor: LLMExecutor, plan_prompt: str, plan_context: str) -> 'PromptAdherence':
        if not isinstance(llm_executor, LLMExecutor):
            raise ValueError("Invalid LLMExecutor instance.")
        if not isinstance(plan_prompt, str):
            raise ValueError("Invalid plan_prompt.")
        if not isinstance(plan_context, str):
            raise ValueError("Invalid plan_context.")

        system_prompt_phase1 = EXTRACT_DIRECTIVES_SYSTEM_PROMPT.strip()
        system_prompt_phase2 = SCORE_ADHERENCE_SYSTEM_PROMPT.strip()

        # Phase 1: Extract directives from the original prompt
        logger.info("Prompt Adherence Phase 1: Extracting directives from plan prompt...")
        phase1_messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt_phase1),
            ChatMessage(role=MessageRole.USER, content=f"User's original prompt:\n{plan_prompt}"),
        ]

        def execute_phase1(llm: LLM) -> dict:
            sllm = llm.as_structured_llm(DirectiveExtractionResult)
            chat_response = sllm.chat(phase1_messages)
            metadata = dict(llm.metadata)
            metadata["llm_classname"] = llm.class_name()
            return {"pydantic_response": chat_response.raw, "metadata": metadata}

        try:
            phase1_result = llm_executor.run(execute_phase1)
        except PipelineStopRequested:
            raise
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.error(f"Phase 1 failed [{llm_error.error_id}]", exc_info=True)
            raise llm_error from e

        extraction: DirectiveExtractionResult = phase1_result["pydantic_response"]
        logger.info(f"Phase 1 complete: extracted {len(extraction.directives)} directives.")

        # Phase 2: Score each directive against the plan
        logger.info("Prompt Adherence Phase 2: Scoring directives against final plan...")
        directives_json = json.dumps(extraction.model_dump(), indent=2)
        phase2_messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt_phase2),
            ChatMessage(role=MessageRole.USER, content=(
                f"User's original prompt:\n{plan_prompt}\n\n"
                f"Extracted directives:\n{directives_json}\n\n"
                f"Final plan artifacts:\n{plan_context}"
            )),
        ]

        def execute_phase2(llm: LLM) -> dict:
            sllm = llm.as_structured_llm(AdherenceScoreResult)
            chat_response = sllm.chat(phase2_messages)
            metadata = dict(llm.metadata)
            metadata["llm_classname"] = llm.class_name()
            return {"pydantic_response": chat_response.raw, "metadata": metadata}

        try:
            phase2_result = llm_executor.run(execute_phase2)
        except PipelineStopRequested:
            raise
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.error(f"Phase 2 failed [{llm_error.error_id}]", exc_info=True)
            raise llm_error from e

        scoring: AdherenceScoreResult = phase2_result["pydantic_response"]
        logger.info(f"Phase 2 complete: scored {len(scoring.results)} directives.")

        metadata = {
            "phase1": phase1_result["metadata"],
            "phase2": phase2_result["metadata"],
        }
        markdown = cls.convert_to_markdown(extraction, scoring)

        return PromptAdherence(
            system_prompt_phase1=system_prompt_phase1,
            system_prompt_phase2=system_prompt_phase2,
            user_prompt=plan_prompt,
            directives=extraction.model_dump(),
            scores=scoring.model_dump(),
            metadata=metadata,
            markdown=markdown,
        )

    def to_dict(self, include_metadata=True, include_system_prompt=True, include_user_prompt=True, include_markdown=True) -> dict:
        d = {
            "directives": self.directives,
            "scores": self.scores,
        }
        if include_metadata:
            d["metadata"] = self.metadata
        if include_system_prompt:
            d["system_prompt_phase1"] = self.system_prompt_phase1
            d["system_prompt_phase2"] = self.system_prompt_phase2
        if include_user_prompt:
            d["user_prompt"] = self.user_prompt
        if include_markdown:
            d["markdown"] = self.markdown
        return d

    def save_raw(self, file_path: str) -> None:
        with open(file_path, 'w') as f:
            f.write(json.dumps(self.to_dict(), indent=2))

    def save_markdown(self, output_file_path: str) -> None:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(self.markdown)

    @staticmethod
    def calculate_overall_score(directives: DirectiveExtractionResult, scores: AdherenceScoreResult) -> int:
        """Weighted average: sum(adherence_5 * importance_5) / sum(5 * importance_5) as integer percentage."""
        if not directives.directives:
            return 100
        importance_map = {d.directive_id: d.importance_5 for d in directives.directives}
        weighted_sum = 0
        max_sum = 0
        for r in scores.results:
            importance = importance_map.get(r.directive_id, 3)
            weighted_sum += r.adherence_5 * importance
            max_sum += 5 * importance
        if max_sum == 0:
            return 100
        return round(weighted_sum * 100 / max_sum)

    @staticmethod
    def convert_to_markdown(directives: DirectiveExtractionResult, scores: AdherenceScoreResult) -> str:
        lines: list[str] = []
        lines.append("# Prompt Adherence Report")
        lines.append("")

        # Build lookup
        importance_map = {d.directive_id: d for d in directives.directives}

        # Calculate overall score
        overall = PromptAdherence.calculate_overall_score(directives, scores)
        lines.append(f"**Overall Adherence: {overall}%**")
        lines.append("")

        # Sort by severity: importance * (6 - adherence), worst first
        scored_items = []
        for r in scores.results:
            d = importance_map.get(r.directive_id)
            importance = d.importance_5 if d else 3
            severity = importance * (6 - r.adherence_5)
            scored_items.append((severity, d, r))
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| ID | Directive | Type | Importance | Adherence | Category |")
        lines.append("|----|-----------|------|------------|-----------|----------|")
        for _, d, r in scored_items:
            directive_text = d.text if d else "Unknown"
            directive_type = d.directive_type.value if d else "unknown"
            lines.append(
                f"| {r.directive_id} | {_escape_table_cell(directive_text)} "
                f"| {directive_type} | {d.importance_5 if d else '?'}/5 "
                f"| {r.adherence_5}/5 | {r.category.value} |"
            )
        lines.append("")

        # Detail section for poorly-scored directives
        poor_items = [(sev, d, r) for sev, d, r in scored_items if r.adherence_5 <= 3]
        if poor_items:
            lines.append("## Issues")
            lines.append("")
            for _, d, r in poor_items:
                directive_text = d.text if d else "Unknown"
                lines.append(f"### {r.directive_id}: {directive_text}")
                lines.append("")
                lines.append(f"- **Category:** {r.category.value}")
                lines.append(f"- **Adherence:** {r.adherence_5}/5")
                lines.append(f"- **Importance:** {d.importance_5 if d else '?'}/5")
                lines.append(f"- **Evidence:** {r.evidence}")
                lines.append(f"- **Explanation:** {r.explanation}")
                lines.append("")

        return "\n".join(lines)


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker_plan && .venv/bin/python -m pytest worker_plan_internal/diagnostics/tests/test_prompt_adherence.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add worker_plan/worker_plan_internal/diagnostics/prompt_adherence.py worker_plan/worker_plan_internal/diagnostics/tests/test_prompt_adherence.py
git commit -m "feat: add prompt adherence Pydantic models, prompts, and markdown generation"
```

---

### Task 3: Luigi task

**Files:**
- Create: `worker_plan/worker_plan_internal/plan/nodes/prompt_adherence.py`

- [ ] **Step 1: Implement the Luigi task**

```python
# worker_plan/worker_plan_internal/plan/nodes/prompt_adherence.py
"""PromptAdherenceTask - Check how faithfully the plan follows the original prompt."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.prompt_adherence import PromptAdherence
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.executive_summary import ExecutiveSummaryTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask


class PromptAdherenceTask(PlanTask):
    """Score how faithfully the final plan follows the user's original prompt."""

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PROMPT_ADHERENCE_RAW),
            'markdown': self.local_target(FilenameEnum.PROMPT_ADHERENCE_MARKDOWN),
        }

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'project_plan': self.clone(ProjectPlanTask),
            'executive_summary': self.clone(ExecutiveSummaryTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['executive_summary']['markdown'].open("r") as f:
            executive_summary_markdown = f.read()
        with self.input()['consolidate_assumptions_markdown']['full'].open("r") as f:
            assumptions_markdown = f.read()

        plan_context = (
            f"File 'executive_summary.md':\n{executive_summary_markdown}\n\n"
            f"File 'project_plan.md':\n{project_plan_markdown}\n\n"
            f"File 'consolidate_assumptions_full.md':\n{assumptions_markdown}"
        )

        result = PromptAdherence.execute(
            llm_executor=llm_executor,
            plan_prompt=plan_prompt,
            plan_context=plan_context,
        )

        result.save_raw(self.output()['raw'].path)
        result.save_markdown(self.output()['markdown'].path)
```

- [ ] **Step 2: Verify import works**

Run: `cd worker_plan && .venv/bin/python -c "from worker_plan_internal.plan.nodes.prompt_adherence import PromptAdherenceTask; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/nodes/prompt_adherence.py
git commit -m "feat: add PromptAdherenceTask Luigi node"
```

---

### Task 4: Wire into pipeline and report

**Files:**
- Modify: `worker_plan/worker_plan_internal/plan/nodes/full_plan_pipeline.py`
- Modify: `worker_plan/worker_plan_internal/plan/nodes/report.py`

- [ ] **Step 1: Add to full_plan_pipeline.py**

Add the import at the top with the other node imports:

```python
from worker_plan_internal.plan.nodes.prompt_adherence import PromptAdherenceTask
```

Add to the `requires()` dict, after `'self_audit'` and before `'report'`:

```python
            'prompt_adherence': self.clone(PromptAdherenceTask),
```

- [ ] **Step 2: Add to report.py**

Add the import at the top:

```python
from worker_plan_internal.plan.nodes.prompt_adherence import PromptAdherenceTask
```

Add to `requires()` dict:

```python
            'prompt_adherence': self.clone(PromptAdherenceTask),
```

In `run_inner()`, find where `self_audit` is appended and add after it:

```python
        rg.append_markdown_with_tables('Prompt Adherence', self.input()['prompt_adherence']['markdown'].path)
```

- [ ] **Step 3: Run full test suite**

Run: `cd worker_plan && .venv/bin/python -m pytest -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/nodes/full_plan_pipeline.py worker_plan/worker_plan_internal/plan/nodes/report.py
git commit -m "feat: wire PromptAdherenceTask into pipeline and report"
```

---

### Task 5: Integration verification

- [ ] **Step 1: Verify extract_dag picks up the new node**

Run: `cd worker_plan && .venv/bin/python -c "from worker_plan_internal.extract_dag import extract_dag; dag = extract_dag(); nodes = {n['id'] for n in dag['nodes']}; assert 'prompt_adherence' in nodes; print(f'OK: {len(nodes)} nodes')"`
Expected: `OK: <N> nodes` (one more than before)

- [ ] **Step 2: Run full test suite**

Run: `cd worker_plan && .venv/bin/python -m pytest -q`
Expected: All tests pass, no regressions

- [ ] **Step 3: Commit any fixes**

Only if step 2 revealed issues. Otherwise skip.
