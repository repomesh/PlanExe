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
from typing import List, Literal
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
    directive_index: int = Field(description="Index of this directive, starting from 1.")
    directive_type: Literal["constraint", "stated_fact", "requirement", "banned", "intent"] = Field(description=(
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
    directive_index: int = Field(description="References a directive_index from Phase 1.")
    adherence_5: int = Field(description="1 (ignored/contradicted) to 5 (fully honored).")
    category: Literal["fully_honored", "partially_honored", "softened", "ignored", "contradicted", "unsolicited_caveat"] = Field(description=(
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
        importance_map = {d.directive_index: d.importance_5 for d in directives.directives}
        weighted_sum = 0
        max_sum = 0
        for r in scores.results:
            importance = importance_map.get(r.directive_index, 3)
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
        importance_map = {d.directive_index: d for d in directives.directives}

        # Calculate overall score
        overall = PromptAdherence.calculate_overall_score(directives, scores)
        lines.append(f"**Overall Adherence: {overall}%**")
        lines.append("")

        # Sort by severity: importance * (6 - adherence), worst first
        scored_items = []
        for r in scores.results:
            d = importance_map.get(r.directive_index)
            importance = d.importance_5 if d else 3
            severity = importance * (6 - r.adherence_5)
            scored_items.append((severity, d, r))
        scored_items.sort(key=lambda x: x[2].directive_index)

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append("| ID | Directive | Type | Importance | Adherence | Category |")
        lines.append("|----|-----------|------|------------|-----------|----------|")
        for _, d, r in scored_items:
            directive_text = d.text if d else "Unknown"
            directive_type = _DIRECTIVE_TYPE_LABELS.get(d.directive_type, d.directive_type) if d else "Unknown"
            lines.append(
                f"| {r.directive_index} | {_escape_table_cell(directive_text)} "
                f"| {directive_type} | {d.importance_5 if d else '?'}/5 "
                f"| {r.adherence_5}/5 | {_format_category(r.category)} |"
            )
        lines.append("")

        # Detail section for poorly-scored directives
        poor_items = [(sev, d, r) for sev, d, r in scored_items if r.adherence_5 <= 3]
        poor_items.sort(key=lambda x: x[0], reverse=True)
        if poor_items:
            lines.append("## Issues")
            lines.append("")
            for _, d, r in poor_items:
                directive_text = d.text if d else "Unknown"
                lines.append(f"### Issue {r.directive_index} - {directive_text}")
                lines.append("")
                lines.append(f"- **Category:** {_format_category(r.category)}")
                lines.append(f"- **Adherence:** {r.adherence_5}/5")
                lines.append(f"- **Importance:** {d.importance_5 if d else '?'}/5")
                lines.append(f"- **Evidence:** {r.evidence}")
                lines.append(f"- **Explanation:** {r.explanation}")
                lines.append("")

        return "\n".join(lines)


_DIRECTIVE_TYPE_LABELS = {
    "constraint": "Constraint",
    "stated_fact": "Stated fact",
    "requirement": "Requirement",
    "banned": "Banned",
    "intent": "Intent",
}


_CATEGORY_LABELS = {
    "fully_honored": "Fully honored",
    "partially_honored": "Partially honored",
    "softened": "Softened",
    "ignored": "Ignored",
    "contradicted": "Contradicted",
    "unsolicited_caveat": "Unsolicited caveat",
}


def _format_category(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
