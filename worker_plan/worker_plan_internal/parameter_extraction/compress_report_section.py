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
    SELECTED_SCENARIO = "selected_scenario"
    REVIEW_PLAN = "review_plan"
    PREMORTEM = "premortem"
    EXPERT_CRITICISM = "expert_criticism"
    UNKNOWN = "unknown"


class _ScoredItem(BaseModel):
    """LLM-facing per-item schema shared by all of the list buckets in
    ``CompressedReportSection`` (numeric_values, load_bearing_assumptions,
    gates_and_thresholds, risks_and_shocks, missing_data_to_estimate).

    The ``line`` field carries the bucket-specific content (a labelled
    number, an if/then gate, a primitive missing input, etc.) — the bucket
    prompt defines what shape ``line`` should take in that context. The
    other fields (scores, source_status, source_quote) have the same
    meaning everywhere.

    Does NOT include ``quote_verified`` — that field is computed in code
    from a substring check against the source markdown, not by the LLM.

    Detailed instructions live in each bucket prompt; the schema field
    descriptions are kept short on purpose so the JSON-schema overhead in
    the structured-output system message stays small.
    """

    line: str = Field(description="Bucket-specific content (see bucket prompt for the required format).")
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


class ScoredItem(_ScoredItem):
    """Public per-item shape for compressed list-bucket entries.

    Inherits the LLM-populated fields from ``_ScoredItem`` and adds
    ``quote_verified``, which the pipeline sets after substring-checking the
    model's ``source_quote`` against the section markdown.
    """

    quote_verified: bool = Field(
        default=False,
        description=(
            "True if source_quote appears in the section markdown after "
            "case-insensitive, unicode-dash-tolerant, whitespace-collapsed "
            "normalisation. Set by code, not by the LLM."
        ),
    )


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
    numeric_values: list[ScoredItem] = Field(
        default_factory=list,
        description="Modelling-relevant numbers — see ScoredItem and the numeric_values bucket prompt.",
    )
    load_bearing_assumptions: list[ScoredItem] = Field(
        default_factory=list,
        description="Foundational claims whose failure would change the plan's viability.",
    )
    gates_and_thresholds: list[ScoredItem] = Field(
        default_factory=list,
        description="Pass/fail conditions with consequence on failure (if/then form).",
    )
    risks_and_shocks: list[ScoredItem] = Field(
        default_factory=list,
        description="Downside triggers with quantitative or operationally specific impact.",
    )
    missing_data_to_estimate: list[ScoredItem] = Field(
        default_factory=list,
        description="Primitive inputs the section does not supply, with an estimation hint.",
    )


_SECTION_TYPE_BY_STEM = {
    "strategic_decisions": ReportSectionTypeEnum.STRATEGIC_DECISIONS.value,
    "selected_scenario": ReportSectionTypeEnum.SELECTED_SCENARIO.value,
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
    ReportSectionTypeEnum.SELECTED_SCENARIO.value: (
        "This is the Selected (picked) Scenario — the actual plan to model, not the "
        "menu of options. The signal is in what the plan *committed to*. "
        "Keep: chosen strategy name, explicit commitments and the numbers attached to "
        "them (budget envelope, contingency %, revenue mix, deadlines, conversion "
        "targets), viability gates for the chosen strategy, risk buffers and "
        "mitigations. "
        "Drop HARD: rejected alternatives' numbers (do NOT extract them as parameters), "
        "speculative trade-offs the plan ultimately did not pick, generic 'option A vs B' "
        "narrative. If a rejected alternative is mentioned only for disambiguation, do "
        "not treat its numbers as commitments of the chosen plan."
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
- SOURCE-FAITHFULNESS RULE (critical): do NOT create numeric values from
  generic business intuition. Specifically, never invent: benchmark
  percentages, generic shock sizes, utilization thresholds, salary shares,
  equipment cost guesses, growth rates, churn rates, demand reductions,
  cybersecurity/insurance/disaster impact percentages, or any "typical
  business" filler. If a modelling variable is important but the source
  does not state a number, that variable belongs in
  missing_data_to_estimate — not in numeric_values, not as a hard gate,
  and not as a quantified risk
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


class _NumericValuesOnly(BaseModel):
    numeric_values: list[_ScoredItem] = Field(
        default_factory=list,
        description="See system prompt for the required line format and scoring.",
    )


class _LoadBearingAssumptionsOnly(BaseModel):
    load_bearing_assumptions: list[_ScoredItem] = Field(
        default_factory=list,
        description="See system prompt.",
    )


class _GatesAndThresholdsOnly(BaseModel):
    gates_and_thresholds: list[_ScoredItem] = Field(
        default_factory=list,
        description="See system prompt.",
    )


class _RisksAndShocksOnly(BaseModel):
    risks_and_shocks: list[_ScoredItem] = Field(
        default_factory=list,
        description="See system prompt.",
    )


class _MissingDataOnly(BaseModel):
    missing_data_to_estimate: list[_ScoredItem] = Field(
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


# Shared scoring rules that apply identically to every list bucket. Each
# per-bucket prompt below appends this block so the LLM sees the same
# discipline regardless of which bucket it is currently producing.
_SCORING_DISCIPLINE = """
Every item in the list is a scored object with five fields: line,
modelling_relevance, source_evidence, source_status, source_quote.

Scoring rules (identical across buckets):
- modelling_relevance (1-5): how useful this item is for Monte Carlo /
  napkin-math modelling. 5 = primary driver of viability; 1 = irrelevant
  narrative.
- source_evidence (1-5): how directly the source text supports this exact
  item. 5 = near-verbatim quote present in the section; 1 = you invented
  it. Be honest.
- source_status: 'explicit' = literally stated in the source; 'derived' =
  computed from explicit source values; 'inferred' = a plausible assumption
  you added that the source does not state. When in doubt prefer
  'inferred'.
- source_quote: a SHORT (≤12 word) verbatim or near-verbatim fragment from
  the section that supports this item. If the item is not in the section,
  write 'NOT IN SOURCE' and set source_evidence to 1 and source_status to
  'inferred'.

Cast a wide net — surface borderline candidates with honest low scores
rather than self-censoring; the Python pipeline drops the lowest-scoring
items after sorting, so the cost of including a weak candidate is small
and the cost of missing a real one is large. But never *invent* a specific
value where the source is silent — mark such guesses 'inferred' with
source_evidence 1 if you include them at all.

Keep each source_quote to ≤8 words so the response stays within the output
budget.
""".strip()


_NUMERIC_VALUES_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the numeric_values list.

Output exactly one JSON OBJECT, not a bare array. The top-level shape is:
{"numeric_values":[ ...one or more scored items... ]}
Do NOT emit any other top-level key (no section_summary, no
load_bearing_assumptions, no gates_and_thresholds, no risks_and_shocks, no
missing_data_to_estimate). Do NOT emit a bare top-level array.

The 'line' field for this bucket MUST follow the form
'label: value [unit] — modelling role':
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

Skip numbers that only appear for narrative color. At most 8 items, sorted
by your judgement of importance for modelling. Fewer items is fine.
""".strip() + "\n\n" + _SCORING_DISCIPLINE


_LOAD_BEARING_ASSUMPTIONS_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the load_bearing_assumptions list.

Output exactly one JSON OBJECT with key 'load_bearing_assumptions' whose
value is a list of scored items. Do NOT emit any other top-level key. Do
NOT emit a bare top-level array.

The 'line' field for this bucket is a complete short sentence stating the
assumption itself, in 25 words or fewer. Prefer assumptions that have an
obvious modelling consequence — regulatory permissions, demand
assumptions, supply assumptions, cost-stability assumptions, capacity
assumptions. Do not enumerate supporting numbers in the line — numbers
belong in numeric_values.

At most 8 items.
""".strip() + "\n\n" + _SCORING_DISCIPLINE


_GATES_AND_THRESHOLDS_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the gates_and_thresholds list.

Output exactly one JSON OBJECT with key 'gates_and_thresholds' whose value
is a list of scored items. Do NOT emit any other top-level key. Do NOT
emit a bare top-level array.

The 'line' field for this bucket is a pass/fail condition, KPI cutoff,
validation gate, or deadline that triggers a decision. Write each gate as
an if/then sentence so the condition AND the consequence read in the
correct logical direction.

Template shape (substitute the actual metric, comparison, threshold, and
consequence from the source):
- 'If <failure condition>, then <consequence>.'

Examples of the right direction (these are templates — substitute values
from the source, do not copy the literals):
- 'If <metric> falls below <threshold>, then <consequence>.'
- 'If <approval> is not granted by <date>, then <consequence>.'
- 'If <ratio> exceeds <threshold>, then <surcharge/contingency action>.'

Write the failure case as the if-clause. Avoid the inverted form where the
gate reads as 'X must Y, else Z' — that pattern flips the logical direction
and a downstream extractor can misread the boolean.

A gate must be expressible as a threshold, boolean, ratio, surplus, or
deficit. If something is a qualitative trade-off without a pass/fail edge,
leave it out. If a condition is named but no numeric threshold is given in
the source, put the missing threshold in missing_data_to_estimate rather
than emitting a vague gate like 'must meet a threshold'.

At most 8 items.
""".strip() + "\n\n" + _SCORING_DISCIPLINE


_RISKS_AND_SHOCKS_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the risks_and_shocks list.

Output exactly one JSON OBJECT with key 'risks_and_shocks' whose value is
a list of scored items. Do NOT emit any other top-level key. Do NOT emit
a bare top-level array.

The 'line' field for this bucket is a trigger plus modelling-relevant
impact. Template shape (substitute from the source):
- '<trigger>: <quantitative or operationally specific impact>'

A risk is a downside scenario that could happen — an external shock, a
demand collapse, a supply disruption, a capacity overload, a regulatory
rejection. It is NOT the same as a gate/threshold (which is a pass/fail
condition you actively check). If you have already produced an item in
gates_and_thresholds, do not restate it here.

Skip purely qualitative risks that do not name a number, a date, a capacity,
or an operationally specific failure mode. If you include a scenario
shock whose magnitude the source does not state, set source_status to
'inferred' and source_evidence to 1 — do not present invented shock
magnitudes as if they were plan facts.

At most 8 items.
""".strip() + "\n\n" + _SCORING_DISCIPLINE


_MISSING_DATA_BUCKET_PROMPT = """
Your job for THIS call: produce ONLY the missing_data_to_estimate list.

Output exactly one JSON OBJECT with key 'missing_data_to_estimate' whose
value is a list of scored items. Do NOT emit any other top-level key. Do
NOT emit a bare top-level array.

The 'line' field for this bucket names a PRIMITIVE input the model would
need but the section does not supply. A primitive is a single quantity
with a unit (currency/month, kWh, hours, count, percent). State what is
missing AND how to estimate it.

Template shape:
- '<missing primitive quantity with unit> — <how to estimate>'

Prefer primitives over derived quantities. Avoid words like 'gap',
'shortfall', 'surplus', 'versus', 'coverage', 'feasibility' unless you are
naming a formula explicitly; if a derived quantity is missing, decompose
it into the primitives that go into it.

Note: by definition these items are absent from the source, so
source_quote will usually be 'NOT IN SOURCE' and source_evidence will be
1. When the section EXPLICITLY says 'we need to estimate X', you may
quote that phrase and raise source_evidence accordingly.

At most 6 items.
""".strip() + "\n\n" + _SCORING_DISCIPLINE


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

# Public list buckets are capped to the top-N items after the LLM-side
# cap, sorted by (modelling_relevance * source_evidence) with a bonus for
# items whose quote was code-verified. The LLM is asked to over-produce so
# the Python sort can drop the weakest candidates; everything stays in
# metadata for inspection.
_MAX_ITEMS_PER_BUCKET = 6

# Buckets whose schema is list[_ScoredItem] (i.e. everything except
# section_summary). The order matches _BUCKET_SPECS below.
_SCORED_LIST_FIELDS: tuple[str, ...] = (
    "numeric_values",
    "load_bearing_assumptions",
    "gates_and_thresholds",
    "risks_and_shocks",
    "missing_data_to_estimate",
)


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


def _annotate_scored_items(
    items: list[_ScoredItem],
    section_markdown: str,
) -> tuple[list[ScoredItem], list[dict]]:
    """Verify each item's quote, sort by composite confidence, and return
    the top survivors as rich ``ScoredItem`` objects.

    The LLM produces ``_ScoredItem`` (line + scores + status + quote). For
    each, we substring-check the quote against the source markdown, build
    a ``ScoredItem`` with ``quote_verified`` set accordingly, sort by
    ``source_evidence * modelling_relevance`` (with a bonus for verified
    items), and keep the top ``_MAX_ITEMS_PER_BUCKET``. The full set of
    scored items (including dropped ones) is returned as a list of dicts
    so the caller can stash them in metadata for inspection.
    """
    scored_dicts: list[dict] = []
    annotated_pairs: list[tuple[int, ScoredItem]] = []
    for llm_item in items:
        verified = _quote_is_in_source(llm_item.source_quote, section_markdown)
        public_item = ScoredItem(
            **llm_item.model_dump(),
            quote_verified=verified,
        )
        scored_dicts.append(public_item.model_dump())
        sort_key = (
            llm_item.source_evidence * llm_item.modelling_relevance
            + (10 if verified else 0)
        )
        annotated_pairs.append((sort_key, public_item))

    annotated_pairs.sort(key=lambda pair: pair[0], reverse=True)
    kept = [item for _, item in annotated_pairs[:_MAX_ITEMS_PER_BUCKET]]
    return kept, scored_dicts


def _format_scored_item_line(item: ScoredItem) -> str:
    """Render one ScoredItem as a markdown bullet body.

    Format mirrors the v10 inline-tag convention so the downstream
    consumer's expectations do not change with the schema refactor.
    """
    tag = (
        f"[{item.source_status} | "
        f"e={item.source_evidence} r={item.modelling_relevance} | "
        f"quote: {'verified' if item.quote_verified else 'unverified'}]"
    )
    return f"{item.line}  {tag}"


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
            if spec.field_name in _SCORED_LIST_FIELDS:
                bucket_values[spec.field_name], scored_items = _annotate_scored_items(
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

        sections: list[tuple[str, list[ScoredItem]]] = [
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
                rendered = _format_scored_item_line(item).replace("\n", " ").strip()
                lines.append(f"- {rendered}")
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
