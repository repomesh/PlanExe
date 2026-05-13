"""
Compress one verbose PlanExe report section (Strategic Decisions, Review Plan,
Premortem, Expert Criticism) into a small Markdown digest that preserves the
signal a downstream parameter-extraction LLM needs for napkin math and Monte
Carlo modelling.

This is an alternative to ``distill_report_section.py``. The two files solve
the same task; they differ in schema design and target LLM compatibility.

Why a separate, simpler schema
------------------------------
The sibling ``distill_report_section.py`` returns a deeply nested object: 8
parallel lists (digest_items, numeric_anchors, model_drivers, gates,
risk_shocks, missing_values, calculations, omitted_rationale), 8 enums, plus
a cross-list ``depends_on`` ID graph the LLM must keep coherent. Frontier
models (GPT-5, Sonnet 4.x, Gemini 2.5) handle that. Smaller, cheaper, or
older models often:

- leave many of the fields empty,
- pick the wrong enum value and fail schema validation,
- invent ``depends_on`` IDs that point at things in another list,
- or echo the schema instead of producing values.

The compression role itself does not need any of that complexity. The
downstream parameter-extractor (see ``planexe_simulator/extract-parameters``)
already builds the typed model. The only job of this module is to throw away
narrative, persuasion, and repetition while keeping the *raw lines* that the
extractor will turn into modelling variables.

So this implementation uses a flat schema: one summary string plus five
``list[str]`` buckets aligned with the digest layout recommended in
``docs/proposals/done/137-section_filtering_for_parameter_extraction.md`` (or
``docs/proposals/137-...`` if not yet moved). Each bullet is a self-contained
short sentence. There are no nested objects, no enums, and no cross-list ID
references — the structure that smaller LLMs trip on.

PROMPT> python -m worker_plan_internal.parameter_extraction.compress_report_section
"""
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from math import ceil
from pathlib import Path
from typing import Any, Optional

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ReportSectionTypeEnum(str, Enum):
    STRATEGIC_DECISIONS = "strategic_decisions"
    REVIEW_PLAN = "review_plan"
    PREMORTEM = "premortem"
    EXPERT_CRITICISM = "expert_criticism"
    UNKNOWN = "unknown"


class CompressedReportSection(BaseModel):
    """Flat, LLM-friendly compression of one report section.

    Every field is either a string or a ``list[str]``. There are no nested
    objects, no enums, and no foreign-key references. An older or smaller
    model that struggles with elaborate schemas can still produce useful
    output here.
    """

    section_summary: str = Field(
        description=(
            "One to three sentences describing what this section contributes to "
            "Monte Carlo / napkin-math modelling. Plain English, no markdown."
        )
    )
    numeric_values: list[str] = Field(
        default_factory=list,
        description=(
            "Numbers worth preserving for modelling, each on its own line with "
            "enough context to be understandable in isolation. Include the value "
            "and unit verbatim (e.g. '15% startup contingency = 300,000 DKK', "
            "'utility variance approval deadline 2026-08-15', '60% target "
            "outreach contact rate'). Skip numbers that only appear for narrative "
            "color. At most 12 items."
        ),
    )
    load_bearing_assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Foundational claims that, if false, change the plan's viability. "
            "Each line: the assumption itself, in 25 words or fewer (e.g. "
            "'Greenlandic labor law lets us treat instructors as contractors'). "
            "Prefer assumptions that have an obvious modelling consequence. "
            "At most 10 items."
        ),
    )
    gates_and_thresholds: list[str] = Field(
        default_factory=list,
        description=(
            "Pass/fail conditions, KPI cutoffs, validation gates, deadlines that "
            "trigger a decision. Each line should state the condition and the "
            "consequence if it fails (e.g. 'Off-peak revenue must cover >=75% of "
            "direct utility overhead, else contingency funds operating costs'). "
            "At most 8 items."
        ),
    )
    risks_and_shocks: list[str] = Field(
        default_factory=list,
        description=(
            "Downside scenarios, failure paths, tripwires, shocks. Each line: "
            "trigger plus modelling-relevant impact (e.g. 'Single-kiln overload "
            "during June-September peak: bookings exceed 24/7 capacity by >48h, "
            "causes seasonal revenue cap'). Skip purely qualitative risks. "
            "At most 10 items."
        ),
    )
    missing_data_to_estimate: list[str] = Field(
        default_factory=list,
        description=(
            "Inputs the model would need but the section does not supply. Each "
            "line: what is missing and ideally how to estimate it (e.g. 'Direct "
            "monthly utility overhead in DKK — derive from metered pricing trial'). "
            "At most 6 items."
        ),
    )


_SECTION_TYPE_BY_STEM = {
    "strategic_decisions": ReportSectionTypeEnum.STRATEGIC_DECISIONS.value,
    "review_plan": ReportSectionTypeEnum.REVIEW_PLAN.value,
    "premortem": ReportSectionTypeEnum.PREMORTEM.value,
    "expert_criticism": ReportSectionTypeEnum.EXPERT_CRITICISM.value,
}

_SECTION_GUIDANCE = {
    ReportSectionTypeEnum.STRATEGIC_DECISIONS.value: (
        "This is Strategic Decisions. The signal is in the *trade-offs* and *levers*. "
        "Keep: decision title, the core choice, the trade-off it forces, any numbers "
        "that quantify the choice (budget %, capacity, deadline), and the *consequence* "
        "if the decision turns out wrong. Drop: long synergy/conflict prose, repeated "
        "framing of the same lever, persuasive narrative."
    ),
    ReportSectionTypeEnum.REVIEW_PLAN.value: (
        "This is Review Plan. The signal is in *what must be checked* and *what fails "
        "if it isn't*. Keep: validation questions, KPI thresholds, fragile assumptions "
        "called out for review, deadlines tied to gates, missing-evidence flags. Drop: "
        "review-process descriptions, methodology prose, generic 'we will review' lines."
    ),
    ReportSectionTypeEnum.PREMORTEM.value: (
        "This is Premortem. The signal is in *failure paths*, *tripwires*, and *the "
        "specific assumption that fails*. Keep: assumptions-to-kill (with their failure "
        "trigger), the numeric tripwires for each failure mode, the contingency drawdown "
        "or revenue shortfall implied. Drop: long failure-story narrative, owner names "
        "and role descriptions, generic mitigations without numbers."
    ),
    ReportSectionTypeEnum.EXPERT_CRITICISM.value: (
        "This is Expert Criticism. The signal is in *hidden assumptions* and *missing "
        "denominators* the experts call out. Keep: each criticism's quantitative claim "
        "(numbers, ratios, thresholds), the consequence the expert names, the "
        "mitigation if it carries a number. Drop: expert biographies, search terms, "
        "process language, repetition of the same critique by different experts."
    ),
    ReportSectionTypeEnum.UNKNOWN.value: (
        "Unknown section type. Apply the same rule as for the named sections: keep "
        "numbers, assumptions, gates, risks, and missing data. Drop narrative, "
        "persuasion, and repetition."
    ),
}

COMPRESS_REPORT_SECTION_SYSTEM_PROMPT = """
You compress one verbose PlanExe report section into a short Markdown digest
that a downstream parameter-extraction model will read for Monte Carlo and
napkin-math purposes.

You are not summarising for a human reader. You are throwing away narrative
so the extractor can find numbers, assumptions, gates, risks, and missing
data without distraction.

Keep:
- explicit numbers, percentages, dates, deadlines, budgets, capacities,
  thresholds — preserve units verbatim
- assumptions whose failure would change the plan's viability
- pass/fail gates, KPI cutoffs, validation criteria
- failure paths and shocks with a numeric or operationally specific impact
- inputs the model would need but the section does not provide

Drop:
- persuasive prose and rhetorical framing
- repeated restatements of the same lever, decision, or risk
- expert biographies, role descriptions, search terms
- generic mitigations with no number, threshold, or specific action
- synergy/conflict paragraphs unless they identify a hard dependency

Output discipline:
- each bullet is one short sentence, self-contained, understandable on its own
- preserve numeric values exactly as written in the source (do not round, do
  not convert percentages to fractions, do not translate currency)
- if a number is implied but not stated, place it in missing_data_to_estimate
  rather than inventing a value
- soft caps: numeric_values <= 12, load_bearing_assumptions <= 10,
  gates_and_thresholds <= 8, risks_and_shocks <= 10, missing_data_to_estimate
  <= 6. Returning fewer is fine; padding to fill a cap is not
- do not add commentary, headings, or markdown formatting inside any field
- if the section genuinely contains nothing for a bucket, return an empty list
  for that bucket

Return only the structured object the schema requests. No prose before or
after.
""".strip()


def infer_section_type_from_path(file_path: str | Path) -> str:
    """Infer the report section type from a PlanExe intermediary filename."""
    stem = Path(file_path).stem
    return _SECTION_TYPE_BY_STEM.get(stem, ReportSectionTypeEnum.UNKNOWN.value)


def normalize_section_type(section_type: str | ReportSectionTypeEnum | None) -> str:
    """Normalise an optional section-type input to one of the schema values."""
    if section_type is None:
        return ReportSectionTypeEnum.UNKNOWN.value
    if isinstance(section_type, ReportSectionTypeEnum):
        return section_type.value
    text = str(section_type).strip().lower().replace("-", "_").replace(" ", "_")
    if text in _SECTION_GUIDANCE:
        return text
    return _SECTION_TYPE_BY_STEM.get(text, ReportSectionTypeEnum.UNKNOWN.value)


def build_user_prompt(
    section_markdown: str,
    section_type: str,
    section_title: Optional[str] = None,
) -> str:
    """Build the user-side prompt for one section."""
    title = section_title or section_type.replace("_", " ").title()
    guidance = _SECTION_GUIDANCE.get(section_type, _SECTION_GUIDANCE[ReportSectionTypeEnum.UNKNOWN.value])
    return "\n".join(
        [
            f"Section type: {section_type}",
            f"Section title: {title}",
            "",
            "Section-specific guidance:",
            guidance,
            "",
            "Compress the following Markdown section:",
            "[START_SECTION_MARKDOWN]",
            section_markdown.strip(),
            "[END_SECTION_MARKDOWN]",
        ]
    )


@dataclass
class CompressReportSection:
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str

    @classmethod
    def execute(
        cls,
        llm: LLM,
        section_markdown: str,
        section_type: str | ReportSectionTypeEnum | None = None,
        section_title: Optional[str] = None,
        **kwargs: Any,
    ) -> "CompressReportSection":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(section_markdown, str):
            raise ValueError("Invalid section_markdown.")

        normalized_section_type = normalize_section_type(section_type)
        system_prompt = kwargs.get("system_prompt", COMPRESS_REPORT_SECTION_SYSTEM_PROMPT)
        if not isinstance(system_prompt, str):
            raise ValueError("Invalid system_prompt.")

        user_prompt = build_user_prompt(
            section_markdown=section_markdown,
            section_type=normalized_section_type,
            section_title=section_title,
        )
        logger.debug(f"System Prompt:\n{system_prompt}")
        logger.debug(f"User Prompt:\n{user_prompt}")

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(CompressedReportSection)

        logger.debug("Starting LLM chat interaction.")
        start_time = time.perf_counter()
        chat_response = sllm.chat(chat_message_list)
        end_time = time.perf_counter()
        duration = int(ceil(end_time - start_time))
        response_byte_count = len(chat_response.message.content.encode("utf-8"))
        logger.info(
            f"LLM chat interaction completed in {duration} seconds. "
            f"Response byte count: {response_byte_count}"
        )

        compressed: CompressedReportSection = chat_response.raw
        if compressed is None:
            raise ValueError(
                "Structured LLM returned None for CompressedReportSection. "
                "The model likely echoed the schema instead of producing values."
            )

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration"] = duration
        metadata["response_byte_count"] = response_byte_count
        metadata["section_type"] = normalized_section_type

        json_response = compressed.model_dump()
        markdown = cls.convert_to_markdown(
            compressed,
            section_title=section_title or normalized_section_type.replace("_", " ").title(),
        )

        return CompressReportSection(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
            markdown=markdown,
        )

    @classmethod
    def execute_from_file(
        cls,
        llm: LLM,
        file_path: str | Path,
        section_type: str | ReportSectionTypeEnum | None = None,
        section_title: Optional[str] = None,
        **kwargs: Any,
    ) -> "CompressReportSection":
        path = Path(file_path)
        markdown = path.read_text(encoding="utf-8")
        inferred_section_type = (
            normalize_section_type(section_type) if section_type else infer_section_type_from_path(path)
        )
        inferred_title = section_title or path.stem.replace("_", " ").title()
        return cls.execute(
            llm=llm,
            section_markdown=markdown,
            section_type=inferred_section_type,
            section_title=inferred_title,
            **kwargs,
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

    def save_raw(self, file_path: str | Path) -> None:
        Path(file_path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def save_markdown(self, file_path: str | Path) -> None:
        Path(file_path).write_text(self.markdown, encoding="utf-8")

    @staticmethod
    def convert_to_markdown(
        compressed: CompressedReportSection,
        section_title: Optional[str] = None,
    ) -> str:
        """Render the compressed section as a clean Markdown digest.

        The output mirrors the digest structure recommended in proposal 137:
        Goal/summary, Numeric Values, Assumptions, Gates, Risks, Missing Data.
        Empty buckets are omitted to keep the digest compact.
        """
        title = section_title or "Compressed Section"
        lines: list[str] = [f"# {title}", "", compressed.section_summary.strip(), ""]

        sections: list[tuple[str, list[str]]] = [
            ("Numeric values", compressed.numeric_values),
            ("Load-bearing assumptions", compressed.load_bearing_assumptions),
            ("Gates and thresholds", compressed.gates_and_thresholds),
            ("Risks and shocks", compressed.risks_and_shocks),
            ("Missing data to estimate", compressed.missing_data_to_estimate),
        ]
        for heading, items in sections:
            if not items:
                continue
            lines.append(f"## {heading}")
            for item in items:
                cleaned = item.strip().replace("\n", " ")
                lines.append(f"- {cleaned}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    # Smoke test against a sample report section. Requires an LLM that
    # implements ``as_structured_llm``. Adjust the model name as needed.
    import os
    from worker_plan_internal.llm_factory import get_llm

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    sample_path = Path(
        os.environ.get(
            "COMPRESS_REPORT_SECTION_SAMPLE",
            "/Users/neoneye/git/PlanExe-web/20260215_nuuk_clay_workshop/strategic_decisions.md",
        )
    )
    if not sample_path.exists():
        raise SystemExit(
            f"Sample report not found at {sample_path}. "
            "Set COMPRESS_REPORT_SECTION_SAMPLE to a real path."
        )

    llm = get_llm("ollama-llama3.1")
    result = CompressReportSection.execute_from_file(llm=llm, file_path=sample_path)

    print("\n--- JSON ---")
    print(json.dumps(result.response, indent=2))
    print("\n--- Markdown ---")
    print(result.markdown)
