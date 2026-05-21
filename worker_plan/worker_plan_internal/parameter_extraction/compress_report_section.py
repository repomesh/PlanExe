"""
Compress one verbose PlanExe report section (Selected Scenario, Review Plan,
Premortem, Expert Criticism) into a small Markdown digest that preserves the
signal a downstream parameter-extraction LLM needs for napkin math and Monte
Carlo modelling.

Schema design: split, single-field calls
----------------------------------------
Each compression call asks the LLM for ONE field. Six calls per section
produce one ``CompressedReportSection``:

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

There are 4 sections getting compressed, with 6 LLM calls per section.
In total 24 (4 x 6) LLM calls.

To actually run the pipeline against PlanExe sample artifacts, use the
driver:

PROMPT> python -m worker_plan_internal.parameter_extraction.run_compress_full
"""
import json
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from math import ceil
from pathlib import Path
from typing import Any, Literal, Optional

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


OPTIMIZE_INSTRUCTIONS = """\
Goal: produce digests that preserve the modelling signal a downstream
parameter-extraction LLM needs, without leaking the contents of the
evaluation corpus into the prompts themselves.

Pipeline context
----------------
This module is Stage 1 of the napkin_math pipeline:

  1. compress_report_section          ← you are here (4 sections × 6 buckets)
  2. extract-parameters-from-digest   — reads the compressed digest
  3. validate-parameters              — deterministic structural checks
  4. generate-bounds                  — low/base/high per variable
  5. generate-calculations            — Python module of formulas
  6. run-scenarios                    — deterministic three-point
  7. monte-carlo                      — sampled distributions
  8. summarize-assessment             — gate verdicts, slideshow

Each downstream stage assumes the bucket schema and field semantics
encoded here. A change to a bucket prompt is a change to the contract
the whole pipeline relies on — re-run the napkin_math 14-plan
baseline before merging, not just unit tests.

Anti-overfitting: NEVER bake corpus content into the prompts
-------------------------------------------------------------
These prompts are evaluated against the napkin_math plan baseline used
by Self-Improve and the smoke fixtures. Specific phrases from any
baseline plan MUST NOT appear in the prompt text. That includes — but
is not limited to:

- Concrete numeric values from any baseline plan (a currency amount,
  an area figure, a capacity figure, a deadline). If the prompt
  example paraphrases a value the test plan also contains, the model
  is being told the answer, not taught the pattern.
- Named entities or acronyms from any baseline plan (the name of a
  regulator, a protocol, a project phase, an industry-specific
  artefact). These leak the structure of the test inputs even when
  the numbers are abstracted.
- Variable names that match what the downstream extract is expected
  to emit (the specific snake_case ids the calculations stage will
  call by name). Putting the desired output name in the prompt
  collapses the test from "did the extract pick the right
  decomposition?" to "did it copy the suggested name?"
- Domain-specific framings that fit only one or two corpus plans
  (the jargon of a single industry, the failure mode of a single
  project). Even if no number leaks, the framing tells the model
  which corpus member the prompt is targeting.

Use abstract placeholder shapes only: '<rate>', '<denominator>',
'<requirement>', '<consequence>', '<period>'. The structural rule
must read identically whether the model is summarising a renewable-
energy plan, a renovation project, a public-benefit policy, or a
language no one on the team reads. PlanExe inputs are multilingual
and span domains; English-only or commercially-biased examples in a
prompt are themselves a form of overfitting.

This banner itself is held to the same rule: it lists categories of
forbidden content but does NOT cite concrete examples from the
evaluation corpus. A list of literal corpus terms here would rot the
moment the baseline shifts and would itself be a corpus leak in the
source file — exactly the failure mode the rule forbids.

If a concrete example feels necessary to anchor a rule, pick a domain
that demonstrably does NOT appear in the napkin_math baseline AND
flag it as illustrative. The safer default is to skip the example
and let the abstract template do the work.

Regression probes are not acceptance criteria
---------------------------------------------
The baseline plans exist to surface failure patterns, NOT to define
what these prompts should target. A prompt edit that "fixes plan X" by
encoding plan X's specifics is overfitting in another form: even if
plan X's literals never enter the prompt verbatim, picking the rule
shape from one plan's behaviour without testing against many will fit
one and miss the others.

When a baseline plan reveals a failure mode:
1. Diagnose the abstract pattern, not the plan-specific symptom. Ask
   "what category of source content is being mishandled?" rather than
   "what does plan X need this bucket to do?"
2. Write the rule in corpus-agnostic language: structural categories
   (rate, denominator, threshold, gate, capacity, sum, decomposition),
   not domain nouns. Multilingual, multi-domain, multi-scale.
3. Verify the rule moves behaviour across MULTIPLE probe plans, not
   just the one that originally failed. A rule that lifts plan X but
   flattens plan Y is a tradeoff, not progress, and needs an explicit
   structural justification.

Report a prompt edit's effect in terms of:
- Which structural rule changed.
- Which corpus-agnostic behaviour it should improve.
- Which regression probes improved or worsened (across multiple
  plans, not one).
- Whether any baseline signal was dropped, and the structural reason
  the drop is acceptable.

Do not claim success because a single probe plan got a desired
variable. Claim success only when the general rule improves multiple
probes without adding corpus leakage and without silently losing
source-level signal elsewhere in the baseline.

Compress-LLM run-to-run variance is its own structural problem; do
NOT try to "fix" it by sharpening a bucket prompt to nudge the model
toward a specific selection it sometimes makes. Variance handling
belongs in orchestration (deterministic retry/merge across passes,
lower-temperature reruns for high-impact buckets), not in this file.

Known failure patterns to guard against
---------------------------------------
- Flattened per-period rates. The source states 'X per period', the
  numeric_values line records the bare amount, the denominator is
  lost, and downstream extract emits a flat bounded variable instead
  of the rate × duration decomposition. Fix: require the denominator
  in the label or unit field of any rate entry.
- Capacity requirements lost as gates. The source frames a minimum
  needed for a target capacity as a sizing calculation rather than a
  pass/fail. The gates_and_thresholds bucket skips it, the extract
  defaults the threshold to '>= 0', and the gate stops testing the
  real failure scenario. Fix: capacity requirements are gates,
  rewritten into if/then form by the compress stage.
- Burn rate / duration separation across sections. The rate lives in
  one PlanExe section, the matching duration in another. Compress
  sees one section at a time. Each section's missing_data bucket
  must therefore surface the *other half* of any rate × duration
  pair the section names, so extract sees both pieces in the digest.
- Per-period unit substitution. Models sometimes translate '/yr' to
  'annual' (or vice versa) in the label, silently. The verbatim rule
  for the value field already protects the unit field; the label
  must mirror the same discipline.
- Hardcoded English keywords in prompts. PlanExe receives reports in
  many languages; prompts that depend on English-only stems ('cost',
  'fee', 'overhead', 'budget') reject perfectly valid digests in
  other languages. Prefer structural cues ('a value divided by a
  period') over keyword lists.
- Numeric-example drift. Whenever a prompt mentions a number, ask:
  does this number appear in any baseline report? If yes — even
  approximately — replace it with a placeholder. Numbers that
  resemble corpus content are the most reliable signal of a
  prompt-eval leak.

When in doubt
-------------
Read the prompt edit and ask: "would a reader who has seen the
baseline plans guess which plan I had in mind when writing this?"
If yes, abstract harder. The prompt is for the model, not for a
human reviewing the baseline.
"""


class LenientJsonModel(BaseModel):
    """BaseModel whose `model_validate_json` tolerates trailing characters.

    Small structured-output LLMs (notably Gemini Flash Lite) occasionally
    emit a valid JSON object followed by extra tokens. Pydantic's strict
    validator rejects the whole payload with `json_invalid` ("trailing
    characters"), wasting retries on a response whose prefix is already
    correct. This override falls back to `json.JSONDecoder().raw_decode`
    to peel off the first balanced JSON value and validates that. If the
    extracted value still fails schema validation, the original error is
    re-raised so genuine schema problems are not hidden.
    """

    @classmethod
    def model_validate_json(cls, json_data, **kwargs):
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as primary_error:
            if not _is_trailing_characters_error(primary_error):
                raise
            text = _coerce_to_str(json_data)
            if text is None:
                raise
            try:
                first_value, _ = json.JSONDecoder().raw_decode(text.lstrip())
            except json.JSONDecodeError:
                raise primary_error
            return cls.model_validate(first_value, **kwargs)


def _is_trailing_characters_error(err: ValidationError) -> bool:
    for error in err.errors():
        if error.get("type") == "json_invalid" and "trailing" in error.get("msg", "").lower():
            return True
    return False


def _coerce_to_str(json_data: Any) -> Optional[str]:
    if isinstance(json_data, str):
        return json_data
    if isinstance(json_data, (bytes, bytearray)):
        try:
            return json_data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


class ReportSectionTypeEnum(str, Enum):
    SELECTED_SCENARIO = "selected_scenario"
    REVIEW_PLAN = "review_plan"
    PREMORTEM = "premortem"
    EXPERT_CRITICISM = "expert_criticism"
    UNKNOWN = "unknown"


# ScoredItem is the LLM-facing per-item schema shared by every list bucket
# (numeric_values, load_bearing_assumptions, gates_and_thresholds,
# risks_and_shocks, missing_data_to_estimate). The class docstring is
# emitted into the structured-output schema and shown to the LLM, so it is
# kept minimal — the bucket prompts carry the actual per-bucket instructions
# and the field descriptions below carry the per-field meaning. Anything
# the LLM does not need to know (quote_verified is computed post-call, etc.)
# belongs in this comment, not the docstring.
class ScoredItem(BaseModel):
    """One scored entry produced for a single compressed-section bucket."""

    line_english: str = Field(
        description=(
            "The bucket-specific content rendered in clean English. ALL "
            "structural words must be English; a source-language term may "
            "appear in parentheses only when no good English equivalent "
            "exists. Never produce a hybrid sentence that mixes two "
            "languages mid-clause."
        )
    )
    line_original: str = Field(
        description=(
            "The same content in the source's primary language, preserving "
            "the source's own terminology verbatim. If the source is fully "
            "English, this is identical to ``line_english``. If the source "
            "is in another language (Danish, Spanish, etc.), this is the "
            "original-language version with native technical/legal terms "
            "left intact."
        )
    )
    modelling_relevance: int = Field(
        description="1-5 Likert: usefulness for Monte Carlo / napkin-math modelling."
    )
    source_evidence: int = Field(
        description="1-5 Likert: how directly the source supports this exact value+label (1 = invented)."
    )
    source_status: Literal[
        "explicit", "derived", "inferred", "stress_test", "missing"
    ] = Field(
        description=(
            "'explicit' = literally stated in the source; "
            "'derived' = computed from explicit source values; "
            "'inferred' = a plausible business assumption you added that the "
            "source does not state; "
            "'stress_test' = a downside scenario magnitude (cost of a "
            "failure, duration of a disruption, lost revenue under a "
            "failure mode) — never a plan fact. Premortem shock magnitudes "
            "are 'stress_test' by default; "
            "'missing' = a primitive input the plan needs but the source "
            "does not supply a value for. Used for every item in the "
            "missing_data_to_estimate bucket — the bucket name already says "
            "the value is absent, so the status records that the entry "
            "describes a NEED, not a known fact. "
            "When in doubt prefer 'inferred' over 'explicit', and "
            "'stress_test' over 'inferred' for shock magnitudes."
        )
    )
    source_quote: str = Field(
        description="≤12 word verbatim fragment from the source, or 'NOT IN SOURCE'."
    )


class PublicScoredItem(ScoredItem):
    """Public per-item shape for compressed list-bucket entries.

    Inherits the LLM-populated fields from ``ScoredItem`` and adds
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
    """Assembled output of the six per-bucket extraction calls.

    This model is the host-side container that ``execute()`` returns; it is
    never used as a structured-output target for an LLM call, so its fields
    carry no ``description`` (which would be dead documentation aimed at no
    audience). The per-bucket meaning lives in the bucket prompts and in
    ``PublicScoredItem``.
    """

    section_summary: str
    numeric_values: list[PublicScoredItem] = Field(default_factory=list)
    load_bearing_assumptions: list[PublicScoredItem] = Field(default_factory=list)
    gates_and_thresholds: list[PublicScoredItem] = Field(default_factory=list)
    risks_and_shocks: list[PublicScoredItem] = Field(default_factory=list)
    missing_data_to_estimate: list[PublicScoredItem] = Field(default_factory=list)


SECTION_TYPE_BY_STEM = {
    "selected_scenario": ReportSectionTypeEnum.SELECTED_SCENARIO.value,
    "review_plan": ReportSectionTypeEnum.REVIEW_PLAN.value,
    "premortem": ReportSectionTypeEnum.PREMORTEM.value,
    "expert_criticism": ReportSectionTypeEnum.EXPERT_CRITICISM.value,
}

SECTION_GUIDANCE = {
    ReportSectionTypeEnum.SELECTED_SCENARIO.value: (
        "This is the Selected (picked) Scenario — the actual plan to model, not the "
        "menu of options. The signal is in what the plan *committed to*. "
        "Keep: chosen strategy name, explicit commitments and the numbers attached to "
        "them (budget envelope, contingency %, revenue mix, deadlines, conversion "
        "targets), viability gates for the chosen strategy, risk buffers and "
        "mitigations. "
        "Scenario-boundary rule (HARD): only include items that belong to the selected "
        "baseline scenario. The candidate-scenarios input enumerates several named "
        "scenarios; only one of them is the chosen baseline (identified by the "
        "selected_scenario.json content). Every other named scenario is a rejected "
        "alternative and must not produce numeric_values, load_bearing_assumptions, "
        "gates_and_thresholds, or risks_and_shocks. A rejected alternative may be "
        "named in source_quote ONLY for disambiguation. Do NOT write gates of the "
        "form 'If the <rejected scenario name> were chosen, then ...' — that is "
        "modelling the wrong plan. Do NOT include numbers that quantify only a "
        "rejected alternative (e.g. 'zero contingency under the high-risk option'). "
        "Drop also: speculative trade-offs the plan ultimately did not pick, generic "
        "'option A vs B' narrative. If a rejected alternative is mentioned only for "
        "disambiguation, do not treat its numbers as commitments of the chosen plan."
    ),
    ReportSectionTypeEnum.REVIEW_PLAN.value: (
        "This is the Review Plan — the *review document* that examines the plan's "
        "validation questions, KPI thresholds, fragile assumptions, gates, and "
        "missing-evidence flags. The signal is in *what must be CHECKED* and *what "
        "FAILS if it is not*. "
        "Do NOT frame the digest as 'a list of strategic decisions'. The source may "
        "enumerate decisions because they are being reviewed, but the compressed "
        "output is about the review's gates, validation questions, and required "
        "evidence — not about restating the decisions themselves. "
        "Keep: validation questions, KPI thresholds, fragile assumptions called out "
        "for review, deadlines tied to gates, missing-evidence flags. Drop: review-"
        "process descriptions, methodology prose, generic 'we will review' lines, "
        "and any narrative that merely lists the decisions rather than reviewing them."
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
You compress one verbose project-plan section so that a downstream
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
  an empty list
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
- do not duplicate items you have already produced in another bucket; each
  bucket captures a distinct kind of signal

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
  VALUES, not the schema structure. Wrong: {"properties":{"<field>":
  {"type":"string"}}}. Right: {"<field>":"<your actual answer>"}.
  Wrong: {"type":"array","items":{...}}. Right: the field's value directly.
""".strip()


# ---------------------------------------------------------------------------
# Per-bucket schemas. Each call uses a single-field Pydantic model so the LLM
# never has to balance attention across multiple lists in one response.
# ---------------------------------------------------------------------------


BUCKET_FIELD_DESC = "See the bucket prompt in the user message for the expected content."


class SectionSummaryOnly(LenientJsonModel):
    section_summary: str = Field(description=BUCKET_FIELD_DESC)


class NumericValuesOnly(LenientJsonModel):
    numeric_values: list[ScoredItem] = Field(
        default_factory=list, description=BUCKET_FIELD_DESC,
    )


class LoadBearingAssumptionsOnly(LenientJsonModel):
    load_bearing_assumptions: list[ScoredItem] = Field(
        default_factory=list, description=BUCKET_FIELD_DESC,
    )


class GatesAndThresholdsOnly(LenientJsonModel):
    gates_and_thresholds: list[ScoredItem] = Field(
        default_factory=list, description=BUCKET_FIELD_DESC,
    )


class RisksAndShocksOnly(LenientJsonModel):
    risks_and_shocks: list[ScoredItem] = Field(
        default_factory=list, description=BUCKET_FIELD_DESC,
    )


class MissingDataOnly(LenientJsonModel):
    missing_data_to_estimate: list[ScoredItem] = Field(
        default_factory=list, description=BUCKET_FIELD_DESC,
    )


# ---------------------------------------------------------------------------
# Per-bucket system prompts. Each is concatenated with the shared preamble at
# call time.
# ---------------------------------------------------------------------------


SECTION_SUMMARY_BUCKET_PROMPT = """
Write one to three sentences in plain English describing what this section
contributes to Monte Carlo / napkin-math modelling. No markdown, no bullet
points, no lists. Do not enumerate numbers or assumptions — those are
handled in other calls.
""".strip()


# Shared scoring rules that apply identically to every list bucket. Each
# per-bucket prompt below appends this block so the LLM sees the same
# discipline regardless of which bucket it is currently producing.
SCORING_DISCIPLINE = """
Every item in the list is a scored object with six fields: line_english,
line_original, modelling_relevance, source_evidence, source_status,
source_quote.

Language rule (apply to every item):
- line_english: clean English version. ALL structural words must be in
  English. A source-language term may appear in parentheses only when no
  good English equivalent exists (e.g. 'kontingens (contingency)' is wrong
  — write 'contingency'; 'utility variance approval' is fine even when
  the source calls it 'forsyningsvariansgodkendelse'). Never produce a
  hybrid sentence that mixes two languages mid-clause.
- line_original: the same content in the source's primary language,
  preserving the source's own terminology verbatim. If the source is
  fully English, line_original is identical to line_english. If the
  source contains non-English text, line_original keeps the native
  spelling and technical terms intact.

Quantity annotation rule (apply to every item):
- When the source states a count as a word (in any language: "two",
  "twelve", "a dozen", "half a hundred", "to", "deux", "zwei", …),
  annotate the digit form parenthetically in line_english after the
  count word. Examples: "four (4) part-time instructors", "a dozen (12)
  weekly drop-in sessions", "two (2) FTE equivalents". This applies to
  the line_english field only; line_original keeps the source's native
  phrasing without the digit annotation.
- Do NOT digit-annotate vague quantifiers — "several", "a handful",
  "many", "few", "some", "various", "a number of" are not counts and
  must NOT be expanded into invented digits. If you do not know the
  count, leave the word unannotated.

Scoring rules (identical across buckets):
- modelling_relevance (1-5): how useful this item is for Monte Carlo /
  napkin-math modelling. 5 = primary driver of viability; 1 = irrelevant
  narrative.
- source_evidence (1-5): how directly the source text supports this exact
  item. 5 = near-verbatim quote present in the section; 1 = you invented
  it. Be honest.
- source_status: pick exactly one of these five values. The distinction is
  about what KIND of statement the line makes, not whether the source
  quantifies it.
    * 'explicit' — a PLAN COMMITMENT the source states directly. The plan
      is binding itself to this number, date, ratio, or condition. Total
      budget, allocated contingency, target deadline, declared revenue
      mix, contracted price, committed staff count.
    * 'derived' — a value the plan implies but does not state directly,
      computable from one or more 'explicit' values.
    * 'inferred' — covers two cases: (a) a plausible assumption you
      added that the source does not state at all; (b) an item the
      source DOES state but only as an assumption, aspiration, expected
      behaviour, or non-binding claim — anything the plan is not
      binding itself to. "Local users will accept the high rental rate"
      is 'inferred', even when the source contains that exact sentence,
      because the plan does not bind users to accept it; it is a claim
      the simulation should stress-test. Reserve 'explicit' for items
      the plan binds itself to (committed budget, allocated reserve,
      declared deadline, contracted price).
    * 'stress_test' — applies to lines that QUANTIFY THE DAMAGE of a
      failure outcome: the cost of a breakdown, the weeks of downtime,
      the lost revenue under a what-if, the deficit when an assumption
      breaks, the capacity shortfall during a shock. The defining trait
      is that the number measures *how bad it gets if something goes
      wrong*. Use this tag EVEN WHEN the source states the damage
      magnitude — a quantified failure outcome is still a stress test,
      not a plan commitment.
      Do NOT confuse the damage magnitude with the trigger threshold
      inside a gate. "If revenue falls below 70% of target, then pivot"
      is a gate: the 70% is the trigger threshold, not damage. The
      stress_test number, if there were one, would be a separate item
      naming what the pivot costs or how much revenue is lost. Gates
      stay 'explicit'/'derived'/'inferred' according to how the source
      establishes the threshold; assumptions and load-bearing claims do
      the same. stress_test belongs almost entirely in risks_and_shocks
      and in numeric_values lines that name a failure-outcome
      magnitude.
    * 'missing' — a primitive input the plan needs but the source does
      not supply. Used in the missing_data_to_estimate bucket; the
      status for items in that bucket will be overwritten to 'missing'
      regardless of what you set. Do NOT use 'missing' in any other
      bucket: if the source does not supply a value for an assumption,
      gate, risk, or numeric_value, use 'inferred' instead.
  Disambiguation tests, in order of priority:
  1. Is this a quantification of what could go wrong (failure cost,
     downtime, lost revenue under a what-if, deficit when an assumption
     breaks)? If yes → 'stress_test', even when the source states the
     number.
  2. Otherwise, is the plan BINDING itself to this — a committed
     budget, allocated reserve, declared deadline, contracted rate,
     committed staff count? If yes → 'explicit'.
  3. Otherwise, does the source state this as an assumption,
     aspiration, expected behaviour, or non-binding claim that the
     simulation would want to stress-test? If yes → 'inferred'.
  4. Otherwise it's something you added without source support →
     'inferred' (and source_evidence should be 1).
  When in doubt prefer 'inferred' over 'explicit'.
- source_quote: a SHORT (≤12 word) verbatim or near-verbatim fragment from
  the section that supports this item. If the item is not in the section,
  write 'NOT IN SOURCE' and set source_evidence to 1 and source_status to
  'inferred'.

Cast a wide net — surface borderline candidates with honest low scores
rather than self-censoring; the lowest-scoring items will be dropped
after ranking, so the cost of including a weak candidate is small and the
cost of missing a real one is large. But never *invent* a specific value
where the source is silent — mark such guesses 'inferred' with
source_evidence 1 if you include them at all.

Keep each source_quote to ≤12 words so the response stays within the
output budget.
""".strip()


NUMERIC_VALUES_BUCKET_PROMPT = """
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

Per-period and per-unit rates (important): when the source expresses a
quantity as a rate (a value divided by some period or some other unit),
the label MUST carry the denominator so the rate stays visible
downstream. Write the label as '<quantity> per <denominator>' or
include the denominator in the unit field (e.g. '<unit>/<denominator>').
A flat label that drops the denominator is invalid when the source
states one — the downstream extract can no longer reconstruct the
multiplication. For these rate entries the modelling role should
describe the multiplication structure rather than just naming the cost,
so a downstream stage can identify the matching scaling input.

Source-stated rates belong in this bucket, not in missing_data. If the
source names a per-period or per-unit rate at all — explicitly,
inferred, as a recommended range, or as a stress_test magnitude — emit
it as a numeric_value with the denominator preserved. Setting
source_status to 'inferred' or 'stress_test' is fine when the source's
framing fits; do NOT route a rate-like quantity to missing_data merely
because the source gives it as a range, a recommendation, or an
expert's estimate rather than as a single committed value.
missing_data_to_estimate is reserved for primitives the source does NOT
name. A rate the source mentions, even imprecisely, has been named and
must surface here with its denominator intact.

A total cost that the source ALSO frames as a per-period burn must
appear here in BOTH forms when the source supplies both: one entry for
the total (with its absolute label) and one entry for the rate (with
the per-period denominator). Listing only the total flattens the burn
structure; listing only the rate hides the source's own committed total.

Template shape (substitute values from the source — DO NOT copy these
placeholders or any unit from them):
- '<what the number is>: <amount> <currency-from-source> — <modelling role>.'
- '<what the number is>: <percent>% — <modelling role>.'
- '<what the number is>: <date-from-source> — <modelling role>.'
- '<what the rate is> per <denominator>: <amount> <unit-from-source>/<denominator> — <modelling role describing what it scales with>.'

If the source contains conflicting values for the same quantity, list each
with a disambiguating label (e.g. 'minimum', 'aspirational') rather than
picking one silently.

Skip numbers that only appear for narrative color. At most 8 items, sorted
by your judgement of importance for modelling. Fewer items is fine.
""".strip() + "\n\n" + SCORING_DISCIPLINE


LOAD_BEARING_ASSUMPTIONS_BUCKET_PROMPT = """
The 'line' field for this bucket is a complete short sentence stating the
assumption itself, in 25 words or fewer. Prefer assumptions that have an
obvious modelling consequence — regulatory permissions, demand
assumptions, supply assumptions, cost-stability assumptions, capacity
assumptions. Do not enumerate supporting numbers in the line — numbers
belong in numeric_values.

At most 8 items.
""".strip() + "\n\n" + SCORING_DISCIPLINE


GATES_AND_THRESHOLDS_BUCKET_PROMPT = """
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

Capacity requirements count as gates. When the source states a numeric
minimum needed to physically support a declared capacity, output, or
service level, the requirement IS the gate — even when the source
frames it as a sizing calculation rather than an explicit pass/fail
condition. Write it in the if/then form: 'If <quantity> falls below
<required value>, then <the supported capacity cannot be achieved>.'
Do not skip such requirements just because the source phrases them as
sizing math instead of a gate.

At most 8 items.
""".strip() + "\n\n" + SCORING_DISCIPLINE


RISKS_AND_SHOCKS_BUCKET_PROMPT = """
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
""".strip() + "\n\n" + SCORING_DISCIPLINE


MISSING_DATA_BUCKET_PROMPT = """
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

Denominator-pairing rule (important): the earlier buckets already
captured rates, shares, percentages, per-unit prices, conversion rates,
utilization targets, FTE counts, and failure-duration magnitudes. Each
of those needs a matching denominator or scaling input to become an
executable formula. For every such rate-like or per-unit item in the
prior buckets that the section does NOT otherwise quantify, surface its
missing counterpart here. Patterns to look for:
- A share-of-revenue percentage needs the absolute period-revenue
  target.
- A per-hour, per-day, or per-unit price needs the billable hours, days,
  or units per period the price will be applied to.
- A conversion or adoption rate needs the count of attendees,
  candidates, or eligible people the rate operates on.
- An FTE or headcount value needs the per-head monthly or annual cost.
- A failure-duration magnitude (weeks of downtime, days of disruption)
  needs the per-week or per-day revenue exposure the failure interrupts.
- An overhead coverage threshold ('cover 75% of X') needs the absolute
  X amount per period.
- A per-period burn rate (any cost or output expressed as a value per
  unit of time) needs the matching duration the rate will be
  multiplied by — the count of those time units the burn applies for.
  Without the duration, the rate cannot be turned into a total and the
  multiplication is lost downstream.
Do not invent a value; just name the missing primitive and how it
would be estimated. Skip this pairing only when the section already
supplies the denominator elsewhere.

Note: by definition these items are absent from the source. Always set
source_status to 'missing' for items in this bucket. When the source has
no value, source_quote is 'NOT IN SOURCE' and source_evidence is 1. When
the section EXPLICITLY says 'we need to estimate X', you may quote that
phrase and raise source_evidence accordingly — but source_status still
stays 'missing' because the value itself is what's absent.

At most 6 items.
""".strip() + "\n\n" + SCORING_DISCIPLINE


@dataclass(frozen=True)
class BucketSpec:
    field_name: str
    schema: type[BaseModel]
    bucket_prompt: str


BUCKET_SPECS: tuple[BucketSpec, ...] = (
    BucketSpec("section_summary", SectionSummaryOnly, SECTION_SUMMARY_BUCKET_PROMPT),
    BucketSpec("numeric_values", NumericValuesOnly, NUMERIC_VALUES_BUCKET_PROMPT),
    BucketSpec(
        "load_bearing_assumptions",
        LoadBearingAssumptionsOnly,
        LOAD_BEARING_ASSUMPTIONS_BUCKET_PROMPT,
    ),
    BucketSpec(
        "gates_and_thresholds",
        GatesAndThresholdsOnly,
        GATES_AND_THRESHOLDS_BUCKET_PROMPT,
    ),
    BucketSpec("risks_and_shocks", RisksAndShocksOnly, RISKS_AND_SHOCKS_BUCKET_PROMPT),
    BucketSpec("missing_data_to_estimate", MissingDataOnly, MISSING_DATA_BUCKET_PROMPT),
)


# Per-bucket call attempts before giving up. Small models like Llama 3.1 8B
# occasionally emit malformed JSON, drop required fields, or truncate mid-
# list; retrying the same chat history usually succeeds because each attempt
# samples fresh.
PER_BUCKET_MAX_ATTEMPTS = 3

# Public list buckets are capped to the top-N items after the LLM-side
# cap, sorted by a composite score combining the LLM's self-rated
# source_evidence * modelling_relevance, a code-side quote-verification
# bonus, and a numeric-density bonus. The LLM is asked to over-produce so
# the Python sort can drop the weakest candidates; everything stays in
# metadata for inspection.
MAX_ITEMS_PER_BUCKET = 6

# Digit-led tokens, used to count numeric content in a candidate line.
# Numbers are universal across languages and across plan domains
# (commercial budgets, renovation square-metre counts, public-health
# coverage rates, …), so a numeric-density bonus does not bias the
# ranking toward any one input language or plan type. Matches things
# like ``2,000,000``, ``0.15``, ``2026-09-15``.
NUMBER_PATTERN: re.Pattern[str] = re.compile(r"\d[\d,.]*")

# Bonus weights for the composite score. The verified-quote bonus (10)
# is the largest because code-verified provenance is the strongest single
# trust signal. The numeric-density bonus is smaller and capped so a
# heavily-quantified item cannot overwhelm a well-evidenced qualitative
# one.
VERIFIED_QUOTE_BONUS: int = 10
NUMERIC_DENSITY_BONUS_PER_TOKEN: float = 1.0
NUMERIC_DENSITY_BONUS_CAP: float = 3.0

# Buckets whose schema is list[ScoredItem] (i.e. everything except
# section_summary). The order matches BUCKET_SPECS below.
SCORED_LIST_FIELDS: tuple[str, ...] = (
    "numeric_values",
    "load_bearing_assumptions",
    "gates_and_thresholds",
    "risks_and_shocks",
    "missing_data_to_estimate",
)

# For buckets where the bucket name already determines the right
# source_status, override whatever the LLM emitted. The
# missing_data_to_estimate bucket is by definition about absent values, so
# every entry there is 'missing' — the LLM occasionally tags them
# 'explicit' because the NEED was explicit in the source, which confuses
# the downstream consumer.
FORCED_STATUS_BY_BUCKET: dict[str, str] = {
    "missing_data_to_estimate": "missing",
}


def normalise_for_quote_match(text: str) -> str:
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


def quote_is_in_source(quote: str, section_markdown: str) -> bool:
    if not quote:
        return False
    if quote.strip().upper() == "NOT IN SOURCE":
        return False
    return normalise_for_quote_match(quote) in normalise_for_quote_match(section_markdown)


def numeric_density_bonus(text: str) -> float:
    """Bonus for lines carrying numeric tokens (currency amounts, dates,
    percentages, square metres). A bare-prose claim with no numbers is
    less useful for napkin math than one with explicit quantities.
    Language- and domain-neutral: digits are digits in any plan.
    """
    count = len(NUMBER_PATTERN.findall(text))
    return min(count * NUMERIC_DENSITY_BONUS_PER_TOKEN, NUMERIC_DENSITY_BONUS_CAP)


def composite_score(
    item: "ScoredItem",
    quote_verified: bool,
) -> float:
    """Combine the LLM-self-rated base score with code-side bonuses.

    base = source_evidence * modelling_relevance  (range 1..25)
    + verified-quote bonus                        (0 or 10)
    + numeric-density bonus                       (0..3)

    Items with a code-verified quote always outrank otherwise-equivalent
    unverified items. The numeric-density bonus then breaks ties toward
    quantified content. Both signals are language- and domain-neutral.
    """
    haystack = f"{item.line_english} {item.source_quote}"
    return (
        item.source_evidence * item.modelling_relevance
        + (VERIFIED_QUOTE_BONUS if quote_verified else 0)
        + numeric_density_bonus(haystack)
    )


def annotate_scored_items(
    items: list[ScoredItem],
    section_markdown: str,
    field_name: str,
) -> tuple[list[PublicScoredItem], list[dict]]:
    """Verify each item's quote, sort by composite confidence, and return
    the top survivors as rich ``PublicScoredItem`` objects.

    The LLM produces ``ScoredItem`` (line + scores + status + quote). For
    each, we substring-check the quote against the source markdown, build
    a ``PublicScoredItem`` with ``quote_verified`` set accordingly, sort by
    ``composite_score`` (LLM-self-rated evidence × relevance plus
    code-side bonuses for verified quote, protected modelling terms,
    numeric density, and formula-cue presence), and keep the top
    ``MAX_ITEMS_PER_BUCKET``. The full set of scored items (including
    dropped ones) is returned as a list of dicts so the caller can stash
    them in metadata for inspection.

    For buckets listed in ``FORCED_STATUS_BY_BUCKET`` (currently just
    ``missing_data_to_estimate``), the ``source_status`` is overwritten
    after the LLM call — the bucket name already determines the right
    status and we should not let the LLM disagree.
    """
    forced_status = FORCED_STATUS_BY_BUCKET.get(field_name)
    scored_dicts: list[dict] = []
    annotated_pairs: list[tuple[float, PublicScoredItem]] = []
    for llm_item in items:
        verified = quote_is_in_source(llm_item.source_quote, section_markdown)
        item_dict = llm_item.model_dump()
        if forced_status is not None:
            item_dict["source_status"] = forced_status
        public_item = PublicScoredItem(
            **item_dict,
            quote_verified=verified,
        )
        scored_dicts.append(public_item.model_dump())
        annotated_pairs.append((composite_score(llm_item, verified), public_item))

    annotated_pairs.sort(key=lambda pair: pair[0], reverse=True)
    kept = [item for _, item in annotated_pairs[:MAX_ITEMS_PER_BUCKET]]
    return kept, scored_dicts


def format_scored_item_line(item: PublicScoredItem) -> str:
    """Render one PublicScoredItem as a markdown bullet body.

    The clean English version is the primary text. The native-language
    version is kept in JSON only — downstream consumers that need verbatim
    source terminology can read it from the raw output. The inline tag
    surfaces source_status, the two scores, and the code-side quote
    verification so a downstream LLM can weigh the item by epistemic
    confidence without parsing JSON.
    """
    tag = (
        f"[{item.source_status} | "
        f"e={item.source_evidence} r={item.modelling_relevance} | "
        f"quote: {'verified' if item.quote_verified else 'unverified'}]"
    )
    return f"{item.line_english}  {tag}"


SECOND_PASS_USER_PROMPT_TEMPLATE = (
    "Review the {field_name} items you just produced above. "
    "Identify items present in the section that you missed. "
    "Emit only NEW items not already covered above; do not repeat or "
    "rephrase items you already produced. "
    "Apply the same bucket rules. "
    "Up to 8 new items. "
    "If you captured everything important on the first pass, return an "
    "empty list."
)


def merge_second_pass_items(
    first_pass: list[ScoredItem],
    second_pass: list[ScoredItem],
) -> tuple[list[ScoredItem], int]:
    """Merge two batches of ScoredItem, de-duplicating second-pass items
    whose normalised source_quote already appears in the first pass.

    The second pass is gated by a "what did you miss?" prompt that asks the
    LLM to surface candidates absent from the first batch. Smaller models
    can mis-count near the per-bucket cap; the two-batch protocol keeps each
    call's cognitive load comparable to the original single-batch flow, and
    leaves the deterministic top-N filter (``annotate_scored_items``) to
    pick the survivors from the combined pool.

    Sometimes the model re-emits a first-pass item anyway; this merger
    drops those duplicates while preserving order: first-pass items come
    first, second-pass items follow in their emitted order, and any
    duplicate from the second pass is silently skipped.

    Returns ``(merged_list, newly_added_count)``.
    """
    seen = {normalise_for_quote_match(item.source_quote) for item in first_pass}
    merged = list(first_pass)
    newly_added = 0
    for item in second_pass:
        key = normalise_for_quote_match(item.source_quote)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        newly_added += 1
    return merged, newly_added


def infer_section_type_from_path(file_path: str | Path) -> str:
    """Infer the section type from a filename whose stem matches one of the
    known section names. Returns ``"unknown"`` if the stem is not recognised.
    """
    stem = Path(file_path).stem
    return SECTION_TYPE_BY_STEM.get(stem, ReportSectionTypeEnum.UNKNOWN.value)


def normalize_section_type(section_type: str | ReportSectionTypeEnum | None) -> str:
    """Normalise an optional section-type input to one of the schema values."""
    if section_type is None:
        return ReportSectionTypeEnum.UNKNOWN.value
    if isinstance(section_type, ReportSectionTypeEnum):
        return section_type.value
    text = str(section_type).strip().lower().replace("-", "_").replace(" ", "_")
    if text in SECTION_GUIDANCE:
        return text
    return SECTION_TYPE_BY_STEM.get(text, ReportSectionTypeEnum.UNKNOWN.value)


def build_user_prompt(
    section_markdown: str,
    section_type: str,
    section_title: Optional[str] = None,
) -> str:
    """Build the section-wrapper user prompt shared by all six bucket calls."""
    title = section_title or section_type.replace("_", " ").title()
    guidance = SECTION_GUIDANCE.get(
        section_type, SECTION_GUIDANCE[ReportSectionTypeEnum.UNKNOWN.value]
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

        for turn_index, spec in enumerate(BUCKET_SPECS):
            # The section context (the [START_SECTION_MARKDOWN]...
            # [END_SECTION_MARKDOWN] wrapper) is established on the very
            # first user turn and then reused implicitly by every later
            # turn via the accumulated chat history. Whichever bucket
            # happens to be first in BUCKET_SPECS gets the section
            # wrapper prepended to its own prompt.
            is_first_turn = turn_index == 0
            if is_first_turn:
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
            for retry in range(PER_BUCKET_MAX_ATTEMPTS):
                logger.debug(
                    f"Bucket {spec.field_name}: starting LLM call "
                    f"(turn {turn_index + 1}, attempt {retry + 1}/{PER_BUCKET_MAX_ATTEMPTS})"
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
                    f"{PER_BUCKET_MAX_ATTEMPTS} attempts. Last error: "
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

            # Append the first-pass assistant turn so the second pass (and
            # subsequent buckets) can see what was already produced and avoid
            # duplicating it.
            assistant_content_first = json.dumps(obj.model_dump(), separators=(",", ":"))
            accumulated_chat.append(
                ChatMessage(role=MessageRole.ASSISTANT, content=assistant_content_first)
            )

            # Second pass: for scored-list buckets only, ask the LLM what it
            # missed. Smaller models can mis-count near the per-bucket cap and
            # silently drop high-signal items on a single pass; the two-batch
            # protocol keeps each call's cognitive load comparable to the
            # original flow, with the deterministic scorer (annotate_scored_items
            # below) picking the survivors from the combined pool.
            if spec.field_name in SCORED_LIST_FIELDS:
                second_pass_user_content = SECOND_PASS_USER_PROMPT_TEMPLATE.format(
                    field_name=spec.field_name
                )
                accumulated_chat.append(
                    ChatMessage(role=MessageRole.USER, content=second_pass_user_content)
                )

                second_pass_start = time.perf_counter()
                second_pass_obj = None
                second_pass_chat_response = None
                second_pass_last_error: Optional[Exception] = None
                for retry in range(PER_BUCKET_MAX_ATTEMPTS):
                    logger.debug(
                        f"Bucket {spec.field_name} second pass: starting LLM call "
                        f"(attempt {retry + 1}/{PER_BUCKET_MAX_ATTEMPTS})"
                    )
                    try:
                        second_pass_chat_response = sllm.chat(accumulated_chat)
                        second_pass_obj = second_pass_chat_response.raw
                        if second_pass_obj is None:
                            raise ValueError(
                                f"Structured LLM returned None for bucket "
                                f"{spec.field_name!r} (second pass)."
                            )
                        break
                    except Exception as e:
                        second_pass_last_error = e
                        logger.warning(
                            f"Bucket {spec.field_name} second pass attempt "
                            f"{retry + 1} failed: {type(e).__name__}: "
                            f"{str(e)[:160]}"
                        )
                if second_pass_obj is None:
                    raise ValueError(
                        f"Bucket {spec.field_name!r} second pass failed after "
                        f"{PER_BUCKET_MAX_ATTEMPTS} attempts. Last error: "
                        f"{type(second_pass_last_error).__name__}: "
                        f"{second_pass_last_error}"
                    ) from second_pass_last_error
                second_pass_duration = int(ceil(time.perf_counter() - second_pass_start))
                second_pass_byte_count = len(
                    second_pass_chat_response.message.content.encode("utf-8")
                )
                logger.info(
                    f"Bucket {spec.field_name} second pass: completed in "
                    f"{second_pass_duration}s, {second_pass_byte_count} bytes"
                )

                first_pass_items = list(raw_field_value or [])
                second_pass_items = list(
                    getattr(second_pass_obj, spec.field_name) or []
                )
                merged_items, newly_added_count = merge_second_pass_items(
                    first_pass_items, second_pass_items
                )
                raw_field_value = merged_items

                # Append the second-pass assistant turn so subsequent buckets
                # see the full pool the LLM produced.
                assistant_content_second = json.dumps(
                    second_pass_obj.model_dump(), separators=(",", ":")
                )
                accumulated_chat.append(
                    ChatMessage(
                        role=MessageRole.ASSISTANT,
                        content=assistant_content_second,
                    )
                )

                bucket_metadata.update(
                    {
                        "second_pass_duration": second_pass_duration,
                        "second_pass_response_byte_count": second_pass_byte_count,
                        "second_pass_user_prompt": second_pass_user_content,
                        "first_pass_item_count": len(first_pass_items),
                        "second_pass_item_count": len(second_pass_items),
                        "newly_added_count": newly_added_count,
                    }
                )

            if spec.field_name in SCORED_LIST_FIELDS:
                bucket_values[spec.field_name], scored_items = annotate_scored_items(
                    raw_field_value, section_markdown, spec.field_name
                )
                bucket_metadata["scored_items"] = scored_items
            else:
                bucket_values[spec.field_name] = raw_field_value

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
        # The section title gets shown to the LLM as 'Section title: …'.
        # Falling back to a path-derived title would produce nonsense for
        # non-section files (e.g. 'compress_premortem_raw.json' becomes
        # 'Compress Premortem Raw Json'). If no title is supplied and the
        # stem is a recognised section, derive from the stem; otherwise
        # fall back to the section type name, which always at least
        # describes the intent of the call.
        if section_title is not None:
            inferred_title = section_title
        elif inferred_section_type != ReportSectionTypeEnum.UNKNOWN.value:
            inferred_title = inferred_section_type.replace("_", " ").title()
        else:
            inferred_title = "Compressed Section"
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

        sections: list[tuple[str, list[PublicScoredItem]]] = [
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
                rendered = format_scored_item_line(item).replace("\n", " ").strip()
                lines.append(f"- {rendered}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(
        "compress_report_section.py is a library module. To run the "
        "compression pipeline, use:\n\n"
        "    python -m worker_plan_internal.parameter_extraction.run_compress_full\n"
    )
