"""
Classify the project domain into a primary domain (and 0-3 secondary
domains) so downstream stages can apply domain-appropriate
expertise, risks, and templates.

Two LLM passes per classification:

  1. First pass — adaptive batch loop. The classifier is asked
     for 3 candidate expert disciplines per batch and the loop
     repeats until TARGET_CANDIDATES distinct candidates have
     been collected (or MAX_CALLS is reached, or batch 1 returns
     empty for a vague prompt). Subsequent batches inject the
     already-produced names and ask for 3 MORE that are
     different. Each candidate is scored on two 1-5 Likert
     scales: `importance` (how much this domain affects whether
     the project succeeds) and `specificity` (how directly this
     domain matches the actual project mechanism). The system
     prompt is purpose-routed — three guidance blocks (personal
     / business / other) are selected based on the upstream
     IdentifyPurpose pre-pass tag.

  2. Second pass — primary selection. The model sees the cleaned
     candidate list as an enumerated menu, picks one as the
     primary by `primary_index`, and emits a `rationale`.
     Tie-breakers: prefer `role="outcome"` first, then highest
     importance × specificity, then higher specificity (narrower
     match), then document order. The rationale text refers to
     candidates by domain name; the bracket index is an
     interface detail of the structured-output `primary_index`
     field and is not used in the human-readable rationale.

Result schema:
  - primary_domain (str): the chosen primary, or "Unclear" when
    no candidates were emitted (vague-prompt case).
  - secondary_domains (list[str]): up to 3 non-primary
    candidates in document order.
  - domain_fits (list[dict]): the cleaned fit list with
    importance / specificity / role / reason per candidate.
  - rationale (str): the second-pass LLM's justification (or a
    hardcoded fallback for the empty / fallback paths).
  - warnings (list[str]): records any code-side mutations
    (duplicate fits dropped, out-of-range Likert values clamped,
    purpose-tag candidates dropped, etc.).

Pipeline integration:
The Luigi wrapper feeds the first pass with a user message that
concatenates the raw plan prompt with the IdentifyPurpose
markdown ("## Plan purpose ...") and the ExtractConstraints
markdown ("## Extracted constraints ..."), and passes the
IdentifyPurpose tag as the `purpose` argument so the system-
prompt routing applies. derive_primary serves as a deterministic
fallback when the second-pass call fails.

PROMPT> python -m worker_plan_internal.assume.classify_domain
"""
import time
import logging
import json
import re
from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)


OPTIMIZE_INSTRUCTIONS = """\
Goal
----
Classify each plan prompt into a useful primary_domain (and 0-3
secondary_domains) so downstream stages can apply domain-
appropriate expertise, risks, and templates.

Pipeline context
----------------
Runs immediately after prompt parsing and the IdentifyPurpose +
ExtractConstraints pre-passes. Output feeds downstream stages
picking assumptions, expert lenses, regulators, and planning
templates.

The user message sent to the first-pass classifier concatenates
the raw plan prompt with the IdentifyPurpose markdown (under
"## Plan purpose ...") and the ExtractConstraints markdown
(under "## Extracted constraints ..."). The IdentifyPurpose tag
(personal / business / other) is passed separately and selects
which of three purpose-routed system prompts the first pass uses;
unknown / missing values fall back to the business prompt.

Architecture
------------
Two LLM passes per classification.

  1. First pass — adaptive batch loop. Each batch asks for
     BATCH_SIZE candidate disciplines; loop continues until
     TARGET_CANDIDATES distinct candidates are collected, or
     MAX_CALLS is reached, or batch 1 returns an empty fit list
     (vague-prompt path). Subsequent batches inject the names
     already produced and ask for "BATCH_SIZE MORE" candidates
     that are different. Pattern adapted from
     identify_potential_levers.py.

  2. Second pass — primary selection. Sees the cleaned candidate
     list as an enumerated menu and picks one by primary_index,
     with a rationale.

Each candidate is two-Likert scored:

  - importance (1-5): how much this domain affects whether the
    project succeeds. 1 = barely affects success; 5 = critical.
  - specificity (1-5): how directly this domain matches the
    actual project mechanism. 1 = very indirect / background
    context; 5 = direct match to the core mechanism.

Downstream stages can compute importance × specificity (1-25)
and threshold or weight by need.

Code-side derivation
--------------------
The second-pass LLM picks the primary normally. derive_primary
is a deterministic fallback when the second-pass call fails or
fits is empty:

  - If fits is empty: primary = "Unclear".
  - If any role="outcome" exists: prefer those, ranked by
    importance × specificity (descending), tie-broken by higher
    specificity, then higher importance, then document order.
  - Otherwise the same ranking among all fits.

Secondary domains are non-primary candidates in document order,
capped at 3.

Cleanup pipeline
----------------
Per-batch cleanup of emitted fits:

  - Drop entries with empty domain label.
  - Drop entries whose normalized domain matches a purpose-tag
    label ("Personal" / "Business" / "Other") — those are
    carried separately on the result and would duplicate the
    purpose tag.
  - Drop duplicate domains (case-insensitive label match).
  - Clamp out-of-range Likert values to [1, 5] with a warning.
  - Drop entries where importance == 1 AND specificity == 1
    (effectively unrelated; the analog of "low fit").
  - Truncate beyond TARGET_CANDIDATES with a warning.

All silent mutations are recorded in the result's `warnings`
list. Empty in the common case where the model emits clean
output.

Design philosophy
-----------------
The system prompts are principle-driven. They state the rules
("pick the narrowest expert discipline", "score importance and
specificity independently") and refrain from worked examples or
test-prompt paraphrases.

Reasoning:

  - Negative constraints ("do NOT pick X") get latched onto by
    LLMs and inverted. All constraints are positive ("use Y").
  - Worked examples that paraphrase test-set prompts make the
    classifier appear to improve on the test set without
    learning the underlying principle. Removing them forces
    the principle to carry the load.
  - Schema field descriptions are kept short and example-free
    for the same reasons.

Test prompts MUST NOT be referenced inside the system prompt
-------------------------------------------------------------
The system prompts MUST NOT contain any content that mirrors the
smoke harness's test prompts. Specifically:

  - No discipline names that are the expected primary or
    secondary for any test prompt.
  - No worked examples whose left-hand side paraphrases a test
    prompt.
  - No keywords or phrases lifted from any test prompt's text.
  - No deliverable-type or activity-type enumerations that map
    one-to-one onto specific test prompts.

Rationale: any test-prompt-mirroring content in the system
prompt is a form of training-on-the-test-set. The classifier
appears to improve on the smoke harness without learning the
underlying principle, the improvement is tautological.

Positive substitutes:

  - State the principle abstractly. "Use the field of practice,
    not the practitioner" is principle-shaped; listing
    "Engineering not Engineer, Architecture not Architect" is
    example-shaped and risks test-leak when those happen to be
    test answers.
  - When examples genuinely help comprehension, use
    morphological hints ("field nouns typically end in -y, -ics,
    -ing, -ure") rather than enumerated discipline names.
  - Use abstract category descriptions ("the broad umbrella
    categories that subsume many subfields under one banner")
    instead of enumerated lists of test-relevant labels.

Operational check before any commit that touches an LLM-facing
prompt: run a string search against the smoke harness's expected
discipline answers across the catalog sample. Any hit is a leak;
revise the prompt until the prompt is principle-only.

Evaluation discipline
---------------------
The smoke harness must be evaluated against a held-out test set
that the prompts have never been tuned against. Otherwise
apparent improvement is unmeasurable and the team risks the
overfit loop documented above.

Cost notes
----------
Per classification under typical conditions:

  - First pass: up to MAX_CALLS=3 batches.
  - Second pass: 1 LLM call when fits is non-empty (skipped on
    the empty-fits path).

Total: ~3 LLM calls for the classifier itself. The Luigi pipeline
also runs IdentifyPurpose and ExtractConstraints as pre-passes
(1 call each), but those outputs are reused by other downstream
tasks, so the marginal cost charged to classification is the
classifier's own ~3 calls.

Model fitness notes
-------------------
- Larger models (gpt-oss-safeguard-20b, gemini-2.0-flash) honour
  the principle-driven design reliably from the prompt alone.
- Smaller models (llama-3.1-8b-instruct) sometimes fail on
  imperative-as-instruction prompts (e.g. "Implement a Python
  script ...") by emitting code instead of JSON. The
  IdentifyPurpose markdown sometimes rescues this under
  augmentation, sometimes not. This is a small-model
  architectural limit, not a prompt issue.
- Same-model first-and-second-pass cannot catch its own
  confabulation on vague prompts. Use a sharper model for the
  second pass via the `primary_llm` parameter on
  ClassifyDomain.execute when the first pass is on a small
  model and you need the safety net.
"""


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """Strip leading/trailing whitespace and collapse internal whitespace runs."""
    return _WHITESPACE_RE.sub(" ", label).strip()


def label_key(label: str) -> str:
    """Case-insensitive comparison key for domain labels."""
    return normalize_label(label).casefold()


class DomainFit(BaseModel):
    domain: str = Field(
        description=(
            "A short Title Case noun phrase (1-3 words) naming an "
            "expert discipline as a FIELD of practice — the area of "
            "expertise itself, not the practitioner. Use the field-"
            "of-practice noun, not the noun for the person who "
            "practises it. Pick the narrowest field the prompt's "
            "signals support."
        )
    )
    # `importance` and `specificity` are 1-5 Likert scales. Stored as
    # plain ints rather than Field(ge=1, le=5, ...) so the structured-
    # output call survives a small model emitting an out-of-range value
    # (0, 6, or a string-coerced int); the cleanup pipeline clamps to
    # [1, 5] with a warning. Entries where both dimensions equal 1 are
    # dropped during cleanup as effectively unrelated.
    importance: int = Field(
        description=(
            "How much this domain affects whether the project "
            "succeeds, on a 1-5 Likert scale. 1 = barely affects "
            "success (peripheral concern). 2 = minor influence. "
            "3 = useful supporting influence. 4 = major influence "
            "(the project depends on getting this right). "
            "5 = critical to success (a blocking constraint or core "
            "capability the project cannot proceed without)."
        )
    )
    specificity: int = Field(
        description=(
            "How directly this domain matches the actual project "
            "mechanism, on a 1-5 Likert scale. 1 = very indirect or "
            "background context. 2 = somewhat related, but broad or "
            "peripheral. 3 = relevant but not central. 4 = strong "
            "match to a key part of the project. 5 = direct match to "
            "the core mechanism or specific technique the project "
            "uses (a specialist subfield, not its umbrella)."
        )
    )
    role: Literal[
        "outcome",
        "constraint",
        "market",
        "method",
        "stakeholder",
        "tool",
        "unclear",
    ] = Field(
        description=(
            "Why this domain shows up. "
            "'outcome' = this domain owns the project's main success "
            "criterion (any kind of success criterion, including "
            "intangible changes and ongoing operations, not only "
            "physical deliverables). "
            "'constraint' = this domain enforces regulatory, "
            "compliance, safety, or legal requirements that must be "
            "met. "
            "'market' = this domain's actors are the audience, buyer, "
            "or beneficiary. "
            "'method' = this domain's techniques are used as means to "
            "deliver the project. "
            "'stakeholder' = a key actor in the project comes from "
            "this domain. "
            "'tool' = this domain provides a generic instrument used "
            "in the project. "
            "'unclear' = this domain is present in the project but "
            "its functional role is genuinely ambiguous."
        )
    )
    reason: str = Field(
        description=(
            "One short sentence (≤15 words) explaining why this "
            "domain shows up and how it relates to the project."
        )
    )


class DomainFitAssessment(BaseModel):
    """A list of candidate domain fits for the project. The first-pass
    classifier emits only this field; the primary domain, secondary
    domains, and the human-readable rationale are all computed by
    the second-pass primary-selection LLM call (or by
    deterministic fallbacks when the second pass does not run).
    """
    # No max_length here on purpose — small models occasionally
    # over-emit and we'd rather truncate in code with a warning than
    # lose the entire response to a pydantic validation error.
    domain_fits: list[DomainFit] = Field(
        default_factory=list,
        description=(
            "Exactly 3 candidate domains for the current batch. The "
            "user message may instruct you that this is the first or a "
            "subsequent batch — in subsequent batches the candidates "
            "must be distinct from those already produced. For prompts "
            "that name no concrete project, emit an empty list "
            "regardless of the requested batch size."
        ),
    )


# --- Second-pass primary-selection schema -----------------------------

class PrimarySelection(BaseModel):
    """LLM-returned choice of primary domain from a candidate list."""
    primary_index: int = Field(
        description=(
            "Zero-based index into the candidate list. Pick exactly "
            "one candidate whose discipline owns the project's main "
            "success criterion. The index must be in the range "
            "[0, number_of_candidates - 1]."
        )
    )
    rationale: str = Field(
        description=(
            "One to two sentences (≤40 words) explaining why this "
            "candidate is the best primary fit for the project as a "
            "whole, including how it compares to the other candidates. "
            "Refer to candidates by their domain name only — never by "
            "their bracket index (`[0]`, `[1]`, ...) or by phrasings "
            "like 'index 0' or 'candidate 3'. The indices are an "
            "interface detail for the primary_index field and are not "
            "meaningful in the human-readable rationale text."
        )
    )


PRIMARY_SELECT_SYSTEM_PROMPT = """
You are selecting the primary domain for a project from a list of expert-discipline candidates that have already been judged relevant. Your task: pick the ONE candidate whose discipline owns the project's main success criterion — what a specialist who would lead the entire project as a whole calls themselves.

The user message contains the original project description, an optional `## Project purpose` section identifying the project as `personal`, `business`, or `other`, and the enumerated candidate list. Each candidate has an index, a domain, an `importance` score (1-5; how much this domain affects whether the project succeeds), a `specificity` score (1-5; how directly this domain matches the actual project mechanism), a role ("outcome" / "constraint" / "market" / "method" / "stakeholder" / "tool" / "unclear"), and a reason. The candidate list does not include the purpose category itself as a candidate — the purpose is carried separately so the candidate list always names actual expert disciplines.

# Output format

A single JSON object with two fields:

```json
{
  "primary_index": 0,
  "rationale": "..."
}
```

The first character of your response is `{`. The last character is `}`.

`primary_index` is the zero-based integer index of the candidate you select. It must be in the range [0, number_of_candidates - 1].

`rationale` is one or two sentences, ≤40 words, that explain why the chosen candidate is the project's primary discipline and (briefly) why each rejected candidate is not. In the rationale text, refer to candidates by their domain name (e.g., "Water Supply Engineering"), not by their bracket index (e.g., "[0]") or by phrasings like "index 0" or "candidate 3" — the bracket indices are an interface detail of the structured-output `primary_index` field and are stripped from the human-readable output downstream, so an index reference in the rationale becomes ungrounded.

# How to pick

Apply these preferences in order:

1. Prefer candidates with `role="outcome"` over other roles. The outcome owns the project's success criterion; methods, constraints, markets, stakeholders, and tools are subordinate.
2. Among role="outcome" candidates (or any single tier when no candidate has role="outcome"), prefer the candidate with the highest `importance × specificity` score. A high score means the domain both matters for project success and matches the actual project mechanism directly. Mentally compute the product (1-25) for each candidate and rank by it.
3. When `importance × specificity` is tied, prefer the candidate with higher `specificity` (the narrower, more specific match) over higher `importance` (which can be inflated by broad domains that affect many parts of the project).
4. When still tied, pick the candidate whose discipline best describes what the project is fundamentally about — what someone introducing the project to a stranger would call it.

The candidate list is fixed. Pick from it.

# Project purpose context

When a `## Project purpose` section is present, use it as additional context for the pick:

- **personal** — the project is a private life matter (an individual's task, hobby, vacation, household activity, or a family- or friend-scale event). Among the candidates, prefer the discipline that best names the activity itself, even when the discipline could be applied at a professional scale. Avoid promoting a candidate whose role makes it a generic instrument or supporting service rather than the activity itself.
- **business** — the project is commercial, professional, governmental, or large-scale societal. Apply the standard preferences: outcome over non-outcome, narrowest specialist over umbrella.
- **other** — the project is academic, hypothetical, non-profit / NGO / community-led, or could not be confidently placed in business or personal upstream. Among the candidates, prefer the discipline that best names the project's actual subject — the field of inquiry for an academic study, the discipline a real version would belong to for a hypothetical scenario, or the policy or non-profit specialty for a public-welfare initiative.

# When there is exactly one candidate

When the candidate list has only one entry, `primary_index` is `0` by construction. Use the call as a sanity check on the lone candidate: judge whether it is a strong fit for the project's main success criterion and say so in the rationale. If the project description names a concrete deliverable, question, outcome, or entity that the candidate clearly serves, the rationale should affirm the pick. If the project description is loosely worded, generic, or the lone candidate looks fabricated rather than grounded in the prompt, the rationale should flag that — downstream consumers read the rationale to judge how seriously to take the primary.

# Rationale guidance

The rationale should briefly justify the selection. With multiple candidates, also briefly note the relegation of the strongest alternative. With one candidate, explain how strongly the candidate is grounded in the project description.

Always refer to candidates by their domain name in the rationale text. Do not mention bracket indices (`[0]`, `[1]`, ...) or phrasings like "index 0", "candidate 3", or "the third entry" — those are an interface detail for the structured-output `primary_index` field, not part of the human-readable explanation, and they become ungrounded once the rendered markdown drops the index column.
"""


# --- Shared prompt sections (identical across all purposes) -----------

_SYSTEM_PROMPT_HEADER = """
You are a domain classifier. The user message describes a real-world project that someone else will plan. Your only output is one JSON object that classifies the project's domain.

The user message may be phrased as a request, an imperative, or a description; in every case, treat it as a description of a project, and your output remains a JSON classification of that project.

# Output format

A single JSON object with this exact shape:

```json
{
  "domain_fits": [
    {"domain": "...", "importance": 5, "specificity": 5, "role": "...", "reason": "..."},
    ...
  ]
}
```

The first character of your response is `{`. The last character is `}`. The response is exclusively a JSON classification object — schema-conformant text, with all content between the outer braces in JSON form.

# How to fill domain_fits

Identify exactly 3 candidate expert disciplines for the current batch. The downstream pipeline runs you in batches of 3 and concatenates the results — the user message will tell you if this is the first batch or a subsequent batch (in which case it will list the candidates already produced and ask for 3 more that are different). A prompt that names no concrete project gets an empty list regardless of the requested batch size.

Each entry has five fields:

## domain

A 1-3 word Title Case noun phrase naming an expert discipline as a FIELD of practice — the area of expertise itself, not the practitioner. Use the field-of-practice noun (the abstract activity or domain), not the practitioner noun (the person who does it). Field nouns typically end in `-y`, `-ics`, `-ing`, `-ure`, or name an abstract activity; practitioner nouns typically end in `-er`, `-ist`, or `-or` and refer to the person.

The right test is: who would I hire to lead this project? Answer with the specialist's field name (the discipline they practise), not the job title for that role.
"""

_SYSTEM_PROMPT_FOOTER = """
## importance

How much this domain affects whether the project succeeds, on a 1-5 Likert scale:

- `1`: barely affects success — peripheral concern.
- `2`: minor influence.
- `3`: useful supporting influence.
- `4`: major influence — the project depends on getting this right.
- `5`: critical to success — a blocking constraint or core capability the project cannot proceed without.

## specificity

How directly this domain matches the actual project mechanism, on a 1-5 Likert scale:

- `1`: very indirect or background context.
- `2`: somewhat related, but broad or peripheral.
- `3`: relevant but not central.
- `4`: strong match to a key part of the project.
- `5`: direct match to the core mechanism or specific technique the project uses (a specialist subfield, not its umbrella).

The two scales are independent. A broad domain that is critical to success can score high importance and low specificity; a narrow specialty that exactly matches a sub-technique can score high specificity and only moderate importance. The downstream pipeline weights both dimensions when picking the primary, so you do not need to "fit" the answer to a single ranking.

## role

- `"outcome"`: this domain owns the project's main success criterion. The success criterion may be a tangible artifact, an intangible change, an ongoing operation, a personal achievement, or anything else the project aims to bring about.
- `"constraint"`: this domain enforces regulatory, compliance, safety, or legal requirements that the project must meet.
- `"market"`: this domain's actors are the audience, buyer, or beneficiary.
- `"method"`: this domain's techniques are used as means to deliver the project.
- `"stakeholder"`: a key actor in the project comes from this domain.
- `"tool"`: this domain provides a generic instrument used in the project.
- `"unclear"`: this domain is present in the project but its functional role is genuinely ambiguous.

Use exactly one of these seven literals; pick the closest fit, or `"unclear"` when no role applies.

## reason

One sentence ≤15 words explaining why this discipline shows up.

# Empty-list case

When the prompt is too short or too generic to name a concrete project — when the prompt names no deliverable, no outcome, no audience, no operation, no substance, no medium — emit `domain_fits=[]`. The downstream pipeline supplies the human-readable explanation in that case; you do not need to.

# Pipeline reminder

The pipeline picks `primary_domain` from your `domain_fits` via a second LLM call, and derives `secondary_domains` and the human-readable rationale from there — you emit only the fit list. Focus on getting the fit list right.
"""

# --- Purpose-specific guidance blocks ---------------------------------

_BUSINESS_GUIDANCE = """
# Purpose-specific guidance: business projects

This project is commercial, professional, infrastructure, public-welfare, governmental, entrepreneurial, or large-scale societal.

Choose the narrowest discipline the prompt's signals support. Read the user message for named subfields, named techniques, named instruments, named substances, named media, named application areas, named regulators, named populations, named geographies. Each named thing pulls the answer toward a specific discipline; use the discipline name a practitioner of that thing would call themselves.

Broad umbrella labels — the catch-all categories that subsume many subfields under one banner — are appropriate only when the prompt produces no named subfield, technique, instrument, substance, or medium. When specific names are present, use the specialist discipline; the umbrella, if relevant at all, becomes a secondary entry rather than the primary.

When two specialist disciplines fit equally well, pick the one that owns the project's main success criterion as the primary outcome and put the others in method, constraint, market, stakeholder, or tool roles.
"""

_PERSONAL_GUIDANCE = """
# Purpose-specific guidance: personal projects

This project is a private life matter. The defining trait is that the project is private life rather than commercial, governmental, or organisational; participation by multiple people (a couple, a family, a household, a friend group) is fine and does not promote it to business. Personal therefore covers two shapes:

- one individual's own task, hobby, vacation, household activity, life decision, self-care, or self-improvement
- family- or friend-scale shared events and matters that are private rather than commercial

The participants act on their own behalf (or on behalf of their family, household, or friend group), not on behalf of an employer, a customer base, or a public or governmental remit.

The candidate disciplines for a personal project should describe the hobby, domestic technique, professional service, or specific activity central to the project. The label `"Personal"` is the project's purpose category, not an expert discipline — the purpose context is already carried separately, so the candidate list focuses on what the project actually involves.

Roles still distinguish the project's outcome from its means: assign `role="outcome"` to the discipline that names what the project is fundamentally about. Assign `role="method"` to disciplines that describe instruments or techniques applied within that outcome, `role="constraint"` to regulators governing the project, and `role="tool"` to off-the-shelf apps, websites, AI assistants, or consumer products used in the project — those never become the primary outcome.

For small-scale everyday activities, the discipline that best describes the activity is the right primary even when the activity is performed at hobby or routine scale.
"""

_OTHER_GUIDANCE = """
# Purpose-specific guidance: other projects

This project is in the "other" bucket — a catch-all that includes academic studies, hypothetical scenarios, technical inquiries, government and public-sector initiatives, non-profit organisations, NGOs, charities, foundations, community-led initiatives, AND projects that the upstream pre-pass could not confidently place in business or personal. The pre-pass picks "other" when in doubt, so the bucket sometimes contains projects that would naturally belong in business or personal but lacked clear identifying signals.

Money flow is not a purpose signal. Most projects involving multiple people or longer time spans involve real money — budgets, grants, donations, sponsorship, fundraising, volunteer-time-as-cost — regardless of which bucket they sit in. The notable exception is a small personal project (a lifestyle change, a hobby, a single-household task) which can be near-zero cost. The presence of money signals in the prompt does not by itself promote a project into the business bucket; what matters is whether the outcome is profit-seeking.

## Step 1 — the concreteness rule (always answer this first)

Before identifying any discipline, identify whether the prompt describes a concrete project. A concrete project names at least one of:

- a tangible or intangible deliverable (something the project will produce or hand off)
- a specific question to investigate (a hypothesis, a measurement, a comparison, a phenomenon, a relationship between variables)
- a measurable outcome the project aims to produce (a finding, a proof, an answer, an improvement in a named metric, an operational state to reach)
- a named entity to study or act on (a named species, place, population, substance, historical event, text, artifact, beneficiary group, or market segment)

If none of those is named in the prompt, the prompt has not yet described a project. The correct output is `domain_fits = []`. The downstream pipeline supplies the human-readable explanation in that case; you do not need to.

In that case, the empty-list answer is the final answer; step 2 only applies when step 1 yields a concrete project. A project description must name what is being delivered, investigated, produced, or studied or acted on. Prompts that pair generic imperative verbs with abstract or pronominal objects fall short of this requirement, and the right output is the empty-list answer.

## Step 2 — the discipline pick (only when step 1 yields a concrete project)

When step 1 yields a concrete project, pick the narrowest specialist expert discipline the prompt's signals support — what a specialist who would lead the project calls themselves. The same load-bearing principle as the business prompt applies here: a project that landed in "other" because of an upstream confidence call still gets classified by what it actually is, not by the bucket it arrived through.

For specific project shapes:

- **Academic study** → the field of inquiry whose journals would publish the resulting work. Use `"Research"` as fallback only when the study names no identifiable field.
- **Hypothetical scenario** → the discipline a real version would belong to.
- **Government, public-sector, NGO, charity, foundation, or community-led initiative** serving a population, community, or beneficiary group → the policy area or non-profit specialty whose practitioners would lead it; pick the narrowest that fits the prompt's signals.
- **Philosophical argument, ethical question, or conceptual framework** → the relevant philosophical sub-discipline. Apply this only when the prompt names a specific philosophical question, not as a default for unspecific prompts.
- **Other shapes** that landed in "other" because the upstream pre-pass was uncertain → the narrowest specialist discipline the prompt's signals support, just as the business prompt would. Broad umbrella labels (the catch-all categories that subsume many subfields under one banner) are reserved as fallback only when no specific subfield is named.

## Final check

Before emitting your JSON, re-read the prompt one more time and locate the specific named deliverable, question, outcome, or entity. When you can point to one, step 2 applies and you pick the discipline accordingly. When you cannot, the answer is `domain_fits = []`.
"""

# --- Per-purpose system prompt assembly + dispatch --------------------

_SYSTEM_PROMPTS: dict[str, str] = {
    "business": (_SYSTEM_PROMPT_HEADER + _BUSINESS_GUIDANCE + _SYSTEM_PROMPT_FOOTER),
    "personal": (_SYSTEM_PROMPT_HEADER + _PERSONAL_GUIDANCE + _SYSTEM_PROMPT_FOOTER),
    "other":    (_SYSTEM_PROMPT_HEADER + _OTHER_GUIDANCE    + _SYSTEM_PROMPT_FOOTER),
}

# Default prompt when no purpose tag is supplied. Business is the most
# general (covers commercial, governmental, public-welfare, infrastructure)
# and is the safest fallback.
_DEFAULT_PURPOSE = "business"

# Domain labels matching the purpose categories themselves are dropped
# from the candidate list at cleanup time: the purpose category is
# carried separately on the result, so a candidate domain of
# "Personal" / "Business" / "Other" would just duplicate the
# purpose tag without naming an actual expert discipline.
_PURPOSE_LABEL_KEYS: frozenset[str] = frozenset({
    "personal",
    "business",
    "other",
})


def system_prompt_for_purpose(purpose: str | None) -> str:
    """Return the assembled system prompt for the given purpose.

    Unknown / missing purpose values fall back to the default (business)
    rather than raising — that lets the classifier degrade gracefully if
    the IdentifyPurpose pre-pass fails or returns something unexpected.
    """
    key = (purpose or "").strip().lower()
    if key not in _SYSTEM_PROMPTS:
        key = _DEFAULT_PURPOSE
    return _SYSTEM_PROMPTS[key].strip()


def derive_primary(fits: list[DomainFit]) -> str:
    """Pick the primary_domain from a fit list.

    Priority:
      1. role='outcome' candidates first; among them, highest
         importance × specificity. Ties broken by higher specificity,
         then higher importance, then document order.
      2. If no role='outcome' candidate exists, the same
         importance × specificity ranking among remaining roles.
      3. 'Unclear' when fits is empty.
    """
    if not fits:
        return "Unclear"

    def _key(f: DomainFit) -> tuple[int, int, int]:
        # All keys are negated so Python's ascending sort puts the
        # strongest candidate first. Score = importance * specificity
        # (1-25). Higher specificity is the primary tie-breaker over
        # higher importance, since broad domains can score high on
        # importance without being a precise match.
        return (-(f.importance * f.specificity), -f.specificity, -f.importance)

    outcome_fits = [f for f in fits if f.role == "outcome"]
    candidate_pool = outcome_fits if outcome_fits else list(fits)
    candidate_pool_sorted = sorted(candidate_pool, key=_key)
    return normalize_label(candidate_pool_sorted[0].domain)


def _format_candidate_list(fits: list[DomainFit]) -> str:
    """Render the cleaned fit list as an enumerated candidate menu for
    the second-pass LLM. Returns a markdown-friendly block.
    """
    lines = [f"There are {len(fits)} candidate domains. Pick one."]
    lines.append("")
    for i, f in enumerate(fits):
        lines.append(
            f"- `[{i}]` domain={f.domain!r}, "
            f"importance={f.importance}, specificity={f.specificity}, "
            f"role={f.role!r}, reason={f.reason!r}"
        )
    return "\n".join(lines)


def select_primary_via_llm(
    llm,
    user_prompt: str,
    fits: list[DomainFit],
    purpose: str | None = None,
) -> tuple[int, str]:
    """Run the second-pass LLM call to pick the primary domain.

    Returns (primary_index, rationale). primary_index is a zero-based
    index into `fits`. Raises ValueError on empty `fits`, on an empty
    structured response, or on an out-of-range index.

    `purpose` (optional) is the project purpose category from the
    upstream IdentifyPurpose pre-pass — one of "personal" / "business"
    / "other". When supplied, it is included in the user message as
    a "## Project purpose" section so the second-pass selector can
    use the purpose context as a tie-breaker.
    """
    if not fits:
        raise ValueError("Cannot select primary from empty fit list.")
    if not hasattr(llm, "as_structured_llm"):
        raise ValueError("llm must provide as_structured_llm().")

    candidate_block = _format_candidate_list(fits)
    purpose_key = (purpose or "").strip().lower()
    if purpose_key in _PURPOSE_LABEL_KEYS:
        purpose_section = f"## Project purpose\n\n{purpose_key}\n\n---\n\n"
    else:
        purpose_section = ""
    user_msg = (
        f"{user_prompt}\n\n"
        f"---\n\n"
        f"{purpose_section}"
        f"## Candidate domains\n"
        f"{candidate_block}\n"
    )

    sllm = llm.as_structured_llm(PrimarySelection)
    chat_response = sllm.chat([
        ChatMessage(
            role=MessageRole.SYSTEM,
            content=PRIMARY_SELECT_SYSTEM_PROMPT.strip(),
        ),
        ChatMessage(role=MessageRole.USER, content=user_msg),
    ])

    selection: PrimarySelection = chat_response.raw
    if selection is None:
        raise ValueError(
            "Primary-selection LLM returned empty structured response."
        )
    idx = selection.primary_index
    if idx < 0 or idx >= len(fits):
        raise IndexError(
            f"Primary-selection index {idx} out of range [0, {len(fits)})."
        )
    return idx, normalize_label(selection.rationale)


def derive_secondaries(fits: list[DomainFit], primary: str, cap: int = 3) -> list[str]:
    """Pick up to `cap` secondary domains other than the primary,
    in document order. The cleanup pipeline already drops the
    importance=1 AND specificity=1 candidates, so any fit that
    reaches this function is at least minimally relevant.
    """
    primary_key = label_key(primary)
    seen = {primary_key}
    out: list[str] = []
    for f in fits:
        domain = normalize_label(f.domain)
        key = label_key(domain)
        if not domain or key in seen:
            continue
        seen.add(key)
        out.append(domain)
        if len(out) >= cap:
            break
    return out


@dataclass
class ClassifyDomain:
    """
    Classify a user prompt into a primary domain (with secondaries),
    derived in code from a fit-based assessment the LLM produces.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def execute(
        cls,
        llm,
        user_prompt: str,
        purpose: str | None = None,
        primary_llm=None,
    ) -> "ClassifyDomain":
        """Classify a project description against a purpose-specialised prompt.

        purpose: one of "personal" / "business" / "other" / None. Picks
        which of the three system prompts is sent. None or any unknown
        value falls back to the business prompt (the most general).

        primary_llm: optional separate LLM used for the second-pass
        primary-selection call. Defaults to `llm` when None — using the
        same model for both passes. The smoke harness can pass a more
        capable model here while keeping `llm` on the fast/small model
        for the first pass.
        """
        if not hasattr(llm, "as_structured_llm"):
            raise ValueError("llm must provide as_structured_llm().")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")
        if primary_llm is None:
            primary_llm = llm

        system_prompt = system_prompt_for_purpose(purpose)
        sllm = llm.as_structured_llm(DomainFitAssessment)

        # First pass: adaptive batch loop. Each batch asks for 3
        # candidate disciplines; the loop runs until we have
        # TARGET_CANDIDATES distinct candidates or hit MAX_CALLS.
        # Pattern adapted from identify_potential_levers.py.
        # Over-generation feeds the second-pass primary selector a
        # richer menu so it can re-rank with more options in front of
        # it. If batch 1 returns an empty list (the prompt is vague),
        # the loop exits early and the empty-fits path applies.
        TARGET_CANDIDATES = 9
        BATCH_SIZE = 3
        MAX_CALLS = 3

        cleaned_fits: list[DomainFit] = []
        seen_fits: set[str] = set()
        warnings: list[str] = []
        first_pass_total_seconds = 0.0
        last_response_byte_count = 0
        first_pass_call_count = 0

        for call_index in range(1, MAX_CALLS + 1):
            if call_index == 1:
                user_msg = user_prompt
            else:
                names_list = ", ".join(f'"{f.domain}"' for f in cleaned_fits)
                user_msg = (
                    f"You have already produced these candidate domains in earlier batches: [{names_list}].\n"
                    f"Produce {BATCH_SIZE} MORE candidate expert disciplines for the project below — distinct "
                    f"disciplines that are also relevant to this project but were not yet listed.\n\n"
                    f"{user_prompt}"
                )

            call_start = time.perf_counter()
            try:
                chat_response = sllm.chat([
                    ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                    ChatMessage(role=MessageRole.USER, content=user_msg),
                ])
            except Exception as e:
                llm_error = LLMChatError(cause=e)
                logger.debug(f"First-pass batch {call_index} failed [{llm_error.error_id}]: {e}")
                logger.error(f"First-pass batch {call_index} failed [{llm_error.error_id}]", exc_info=True)
                if call_index == 1 and not cleaned_fits:
                    raise llm_error from e
                warnings.append(
                    f"First-pass batch {call_index} failed "
                    f"({type(e).__name__}: {e}); continuing with "
                    f"{len(cleaned_fits)} candidate(s)."
                )
                continue
            first_pass_total_seconds += time.perf_counter() - call_start
            first_pass_call_count += 1
            last_response_byte_count = len((chat_response.message.content or "").encode("utf-8"))

            assessment: DomainFitAssessment = chat_response.raw
            if assessment is None:
                if call_index == 1 and not cleaned_fits:
                    raise ValueError(
                        "First-pass batch 1 returned empty structured response."
                    )
                warnings.append(
                    f"First-pass batch {call_index} returned empty; "
                    f"continuing with {len(cleaned_fits)} candidate(s)."
                )
                continue

            # If the first batch is empty, the prompt is vague. Stop the
            # loop and let the empty-fits path produce primary="Unclear".
            if call_index == 1 and not assessment.domain_fits:
                logger.info(
                    "First-pass batch 1 returned an empty fit list; "
                    "treating prompt as vague and skipping subsequent batches."
                )
                break

            pre_count = len(cleaned_fits)
            for f in assessment.domain_fits:
                domain = normalize_label(f.domain)
                if not domain:
                    warnings.append("Dropped fit with empty domain label.")
                    continue
                key = label_key(domain)
                if key in _PURPOSE_LABEL_KEYS:
                    # The purpose category (personal / business / other)
                    # is carried separately on the result; including it
                    # as a candidate domain would duplicate that signal.
                    warnings.append(
                        f"Dropped purpose-tag fit (purpose belongs in the "
                        f"purpose field, not the candidate list): {domain}"
                    )
                    continue
                if key in seen_fits:
                    warnings.append(f"Dropped duplicate fit domain: {domain}")
                    continue
                # Clamp out-of-range Likert values to [1, 5]. Small
                # models occasionally emit 0 or 6 or string-coerced
                # ints; we accept and normalize rather than reject the
                # whole structured response.
                importance = max(1, min(5, int(f.importance)))
                specificity = max(1, min(5, int(f.specificity)))
                if importance != f.importance or specificity != f.specificity:
                    warnings.append(
                        f"Clamped out-of-range Likert score for {domain}: "
                        f"importance {f.importance} -> {importance}, "
                        f"specificity {f.specificity} -> {specificity}."
                    )
                if importance == 1 and specificity == 1:
                    # A candidate that both barely affects success AND
                    # barely matches the project mechanism is
                    # effectively useless.
                    warnings.append(
                        f"Dropped 1×1 candidate (importance=1 and "
                        f"specificity=1, effectively unrelated): {domain}"
                    )
                    continue
                if len(cleaned_fits) >= TARGET_CANDIDATES:
                    warnings.append(
                        f"Truncated extra fit beyond cap of {TARGET_CANDIDATES}: {domain}"
                    )
                    continue
                seen_fits.add(key)
                cleaned_fits.append(
                    DomainFit(
                        domain=domain,
                        importance=importance,
                        specificity=specificity,
                        role=f.role,
                        reason=normalize_label(f.reason),
                    )
                )
            added = len(cleaned_fits) - pre_count
            logger.info(
                f"First-pass batch {call_index}: added {added} new "
                f"candidate(s); total {len(cleaned_fits)}/{TARGET_CANDIDATES}."
            )

            if len(cleaned_fits) >= TARGET_CANDIDATES:
                break

            # Stop if a follow-up batch added zero new candidates (all
            # duplicates or rejected) — additional calls would likely
            # repeat the same set.
            if added == 0 and call_index > 1:
                warnings.append(
                    f"First-pass batch {call_index} added 0 new candidates "
                    f"(all duplicates or rejected); stopping loop with "
                    f"{len(cleaned_fits)} candidate(s)."
                )
                break

        if cleaned_fits and len(cleaned_fits) < TARGET_CANDIDATES:
            warnings.append(
                f"First-pass produced {len(cleaned_fits)} candidate(s) "
                f"after {first_pass_call_count} batch call(s); target was "
                f"{TARGET_CANDIDATES}."
            )

        duration_seconds = round(first_pass_total_seconds, 3)
        response_byte_count = last_response_byte_count
        logger.info(
            f"First-pass total: {duration_seconds}s across "
            f"{first_pass_call_count} batch call(s); produced "
            f"{len(cleaned_fits)} candidate(s)."
        )

        # Pick the primary via a second LLM pass whenever there is at
        # least one candidate. Even on the 1-candidate case (where
        # the LLM picks index 0 by construction) the call is worth
        # the extra LLM round-trip: it gives the model a chance to
        # rate how well the lone candidate is grounded in the
        # project description, which can catch a small-model
        # hallucination that produced a single fabricated fit on a
        # vague prompt.
        #
        # With 0 candidates, primary is "Unclear" — no second pass.
        rationale = ""
        primary_select_duration = 0.0
        if not cleaned_fits:
            primary = "Unclear"
            rationale = (
                "No candidates emitted; the prompt is too vague to identify a project."
            )
        else:
            select_start = time.perf_counter()
            try:
                idx, sel_rationale = select_primary_via_llm(
                    primary_llm, user_prompt, cleaned_fits, purpose=purpose
                )
                primary = normalize_label(cleaned_fits[idx].domain)
                rationale = sel_rationale
            except Exception as exc:
                fallback_primary = derive_primary(cleaned_fits)
                warnings.append(
                    "Primary-selection LLM call failed "
                    f"({type(exc).__name__}: {exc}); falling back to "
                    f"derive_primary -> {fallback_primary!r}."
                )
                primary = fallback_primary
                rationale = (
                    "Second-pass selection failed; primary derived from the "
                    "priority-chain fallback (high+outcome > medium+outcome > "
                    "high any role > Unclear)."
                )
            primary_select_duration = round(
                time.perf_counter() - select_start, 3
            )

        secondaries = derive_secondaries(cleaned_fits, primary)

        json_response: dict = {
            "primary_domain": primary,
            "secondary_domains": secondaries,
            "domain_fits": [f.model_dump() for f in cleaned_fits],
            "rationale": rationale,
            "warnings": warnings,
        }

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration_seconds"] = duration_seconds
        metadata["response_byte_count"] = response_byte_count
        metadata["first_pass_call_count"] = first_pass_call_count
        metadata["first_pass_candidate_count"] = len(cleaned_fits)
        if primary_select_duration:
            metadata["primary_select_duration_seconds"] = primary_select_duration

        markdown = cls._convert_to_markdown(
            primary=primary,
            secondaries=secondaries,
            rationale=rationale,
            fits=cleaned_fits,
            warnings=warnings,
        )

        return cls(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
            markdown=markdown,
            warnings=warnings,
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
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str))

    @staticmethod
    def _convert_to_markdown(
        *,
        primary: str,
        secondaries: list[str],
        rationale: str,
        fits: list[DomainFit],
        warnings: list[str],
    ) -> str:
        secondary_display = ", ".join(secondaries) if secondaries else "_(none)_"
        lines = [
            f"**Primary domain:** {primary}",
            "",
            f"**Secondary domains:** {secondary_display}",
            "",
            f"**Rationale:** {rationale}",
        ]
        if fits:
            # Sort by importance × specificity (descending) so the
            # strongest combined-signal disciplines surface at the top.
            # Stable sort preserves document order within each tied
            # score band. The underlying `fits` list is not mutated —
            # only the rendering order changes.
            sorted_fits = sorted(
                fits,
                key=lambda f: -(f.importance * f.specificity),
            )
            lines.append("")
            lines.append("**Disciplines this project involves:**")
            lines.append("")
            lines.append("| Domain | Importance | Specificity | Role | Reason |")
            lines.append("|---|---|---|---|---|")
            for f in sorted_fits:
                reason = f.reason.replace("|", "\\|")
                lines.append(
                    f"| {f.domain} | {f.importance} | {f.specificity} | "
                    f"{f.role} | {reason} |"
                )
        if warnings:
            lines.append("")
            lines.append("**Warnings:**")
            for w in warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)

    def save_markdown(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.markdown)


if __name__ == "__main__":
    # Smoke runner notes:
    # - One LLM per worker thread (threading.local). llama_index LLM clients
    #   are not guaranteed thread-safe; sharing one across the
    #   ThreadPoolExecutor caused intermittent failures.
    # - max_workers is read from the model's luigi_workers config so the
    #   smoke harness mirrors pipeline parallelism.
    # - Always include a few synthetic vague prompts in the smoke set
    #   (e.g. "Help me make a plan for my project.") to verify the
    #   Unclear path end-to-end.
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_internal.utils.planexe_llmconfig import PlanExeLLMConfig
    from worker_plan_internal.assume.identify_purpose import IdentifyPurpose
    from worker_plan_internal.diagnostics.extract_constraints import ExtractConstraints
    from worker_plan_api.prompt_catalog import PromptCatalog
    from worker_plan_api.planexe_dotenv import PlanExeDotEnv

    PlanExeDotEnv.load().update_os_environ()

    # Two classify models tested side by side, each in two conditions:
    # baseline (raw prompt) and augmented (prompt + identified plan
    # purpose + extracted constraints). The purpose pre-pass tells the
    # classifier whether the project is personal, business, or other.
    # The constraint pre-pass surfaces explicit signals (named
    # substances, named regulators, named geographies). The classifier
    # uses both signals to inform role assignments and to favour narrow
    # specialist disciplines.
    LLM_NAMES = [
        "openrouter-llama-3.1-8b-instruct-nitro",
        "openrouter-gpt-oss-safeguard-20b-nitro",
    ]
    # Single model used for both pre-passes (purpose identification and
    # constraint extraction). Picked for speed + reliability on JSON
    # output. We run each pre-pass once per prompt and reuse the
    # result across both classify models.
    PURPOSE_LLM_NAME = "openrouter-gpt-oss-safeguard-20b-nitro"
    EXTRACT_LLM_NAME = "openrouter-gpt-oss-safeguard-20b-nitro"

    @dataclass
    class TestPrompt:
        id: str
        prompt: str

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    sorted_items = sorted(all_items, key=lambda x: x.id)

    # Pick a sample from the catalog. Bump SAMPLE_SEED for each
    # smoke run to get a different sample. The seed determines the
    # shuffle order over the full catalog; sample_size picks the top
    # N from the shuffled list. To do a held-out evaluation against
    # prompts the system prompts have not been shaped against,
    # exclude IDs from prior smoke runs before shuffling — see git
    # history for prior seed values used in evaluation.
    import random
    SAMPLE_SEED = 600
    sample_size = 10
    rng = random.Random(SAMPLE_SEED)
    shuffled = list(sorted_items)
    rng.shuffle(shuffled)
    catalog_sample = shuffled[:sample_size]

    sample_items = list(catalog_sample)

    def augment_with_context(
        prompt: str, purpose_md: str, constraints_md: str
    ) -> str:
        """Format the original prompt followed by purpose and constraint
        markdown sections.

        The classifier sees the original prompt, then (when available) a
        "Plan purpose" section with a personal/business/other tag, then
        (when available) an "Extracted constraints" section with named
        substances, regulators, geographies, etc. The classifier system
        prompt does not know about these sections; they are just extra
        signal embedded in the user message.

        Observed effects on the smoke harness (see OPTIMIZE_INSTRUCTIONS
        for the full notes): augmentation reliably fixes the small-model
        vague-prompt regression (llama no longer emits Software
        Engineering for "Improve things.") and partially nudges
        individual-household-task prompts toward home-flavoured labels.
        It does not promote Personal to primary on either model — that
        gap is in the system prompt's role definitions, not in the
        augmentation signal itself.
        """
        sections: list[str] = [prompt]
        if purpose_md.strip():
            sections.append(
                "## Plan purpose (auto-derived; for context only)\n"
                f"{purpose_md.strip()}"
            )
        if constraints_md.strip():
            sections.append(
                "## Extracted constraints (auto-derived; for context only)\n"
                f"{constraints_md.strip()}"
            )
        if len(sections) == 1:
            return prompt
        return "\n\n---\n\n".join(sections) + "\n"

    def run_purpose_phase() -> dict[int, tuple[str, str]]:
        """Run IdentifyPurpose once per prompt.

        Returns {idx: (purpose_value, purpose_md)} where purpose_value is
        one of "personal" / "business" / "other" / "" (empty on error).
        purpose_md is the IdentifyPurpose markdown summary.
        """
        try:
            cfg_dict = PlanExeLLMConfig.load().llm_config_dict.get(PURPOSE_LLM_NAME, {})
            max_workers = max(1, int(cfg_dict.get("luigi_workers", 1)))
        except Exception:
            max_workers = 1

        thread_local = threading.local()

        def get_thread_llm():
            llm = getattr(thread_local, "llm", None)
            if llm is None:
                llm = get_llm(PURPOSE_LLM_NAME)
                thread_local.llm = llm
            return llm

        def purpose_one(idx, item):
            try:
                result = IdentifyPurpose.execute(get_thread_llm(), item.prompt)
                purpose_value = str(result.response.get("purpose", "") or "").strip().lower()
                return idx, item.id, purpose_value, result.markdown, None
            except Exception as exc:
                return idx, item.id, "", "", exc

        print(
            f"\n========== PURPOSE phase ({PURPOSE_LLM_NAME}, "
            f"max_workers={max_workers}) =========="
        )
        out: dict[int, tuple[str, str]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(purpose_one, idx, item)
                for idx, item in enumerate(sample_items, start=1)
            ]
            for future in as_completed(futures):
                idx, prompt_id, purpose_value, md, exc = future.result()
                if exc is None:
                    out[idx] = (purpose_value, md)
                    label = purpose_value or "?"
                    print(
                        f"  ✓ [{idx}/{len(sample_items)}] {prompt_id} "
                        f"purpose={label} ({len(md)} chars)",
                        flush=True,
                    )
                else:
                    out[idx] = ("", "")
                    print(f"  ✗ [{idx}/{len(sample_items)}] {prompt_id}: {exc}", flush=True)
        return out

    def run_extract_phase() -> dict[int, str]:
        """Run ExtractConstraints once per prompt; return {idx: constraints_md}."""
        try:
            cfg_dict = PlanExeLLMConfig.load().llm_config_dict.get(EXTRACT_LLM_NAME, {})
            max_workers = max(1, int(cfg_dict.get("luigi_workers", 1)))
        except Exception:
            max_workers = 1

        thread_local = threading.local()

        def get_thread_llm():
            llm = getattr(thread_local, "llm", None)
            if llm is None:
                llm = get_llm(EXTRACT_LLM_NAME)
                thread_local.llm = llm
            return llm

        def extract_one(idx, item):
            try:
                result = ExtractConstraints.execute(get_thread_llm(), item.prompt)
                return idx, item.id, result.markdown, None
            except Exception as exc:
                return idx, item.id, "", exc

        print(
            f"\n========== EXTRACT phase ({EXTRACT_LLM_NAME}, "
            f"max_workers={max_workers}) =========="
        )
        out: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(extract_one, idx, item)
                for idx, item in enumerate(sample_items, start=1)
            ]
            for future in as_completed(futures):
                idx, prompt_id, md, exc = future.result()
                if exc is None:
                    out[idx] = md
                    print(f"  ✓ [{idx}/{len(sample_items)}] {prompt_id} ({len(md)} chars)", flush=True)
                else:
                    out[idx] = ""
                    print(f"  ✗ [{idx}/{len(sample_items)}] {prompt_id}: {exc}", flush=True)
        return out

    def run_model(
        llm_name: str,
        purpose_info_by_idx: dict[int, tuple[str, str]],
        constraints_by_idx: dict[int, str] | None,
    ) -> dict:
        """Run classify_domain on every sample item with purpose routing.

        purpose_info_by_idx is required — the classifier always routes
        the system prompt by purpose, so the purpose pre-pass is
        mandatory. Each entry is (purpose_value, purpose_md). When
        purpose_value is empty (pre-pass error or unknown value) the
        dispatch falls back to the business prompt.

        constraints_by_idx=None  -> baseline (raw prompt sent; only the
                                    purpose tag is consumed by routing).
        constraints_by_idx=dict  -> augmented (prompt + purpose markdown
                                    + constraints markdown sections).
        """
        try:
            cfg_dict = PlanExeLLMConfig.load().llm_config_dict.get(llm_name, {})
            max_workers = max(1, int(cfg_dict.get("luigi_workers", 1)))
        except Exception:
            max_workers = 1

        thread_local = threading.local()

        def get_thread_llm():
            llm = getattr(thread_local, "llm", None)
            if llm is None:
                llm = get_llm(llm_name)
                thread_local.llm = llm
            return llm

        is_augmented = constraints_by_idx is not None

        def classify_one(idx, item):
            try:
                purpose_value, purpose_md = purpose_info_by_idx.get(idx, ("", ""))
                if is_augmented:
                    constraints_md = (
                        constraints_by_idx.get(idx, "")
                        if constraints_by_idx is not None
                        else ""
                    )
                    classifier_input = augment_with_context(
                        item.prompt, purpose_md, constraints_md
                    )
                else:
                    classifier_input = item.prompt
                result = ClassifyDomain.execute(
                    get_thread_llm(), classifier_input, purpose=purpose_value
                )
                return idx, item.id, item.prompt, result.to_dict(
                    include_system_prompt=False,
                    include_user_prompt=False,
                    include_metadata=False,
                ), None
            except Exception as exc:
                return idx, item.id, item.prompt, None, exc

        condition = "augmented" if is_augmented else "baseline"
        print(
            f"\n========== {llm_name} [{condition}] "
            f"({len(sample_items)} prompts, max_workers={max_workers}) =========="
        )
        results: dict = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(classify_one, idx, item)
                for idx, item in enumerate(sample_items, start=1)
            ]
            for future in as_completed(futures):
                idx, prompt_id, prompt_text, json_response, exc = future.result()
                results[idx] = (prompt_id, prompt_text, json_response, exc)
                if exc is None:
                    print(f"  ✓ [{idx}/{len(sample_items)}] {prompt_id}", flush=True)
                else:
                    print(f"  ✗ [{idx}/{len(sample_items)}] {prompt_id}: {exc}", flush=True)
        return results

    print(
        f"=== Domain classification (importance × specificity) — sample of "
        f"{len(catalog_sample)} catalog prompts (SAMPLE_SEED={SAMPLE_SEED}, "
        f"picked from full catalog of {len(sorted_items)}) — "
        f"across {len(LLM_NAMES)} models × 2 conditions (baseline vs augmented) ==="
    )

    # Phase 1a: identify purpose once per prompt — drives prompt routing
    # AND (under the augmented condition) is included as user-message context.
    purpose_info_by_idx = run_purpose_phase()

    # Histogram of how many prompts the IdentifyPurpose pre-pass tagged
    # as personal / business / other. This is the trigger count the user
    # cares about: which custom prompt got selected, and how often.
    import collections
    purpose_counts: collections.Counter[str] = collections.Counter(
        (info[0] or "<empty>") for info in purpose_info_by_idx.values()
    )
    print()
    print("========== Purpose histogram ==========")
    print(f"  total prompts: {len(purpose_info_by_idx)}")
    bar_unit = "█"
    max_count = max(purpose_counts.values()) if purpose_counts else 1
    bucket_order = ["personal", "business", "other"]
    seen_buckets = set(purpose_counts)
    extras = sorted(seen_buckets - set(bucket_order))
    for bucket in bucket_order + extras:
        count = purpose_counts.get(bucket, 0)
        bar = bar_unit * int(round(20 * count / max_count)) if max_count else ""
        print(f"  {bucket:<10s} {count:3d}  {bar}")

    # Phase 1b: extract constraints once per prompt — reused for both classifiers.
    constraints_by_idx = run_extract_phase()

    # Phase 2: classify each prompt under both conditions for each model.
    # Both conditions use the purpose-routed system prompt; the difference
    # is whether the user message also gets the purpose + constraint
    # markdown sections appended.
    CONDITIONS = ("baseline", "augmented")
    all_results: dict[tuple[str, str], dict] = {}
    for llm_name in LLM_NAMES:
        all_results[(llm_name, "baseline")] = run_model(
            llm_name, purpose_info_by_idx, None
        )
        all_results[(llm_name, "augmented")] = run_model(
            llm_name, purpose_info_by_idx, constraints_by_idx
        )

    # Per-prompt side-by-side comparison.
    print()
    reference_key = (LLM_NAMES[0], "baseline")
    flip_counts: dict[str, int] = {llm: 0 for llm in LLM_NAMES}
    flips_by_model: dict[str, list[str]] = {llm: [] for llm in LLM_NAMES}
    for idx in sorted(all_results[reference_key]):
        prompt_id = all_results[reference_key][idx][0]
        prompt_text = all_results[reference_key][idx][1]
        print(f"\n[{idx}/{len(sample_items)}] Prompt ID: {prompt_id} (length: {len(prompt_text)} chars)")
        print(f"Preview: {prompt_text[:160].replace(chr(10), ' ')}...")
        for llm_name in LLM_NAMES:
            primaries: dict[str, str] = {}
            for condition in CONDITIONS:
                entry = all_results[(llm_name, condition)][idx]
                json_response = entry[2]
                exc = entry[3]
                short = llm_name.replace("openrouter-", "")
                tag = f"{short:<40s} | {condition:<9s}"
                if exc is not None:
                    print(f"  [{tag}] Error: {exc}")
                    primaries[condition] = f"<error: {exc}>"
                elif json_response is not None:
                    primary = json_response.get("primary_domain")
                    secondary = json_response.get("secondary_domains") or []
                    rat = json_response.get("rationale") or ""
                    primaries[condition] = primary or "<none>"
                    print(
                        f"  [{tag}] primary={primary}, "
                        f"secondary={secondary}"
                    )
                    if rat:
                        print(f"    rationale: {rat}")
            base = primaries.get("baseline")
            aug = primaries.get("augmented")
            if base is not None and aug is not None and base != aug:
                flip_counts[llm_name] += 1
                flips_by_model[llm_name].append(
                    f"  [{idx}] {prompt_id}: {base} -> {aug}"
                )

    # Aggregate summary: how many baseline/augmented disagreements per model.
    print("\n========== SUMMARY: baseline -> augmented primary flips ==========")
    total = len(sample_items)
    for llm_name in LLM_NAMES:
        short = llm_name.replace("openrouter-", "")
        n = flip_counts[llm_name]
        print(f"\n{short}: {n}/{total} prompts changed primary_domain")
        for line in flips_by_model[llm_name]:
            print(line)
