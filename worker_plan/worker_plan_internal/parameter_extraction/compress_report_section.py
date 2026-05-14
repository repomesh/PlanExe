"""
Compress one verbose PlanExe report section (Strategic Decisions, Review Plan,
Premortem, Expert Criticism) into a small Markdown digest that preserves the
signal a downstream parameter-extraction LLM needs for napkin math and Monte
Carlo modelling.

This is an alternative to ``distill_report_section.py``. The two files solve
the same task; they differ in schema design and target LLM compatibility.

Schema design: split, single-field calls
----------------------------------------
The sibling ``distill_report_section.py`` returns a deeply nested object: 8
parallel lists, 8 enums, and a cross-list ``depends_on`` ID graph the LLM
must keep coherent. Frontier models handle that. Smaller, cheaper, or older
models often leave fields empty, pick the wrong enum, invent IDs, or echo
the schema.

This module takes the opposite approach. Each compression call asks the LLM
for ONE field. Six calls per section produce one ``CompressedReportSection``:

1. section_summary             — plain-English purpose of the section
2. numeric_values              — labelled, role-tagged numbers
3. load_bearing_assumptions    — foundational claims with modelling impact
4. gates_and_thresholds        — pass/fail conditions with consequence
5. risks_and_shocks            — triggers with quantitative impact
6. missing_data_to_estimate    — primitive inputs not supplied by the section

Each call has a tiny single-field Pydantic schema, a dedicated system prompt
focused on that bucket only, and a small expected response. This keeps each
response well under any token cap and removes whole classes of small-model
failure: no field-order confusion across buckets, no truncation of long
combined responses, no need for the model to balance attention across six
different extraction jobs in one shot.

The cost is 6 LLM calls per section instead of 1. For the small models this
module targets (Llama 3.1 8B etc.) those calls are cheap and fast.

PROMPT> python -m worker_plan_internal.parameter_extraction.compress_report_section
"""
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from math import ceil
from pathlib import Path
from typing import Any, Literal, Optional

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
    """Assembled output of six single-field extraction calls.

    Field descriptions here document the shape of the assembled object. The
    detailed extraction instructions for each field live in the per-bucket
    system prompts below — the LLM never sees this model directly.
    """

    section_summary: str = Field(
        description=(
            "One to three sentences describing what this section contributes "
            "to Monte Carlo / napkin-math modelling. Plain English."
        )
    )
    numeric_values: list[str] = Field(
        default_factory=list,
        description=(
            "Modelling-relevant numbers as 'label: value [unit] — modelling role'."
        ),
    )
    load_bearing_assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Foundational claims whose failure would change the plan's viability."
        ),
    )
    gates_and_thresholds: list[str] = Field(
        default_factory=list,
        description=(
            "Pass/fail conditions with consequence on failure."
        ),
    )
    risks_and_shocks: list[str] = Field(
        default_factory=list,
        description=(
            "Downside triggers with quantitative or operationally specific impact."
        ),
    )
    missing_data_to_estimate: list[str] = Field(
        default_factory=list,
        description=(
            "Primitive inputs the section does not supply, with an estimation hint."
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
You compress one verbose PlanExe report section so that a downstream
parameter-extraction model can read it for Monte Carlo and napkin-math
purposes.

You are not summarising for a human reader. Throw away narrative and focus
on the one class of signal this call asks for.

Drop in every call:
- persuasive prose and rhetorical framing
- repeated restatements of the same lever, decision, or risk
- expert biographies, role descriptions, search terms
- generic mitigations with no number, threshold, or specific action
- synergy/conflict paragraphs unless they identify a hard dependency

General output discipline:
- preserve numeric values exactly as written in the source (do not round, do
  not convert percentages to fractions, do not translate currency)
- never copy units, currencies, or dates from this prompt's examples — always
  use what the source actually says
- do not add commentary, headings, or markdown formatting inside any field
- if the section genuinely contains nothing for this call's bucket, return
  an empty list (or empty string for the summary)
- only include facts and numbers that appear in the section text between
  [START_SECTION_MARKDOWN] and [END_SECTION_MARKDOWN]; do NOT invent
  breakdowns, sub-categories, or specific values that are not in the source
- this is a multi-turn conversation: on each turn you produce ONE field of
  the digest. Earlier turns are visible above as ASSISTANT JSON. Do NOT
  duplicate items already produced for a previous bucket — each bucket
  captures a distinct kind of signal

CRITICAL response format rules:
- Your entire response must be exactly one JSON object matching the
  requested schema.
- The very first character of your response MUST be '{' and the very last
  character MUST be '}'.
- Do NOT wrap the JSON in markdown code fences (no ```json, no ```).
- Do NOT prefix the JSON with phrases like 'Here is...', 'Below is...',
  'The output is...', 'Here is the JSON...', or any other introduction.
- Do NOT append any prose, explanation, or commentary after the closing '}'.
- Do NOT emit a second JSON object — there must be exactly one.
- Do NOT echo the JSON schema. Produce a response that contains the actual
  VALUES, not the schema structure. Wrong: {"properties":{"section_summary":
  {"type":"string"}}}. Right: {"section_summary":"<your actual answer>"}.
  Wrong: {"type":"array","items":{...}}. Right: the field's value directly.
""".strip()


# ---------------------------------------------------------------------------
# Per-bucket schemas. Each call uses a single-field Pydantic model so the LLM
# never has to balance attention across multiple lists in one response.
# ---------------------------------------------------------------------------


class _SectionSummaryOnly(BaseModel):
    section_summary: str = Field(
        description=(
            "One to three sentences describing what this section contributes "
            "to Monte Carlo / napkin-math modelling. Plain English, no markdown."
        )
    )


class _NumericValueItem(BaseModel):
    """A scored numeric_values entry. The downstream consumer reads every
    item — high- and low-confidence alike — and uses the per-item
    annotations to weigh them. We do NOT drop items in this module; the
    goal is to extract liberally and tag honestly so a cheap downstream
    model does not need to reason about which numbers exist.

    Detailed instructions live in the numeric_values bucket prompt; the
    schema field descriptions are kept short on purpose so the JSON-schema
    overhead in the structured-output system message stays small.
    """

    line: str = Field(description="'label: value [unit] — modelling role'.")
    modelling_relevance: int = Field(
        description="1-5 Likert: usefulness for Monte Carlo / napkin-math modelling."
    )
    source_evidence: int = Field(
        description="1-5 Likert: how directly the source supports this exact value+label (1 = invented)."
    )
    source_status: Literal["explicit", "derived", "inferred"] = Field(
        description=(
            "'explicit' = literally stated in the source; "
            "'derived' = computed from explicit source values; "
            "'inferred' = a plausible business assumption you added that the "
            "source does not state. When in doubt prefer 'inferred'."
        )
    )
    source_quote: str = Field(
        description="≤12 word verbatim fragment from the source, or 'NOT IN SOURCE'."
    )


class _NumericValuesOnly(BaseModel):
    numeric_values: list[_NumericValueItem] = Field(
        default_factory=list,
        description="See system prompt for the required line format and scoring.",
    )


class _LoadBearingAssumptionsOnly(BaseModel):
    load_bearing_assumptions: list[str] = Field(
        default_factory=list,
        description="See system prompt.",
    )


class _GatesAndThresholdsOnly(BaseModel):
    gates_and_thresholds: list[str] = Field(
        default_factory=list,
        description="See system prompt.",
    )


class _RisksAndShocksOnly(BaseModel):
    risks_and_shocks: list[str] = Field(
        default_factory=list,
        description="See system prompt.",
    )


class _MissingDataOnly(BaseModel):
    missing_data_to_estimate: list[str] = Field(
        default_factory=list,
        description="See system prompt.",
    )


# ---------------------------------------------------------------------------
# Per-bucket system prompts. Each is concatenated with the shared preamble at
# call time.
# ---------------------------------------------------------------------------


_SECTION_SUMMARY_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the section_summary.

Write one to three sentences in plain English describing what this section
contributes to Monte Carlo / napkin-math modelling. No markdown, no bullet
points, no lists. Do not enumerate numbers or assumptions — those are
handled in other calls.
""".strip()


_NUMERIC_VALUES_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the numeric_values list.

Output exactly one JSON OBJECT, not a bare array. The top-level shape is:
{"numeric_values":[ ...one or more scored items... ]}
Do NOT emit any other top-level key (no section_summary, no
load_bearing_assumptions, no gates_and_thresholds, no risks_and_shocks, no
missing_data_to_estimate). Do NOT emit a bare top-level array.

Each item is a scored object with five fields: line, modelling_relevance,
source_evidence, source_status, source_quote.

The 'line' field MUST follow the form 'label: value [unit] — modelling role':
- label names what the number represents in 2-6 words
- value [unit] is the literal value and unit from the source, preserved
  verbatim — never invent, translate, or substitute the currency, unit, or
  date
- modelling role is a short phrase such as 'input to cash burn model',
  'gates launch readiness', 'sensitivity driver for revenue', 'capacity
  ceiling'

Bare values are invalid: a percent on its own, an amount in any currency on
its own, or a date on its own.

Template shape (substitute values from the source — DO NOT copy these
placeholders or any unit from them):
- '<what the number is>: <amount> <currency-from-source> — <modelling role>.'
- '<what the number is>: <percent>% — <modelling role>.'
- '<what the number is>: <date-from-source> — <modelling role>.'

If the source contains conflicting values for the same quantity, list each
with a disambiguating label (e.g. 'minimum', 'aspirational') rather than
picking one silently.

Scoring discipline:
- modelling_relevance (1-5): how useful this number is for Monte Carlo /
  napkin-math modelling. 5 = primary driver of viability; 1 = irrelevant
  narrative number.
- source_evidence (1-5): how directly the source text supports this exact
  value AND label. 5 = near-verbatim quote present in the section; 1 = you
  invented it. Be honest.
- source_status: 'explicit' = literally stated in the source; 'derived' =
  computed from explicit source values (note the computation in the
  modelling role); 'inferred' = a plausible business assumption you added
  that the source does not state. When in doubt prefer 'inferred'.
- source_quote: a SHORT (≤12 word) verbatim or near-verbatim fragment from
  the section containing this number. If the number is not in the section,
  write 'NOT IN SOURCE' and set source_evidence to 1 and source_status to
  'inferred'. Do not paste long passages — a 5-10 word fragment is plenty.

We DO NOT drop items downstream — the consumer reads everything and uses
your scores and source_status as guidance. So:
- prefer redundancy over conciseness. Include borderline items with honest
  low scores rather than silently skipping them.
- but never *invent* a specific value where the source is silent. If the
  source says '2M total budget' you may report that. You may NOT then
  report '1M for staff' or '40% admin markup' as separate items unless the
  source states them — mark such guesses 'inferred' with source_evidence 1
  if you include them at all.

At most 6 items, sorted by your judgement of importance for modelling.
Fewer items is fine; padding the cap with low-quality inferences is not.
Keep each source_quote to ≤8 words so the response stays within the
small-LLM output budget.
""".strip()


_LOAD_BEARING_ASSUMPTIONS_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the load_bearing_assumptions list.

Each item is a foundational claim that, if false, changes the plan's
viability. State the assumption itself in 25 words or fewer. Prefer
assumptions that have an obvious modelling consequence — regulatory
permissions, demand assumptions, supply assumptions, cost-stability
assumptions, capacity assumptions.

Each line should be a complete short sentence stating the assumption. Do
not enumerate the supporting numbers here — they are handled in another
call.

At most 10 items.
""".strip()


_GATES_AND_THRESHOLDS_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the gates_and_thresholds list.

Each item is a pass/fail condition, KPI cutoff, validation gate, or deadline
that triggers a decision. State the condition AND the consequence if it
fails.

Template shape (substitute the actual metric, comparison, threshold, and
consequence from the source):
- '<metric> must <comparison> <threshold>, else <consequence>'

A gate must be expressible as a threshold, boolean, ratio, surplus, or
deficit. If something is a qualitative trade-off without a pass/fail edge,
do NOT list it here.

At most 8 items.
""".strip()


_RISKS_AND_SHOCKS_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the risks_and_shocks list.

Each item: trigger plus modelling-relevant impact. Template shape
(substitute from the source):
- '<trigger>: <quantitative or operationally specific impact>'

A risk is a downside scenario that could happen — an external shock, a
demand collapse, a supply disruption, a capacity overload, a regulatory
rejection. It is NOT the same as a gate/threshold (which is a pass/fail
condition you actively check). If you have already produced an item in
gates_and_thresholds, do not restate it here.

Skip purely qualitative risks that do not name a number, a date, a capacity,
or an operationally specific failure mode.

At most 10 items.
""".strip()


_MISSING_DATA_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the missing_data_to_estimate list.

Each item is a PRIMITIVE input the model would need but the section does
not supply. A primitive is a single quantity with a unit (currency/month,
kWh, hours, count, percent). State what is missing AND how to estimate it.

Template shape:
- '<missing primitive quantity with unit> — <how to estimate>'

Prefer primitives over derived quantities. Avoid words like 'gap',
'shortfall', 'surplus', 'versus', 'coverage', 'feasibility' unless you are
naming a formula explicitly; if a derived quantity is missing, decompose
it into the primitives that go into it.

At most 6 items.
""".strip()


@dataclass(frozen=True)
class _BucketSpec:
    field_name: str
    schema: type[BaseModel]
    bucket_prompt: str


_BUCKET_SPECS: tuple[_BucketSpec, ...] = (
    _BucketSpec("section_summary", _SectionSummaryOnly, _SECTION_SUMMARY_BUCKET_PROMPT),
    _BucketSpec("numeric_values", _NumericValuesOnly, _NUMERIC_VALUES_BUCKET_PROMPT),
    _BucketSpec(
        "load_bearing_assumptions",
        _LoadBearingAssumptionsOnly,
        _LOAD_BEARING_ASSUMPTIONS_BUCKET_PROMPT,
    ),
    _BucketSpec(
        "gates_and_thresholds",
        _GatesAndThresholdsOnly,
        _GATES_AND_THRESHOLDS_BUCKET_PROMPT,
    ),
    _BucketSpec("risks_and_shocks", _RisksAndShocksOnly, _RISKS_AND_SHOCKS_BUCKET_PROMPT),
    _BucketSpec("missing_data_to_estimate", _MissingDataOnly, _MISSING_DATA_BUCKET_PROMPT),
)


# Per-bucket call attempts before giving up. Small models like Llama 3.1 8B
# occasionally emit malformed JSON, drop required fields, or truncate mid-
# list; retrying the same chat history usually succeeds because each attempt
# samples fresh.
_PER_BUCKET_MAX_ATTEMPTS = 3


def _normalise_for_quote_match(text: str) -> str:
    """Lowercase, normalise unicode dashes, and collapse whitespace.

    The LLM often paraphrases punctuation/whitespace when quoting (em-dash
    vs hyphen, line wraps, extra spaces). A loose normalisation lets the
    substring check accept those variations while still catching outright
    inventions.
    """
    text = text.lower()
    for dash in ("–", "—", "−"):
        text = text.replace(dash, "-")
    return " ".join(text.split())


def _quote_is_in_source(quote: str, section_markdown: str) -> bool:
    if not quote:
        return False
    if quote.strip().upper() == "NOT IN SOURCE":
        return False
    return _normalise_for_quote_match(quote) in _normalise_for_quote_match(section_markdown)


def _annotate_numeric_values(
    items: list[_NumericValueItem],
    section_markdown: str,
) -> tuple[list[str], list[dict]]:
    """Verify each item's quote against the source, sort by confidence, and
    flatten into tagged strings.

    No items are dropped — the consumer reads the full annotated list and
    uses the inline tags ``[status | e=N r=N | quote: verified|unverified]``
    to weigh each entry. Items the LLM scored low or whose quote does not
    appear in the source remain in the output so a downstream model can
    still see what was considered.
    """
    scored_dicts: list[dict] = []
    annotated_pairs: list[tuple[int, str]] = []
    for item in items:
        verified = _quote_is_in_source(item.source_quote, section_markdown)
        as_dict = item.model_dump()
        as_dict["quote_verified"] = verified
        scored_dicts.append(as_dict)
        tag = (
            f"[{item.source_status} | "
            f"e={item.source_evidence} r={item.modelling_relevance} | "
            f"quote: {'verified' if verified else 'unverified'}]"
        )
        sort_key = item.source_evidence * item.modelling_relevance + (10 if verified else 0)
        annotated_pairs.append((sort_key, f"{item.line}  {tag}"))

    annotated_pairs.sort(key=lambda pair: pair[0], reverse=True)
    return [line for _, line in annotated_pairs], scored_dicts


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
    """Build the section-wrapper user prompt shared by all six bucket calls."""
    title = section_title or section_type.replace("_", " ").title()
    guidance = _SECTION_GUIDANCE.get(
        section_type, _SECTION_GUIDANCE[ReportSectionTypeEnum.UNKNOWN.value]
    )
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
    ) -> "CompressReportSection":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(section_markdown, str):
            raise ValueError("Invalid section_markdown.")

        normalized_section_type = normalize_section_type(section_type)
        section_wrapper = build_user_prompt(
            section_markdown=section_markdown,
            section_type=normalized_section_type,
            section_title=section_title,
        )
        logger.debug(f"Section wrapper user prompt:\n{section_wrapper}")

        accumulated_chat: list[ChatMessage] = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=COMPRESS_REPORT_SECTION_SYSTEM_PROMPT,
            )
        ]

        bucket_values: dict[str, Any] = {}
        per_bucket_metadata: dict[str, dict[str, Any]] = {}
        total_start = time.perf_counter()

        for i, spec in enumerate(_BUCKET_SPECS):
            if i == 0:
                user_content = f"{section_wrapper}\n\n{spec.bucket_prompt}"
            else:
                user_content = spec.bucket_prompt

            accumulated_chat.append(
                ChatMessage(role=MessageRole.USER, content=user_content)
            )

            sllm = llm.as_structured_llm(spec.schema)
            bucket_start = time.perf_counter()
            obj = None
            chat_response = None
            last_error: Optional[Exception] = None
            for retry in range(_PER_BUCKET_MAX_ATTEMPTS):
                logger.debug(
                    f"Bucket {spec.field_name}: starting LLM call "
                    f"(turn {i + 1}, attempt {retry + 1}/{_PER_BUCKET_MAX_ATTEMPTS})"
                )
                try:
                    chat_response = sllm.chat(accumulated_chat)
                    obj = chat_response.raw
                    if obj is None:
                        raise ValueError(
                            f"Structured LLM returned None for bucket {spec.field_name!r}."
                        )
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Bucket {spec.field_name} attempt {retry + 1} failed: "
                        f"{type(e).__name__}: {str(e)[:160]}"
                    )
            if obj is None:
                raise ValueError(
                    f"Bucket {spec.field_name!r} failed after "
                    f"{_PER_BUCKET_MAX_ATTEMPTS} attempts. Last error: "
                    f"{type(last_error).__name__}: {last_error}"
                ) from last_error
            bucket_duration = int(ceil(time.perf_counter() - bucket_start))
            bucket_byte_count = len(chat_response.message.content.encode("utf-8"))
            logger.info(
                f"Bucket {spec.field_name}: completed in {bucket_duration}s, "
                f"{bucket_byte_count} bytes"
            )
            raw_field_value = getattr(obj, spec.field_name)
            bucket_metadata: dict[str, Any] = {
                "duration": bucket_duration,
                "response_byte_count": bucket_byte_count,
                "user_prompt": user_content,
            }
            if spec.field_name == "numeric_values":
                bucket_values[spec.field_name], scored_items = _annotate_numeric_values(
                    raw_field_value, section_markdown
                )
                bucket_metadata["scored_items"] = scored_items
            else:
                bucket_values[spec.field_name] = raw_field_value

            # Append the assistant turn as compact JSON so the next bucket call
            # can see what has already been produced and avoid duplicating it.
            assistant_content = json.dumps(obj.model_dump(), separators=(",", ":"))
            accumulated_chat.append(
                ChatMessage(role=MessageRole.ASSISTANT, content=assistant_content)
            )

            per_bucket_metadata[spec.field_name] = bucket_metadata

        total_duration = int(ceil(time.perf_counter() - total_start))

        compressed = CompressedReportSection(**bucket_values)

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["section_type"] = normalized_section_type
        metadata["total_duration"] = total_duration
        metadata["per_bucket"] = per_bucket_metadata
        metadata["system_prompt"] = COMPRESS_REPORT_SECTION_SYSTEM_PROMPT

        json_response = compressed.model_dump()
        markdown = cls.convert_to_markdown(
            compressed,
            section_title=section_title or normalized_section_type.replace("_", " ").title(),
        )

        return CompressReportSection(
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
        )

    def to_dict(self, include_metadata: bool = True) -> dict:
        d = self.response.copy()
        if include_metadata:
            d["metadata"] = self.metadata
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
