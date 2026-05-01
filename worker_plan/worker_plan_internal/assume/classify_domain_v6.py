"""
Classify the project domain into a primary domain (and 0-3 secondary
domains) so downstream stages can apply domain-appropriate expertise,
risks, and templates.

The LLM emits only a fit list (each entry: domain + role + reason +
fit level), plus an overall confidence and a short rationale. The
primary domain and secondaries are derived in code from the fits, so
the model cannot emit a primary that contradicts its own fit list.

v6: purpose-routed system prompts. The IdentifyPurpose pre-pass
classifies each prompt as personal / business / other; v6 then
routes to one of three purpose-specialised system prompts so the
classifier sees guidance tailored to the kind of project it is
looking at. The shared base (output format, schema, fits, roles,
confidence, rationale, empty-list case) is identical across all
three; only the "Guidance for picking the primary discipline"
section differs. v5's principle-only foundation is preserved;
v6 adds purpose-aware role conventions (notably: Personal is a
valid primary discipline for individual household tasks under
the personal-purpose prompt). v3-v5 are kept on disk for diff
comparison.

PROMPT> python -m worker_plan_internal.assume.classify_domain_v6
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
Goal: classify each plan prompt into a useful primary_domain (and 0-3
secondary_domains) so downstream stages can apply domain-appropriate
expertise, risks, and templates.

The LLM emits only candidate fits (with role + reason); primary and
secondaries are derived deterministically in code. This makes it
structurally impossible for the model to return a primary that
contradicts its own fit list.

Pipeline context
----------------
Runs immediately after prompt parsing and before strategic-lever
identification. Output feeds downstream stages picking assumptions,
expert lenses, regulators, and planning templates.

Schema
------
The LLM emits 1-4 DomainFit entries (or 0 when the prompt names
no concrete project). Each entry has a domain (Title Case noun
phrase naming an expert discipline), a fit ("medium" or "high"),
a role (one of seven literals), and a reason (one short sentence).

Code-side derivation
--------------------
Primary domain is derived from the fits in this priority order:
  1. The first fit with fit="high" and role="outcome".
  2. The first fit with fit="medium" and role="outcome".
  3. The first fit with fit="high" (any role).
  4. "Unclear".

Secondary domains are medium/high-fit domains other than primary,
in original order, capped at 3.

Confidence is taken from the LLM, but forced to "low" when the
derived primary is "Unclear". An empty / whitespace-only primary
also normalizes to "Unclear" with confidence="low".

Warnings
--------
The result carries a `warnings` list naming every silent mutation:
duplicate fits dropped, empty primary normalized, confidence
overridden, etc. Downstream consumers can use these to track
quality regressions without re-running the model.

v6 routing design
-----------------
v6 keeps v5's principle-only base prompt and routes to one of
three guidance blocks based on the IdentifyPurpose pre-pass:
  - personal — Personal is a valid primary discipline; specialist
    disciplines (Horticulture, Cooking, Travel Planning) are
    method-role unless the individual is hiring a professional or
    interacting with a regulator.
  - business — pick the narrowest specialist expert discipline;
    umbrellas are fallback only. (This is the v5 default behavior.)
  - other — the right primary depends on what the prompt is
    actually about; for academic studies use the named field, for
    hypotheticals use the discipline a real version would belong
    to, for ambiguous prompts return Unclear with confidence=low.

Purpose routing makes IdentifyPurpose a load-bearing dependency.
If purpose information is unavailable, the dispatch falls back to
the business prompt (most general).

v5 design philosophy (still load-bearing under v6)
--------------------------------------------------
The system prompt is principle-driven and contains no worked
examples. The single load-bearing principle is: pick the narrowest
expert discipline that fits the prompt's signals — what a
specialist who would lead the project calls themselves. Umbrella
labels (Research, Engineering, Science, Technology, Business,
Industry, Energy, Environmental, Environmental Science, Healthcare)
are reserved for prompts that produce no specific subfield,
technique, instrument, substance, medium, or application area.

The reasoning behind this approach:
- Worked examples that paraphrase test-set prompts make the
  classifier appear to improve on the test set without learning
  the underlying principle. Removing them forces the principle
  to carry the load and exposes which models are too small for
  the task.
- LLMs latch onto negative constraints and produce exactly the
  thing they were told to avoid. v5 phrases everything as
  positive constraints (what to do, not what to avoid).
- Schema field descriptions (in DomainFit / DomainFitAssessment
  pydantic Fields) are kept short and example-free for the same
  reasons.

Architectural notes
-------------------
- The model cannot emit a primary that contradicts the fit list
  because it never emits a primary. The cost is that the role
  definition for "outcome" must be carefully written — if the
  model misuses outcome, the derived primary will be wrong even
  though the fit list looks reasonable.
- Dropping low-fit candidates from the schema reduces token spend.
- Cardinality 1-4 (instead of forced 3-4) lets simple
  single-discipline prompts return a single fit without
  fabricating filler.

Model fitness
-------------
- Larger models (gpt-oss-safeguard-20b, gemini-2.0-flash) honor
  the specificity principle reliably from the prompt alone.
- Smaller models (llama-3.1-8b-instruct) tend to drift toward
  umbrella labels even when the principle is stated clearly. v5
  tests how far the principle alone gets without test-fit
  hardcoding. If remaining drift matters, the next step is a
  code-side guardrail that demotes umbrellas when narrower fits
  exist in the same response — not more bullets in the prompt.

Evaluation discipline
---------------------
The smoke harness must be evaluated against a held-out test set
that the prompt has never been tuned against. Otherwise apparent
improvement is unmeasurable and the team risks the same overfit
loop that produced v2/v3/v4.

Augmentation pre-passes (purpose + constraints)
-----------------------------------------------
The smoke harness in this module runs two pre-passes per prompt
before classification:
  - IdentifyPurpose — emits a personal/business/other tag plus a
    one-line topic summary.
  - ExtractConstraints — surfaces named substances, named
    regulators, named geographies, etc.
Both markdown blocks are concatenated after the original prompt
under labelled headings (## Plan purpose / ## Extracted
constraints) and fed to the classifier as a single user message.

Observed effects on the small model (llama-3.1-8b-instruct):
  - Vague-prompt handling is decisively fixed under the augmented
    condition. Without augmentation, llama would happily emit
    Software Engineering / Environmental Science with high
    confidence on a prompt of "Improve things." Under augmentation
    it correctly emits Unclear with low confidence, matching the
    larger model.
  - "One individual's own household task" is partially helped: the
    "purpose: personal" signal nudges llama toward home-flavoured
    labels (Housekeeping, Domestic Maintenance) rather than
    specialist disciplines (Horticulture). Neither model promotes
    Personal to primary, however, because v5 dropped the worked
    example that named Personal as a valid discipline. Recovering
    that case fully would mean stating the principle "Personal is
    a valid primary discipline when the project is one
    individual's own task, hobby, or household activity" — that
    is a role definition, not test-fit content.
  - On already-narrow cases, augmentation occasionally introduces
    label noise: Machine Learning -> Data Science on an ML-paper
    distillation prompt, Regenerative Medicine -> Biomedical
    Engineering on an aging-research prompt. Both alternatives
    are still narrow; the choice between them shifts under
    augmentation but neither is wrong.

Observed effects on the larger model (gpt-oss-safeguard-20b):
  - Vague prompts are already handled correctly without
    augmentation; the pre-passes are not required.
  - The Horticulture-vs-Personal distinction for the houseplants
    case is unchanged by augmentation. The "purpose: personal"
    signal alone is not enough to override the model's instinct
    to find a specialist discipline; v5's prompt would need to
    define Personal as itself a valid discipline.
  - Other cases are stable across conditions, with the same
    narrow-label noise pattern as the small model.

Cost notes
----------
Adding both pre-passes ~doubles the LLM call count of the
augmented condition (one purpose call + one constraint call per
prompt, before the two classify calls per condition). On
production traffic this is meaningful — the pre-passes only earn
their cost on small models and on prompts where the role
distinction matters. Larger models that already honor the
specificity principle do not benefit and would be better served
by skipping augmentation.

v6 smoke-run observations (2026-05-01, SAMPLE_SEED=300, 23 prompts)
-------------------------------------------------------------------
Purpose histogram on the test set:
  personal:  1   ("water my houseplants")
  business: 17   (catalogue plans + the squid-game / educational
                  / EU inspection / Yellowstone / GEOMAR prompts)
  other:     5   (vague-help, vague-thing, vague-improve,
                  Statue of Liberty relocation, Arxiv ML
                  paper distillation)

Wins from purpose routing:
  - Houseplants is fully fixed on both models. Both llama and
    gpt-oss now emit primary="Personal" with Horticulture as
    role="method"/secondary, matching the intent of v5's
    deleted Personal worked example. The personal-purpose
    prompt's explicit "Personal is itself a valid expert
    discipline" line is what unblocks this; v5 with augmentation
    alone could not.
  - Most business prompts are unchanged from v5 (which is
    expected — the business-purpose prompt is essentially the
    v5 prompt). Narrow specialist labels continue to dominate
    on gpt-oss; llama still drifts to umbrellas on a couple of
    cases (water-treatment -> Environmental Engineering, marine
    pollution -> Environmental Science).

Regressions from purpose routing:
  - Vague prompts under the "other" bucket misclassify on
    llama. "Improve things." now produces Philosophy with
    confidence=medium under the augmented condition (was
    Software Engineering with high confidence in v5). gpt-oss
    correctly emits Unclear. The "other" prompt's mention of
    Philosophy as a valid discipline for philosophical inquiry
    is competing with its empty-list guidance, and the
    aggressive model picks Philosophy rather than admitting it
    cannot identify a project.
  - "Help me make a plan for my project." regressed on gpt-oss
    under augmented (Unclear -> Project Management). The
    "other" prompt is too permissive about emitting a
    narrow-discipline guess on prompts that should yield
    domain_fits=[].

Recommended next step:
  - Tighten the "other" prompt's empty-list case. Move the
    "no concrete project -> domain_fits=[]" guidance ahead of
    the Philosophy / hypothetical scenario examples, or make it
    a hard precondition on those examples ("If, AND ONLY IF, the
    prompt names a concrete philosophical question, use
    Philosophy; otherwise emit domain_fits=[]"). The gating must
    not turn into a negative constraint that the model latches
    onto and inverts.
  - Test set is purpose-skewed: only 1/23 personal prompts. To
    measure the personal-routed prompt under realistic load,
    seed the smoke harness with more individual-task prompts
    and re-run.

v6 "other"-prompt tightening — smoke-run delta (2026-05-01)
-----------------------------------------------------------
The "other" guidance was restructured into two ordered steps:
step 1 is a concreteness check that gates on a named deliverable,
question, outcome, or entity to study; step 2 is the discipline
pick that only applies when step 1 yields a concrete project.
Philosophy is now explicitly gated on "the prompt names a
specific philosophical argument, ethical question, or conceptual
framework" rather than offered as an open default.

Both prior "other"-bucket regressions are fixed:
  - "Improve things." on llama: was Software Engineering /
    Philosophy(conf=medium); now Software Engineering / Unclear
    under augmented. The augmented run correctly bottoms out at
    domain_fits=[]; the baseline still drifts because the model
    has no purpose context in the user message and reaches for
    a discipline anyway.
  - "Help me make a plan for my project." on gpt-oss: was
    Unclear / Project Management under augmented; now Unclear /
    Unclear on both conditions.

No regressions introduced:
  - Concrete "other"-bucket prompts (Statue of Liberty
    relocation, Arxiv ML paper distillation) still classify
    normally. The Statue of Liberty prompt routes to Civil /
    Structural Engineering on both models because it names a
    concrete deliverable (a relocated artifact). The Arxiv
    prompt is in the "other" bucket because IdentifyPurpose
    tagged it that way; gpt-oss emits Machine Learning Research,
    llama emits Research Methodology / Computer Science. Llama
    not picking Machine Learning here is a separate
    narrow-discipline-sensitivity issue, not an artifact of the
    tightening.
  - Houseplants stays Personal on both models, both conditions.
  - Personal and business buckets are unaffected (their guidance
    blocks are byte-identical to the prior v6).

Methodological observation: the fix is not a "do not emit
Philosophy" negative constraint but a positive precondition on
when discipline guidance applies at all. That preserves the
model's ability to use Philosophy when the prompt actually
warrants it (a named ethical question, a named conceptual
framework) while removing the bait for vague prompts.

Status against the original 10-issue review
-------------------------------------------
The original review (received before v4) listed 10 issues with
the v3 output and recommended two 80/20 fixes. Status of each
after the v4 -> v5 -> v6 progression:

(1) Primary domain too generic.
    PARTIALLY ADDRESSED. v5's "narrowest expert discipline"
    principle is load-bearing in v6. On the held-in synthetic
    test set, gpt-oss reliably picks narrow labels; llama is
    partial — drifts to umbrellas (Research, Environmental
    Science) on a minority of prompts. The original failing
    production case has not been re-run.

(2) Secondary domains wrong.
    PARTIALLY ADDRESSED, same caveat as (1). Same principle
    drives both primary and secondaries.

(3) Overly influenced by organization sector.
    NOT ADDRESSED. The system prompts do not explicitly tell
    the classifier to base the answer on the project's goal
    rather than the organization's self-description. Real gap.

(4) No project-level warnings produced.
    EXPLICITLY DEFERRED. The current `warnings` list is for
    code-side mutations (dropped duplicate fits, forced
    confidence override on Unclear, truncations) only. The
    review's project-level red flags
    (organization_project_domain_mismatch, radioactive_material_likely,
    budget_unknown, location_unknown, first_time_project_lead,
    specialized_facility_likely, high_complexity_project) belong
    to downstream stages (risk analysis, premortem, assumptions,
    RedlineGate), not the domain classifier. The classifier's
    scope is intentionally narrow.

(5) Ontology too broad.
    ADDRESSED. v5 introduced the specificity principle, v6
    preserves it. Smoke runs confirm narrow labels on the larger
    model; small-model drift is the residual.

(6) "Research" treated as a domain instead of a project type.
    NOT ADDRESSED. The schema still emits a single
    primary_domain plus a flat secondary_domains list. The
    review's suggested split (project_type="research_and_development"
    + primary_domain="Nuclear Physics") would require schema
    changes downstream consumers depend on.

(7) Lacks domain-specific signal extraction.
    ADDRESSED INDIRECTLY. The smoke harness now runs
    ExtractConstraints as a pre-pass that surfaces named
    substances, regulators, geographies, and beneficiary groups
    into the classifier's user message under the augmented
    condition. The actual production case has not been re-run
    to verify whether this fixes its specific failure.

(8) No outcome / method / constraint distinction in derived output.
    NOT ADDRESSED. Each fit carries a `role` field that the model
    populates, but `derive_primary` and `derive_secondaries`
    collapse the structure into a flat list. The review's
    suggested expansion (outcome_domain, method_domains,
    constraint_domains as separate output fields) was not done.

(9) Classifier too confident.
    NOT ADDRESSED. The `confidence` field is still high / medium
    / low, sourced from the model. The review suggested splitting
    "this is technical/scientific" confidence from "this exact
    domain label is right" confidence; not implemented.

(10) Wrapper too thin / no rule-based guardrail.
    EXPLICITLY DECLINED by the user. Code-side guardrails were
    rejected on two grounds: fragility, and PlanExe's
    multi-language usage (regex-style trigger lists do not
    generalise across languages). All fixes therefore live in
    the system prompt.

Original 80/20 fixes:
- Fix 1 (broad-label penalty + narrowest-discipline rule):
  ADDRESSED in v5/v6. The primary intended outcome of the v4 ->
  v5 -> v6 progression.
- Fix 2 (mandatory warning flags as required output):
  NOT ADDRESSED; out of scope per the deferral on issue (4).

Honest caveats:
- The original failing production case was never re-run against
  v6. Specific terms from that case were deliberately excluded
  from any shipped artifact, which means we have no direct
  measurement of whether v6 corrects that specific failure. The
  principle is in place; the specific verification is not.
- Issues (3), (6), (8), (9), and (4 / Fix 2) are real gaps. Of
  those, (4 / Fix 2) is likely the biggest impact on downstream
  planning quality if no other stage produces those project-level
  warnings.

Field-quality probe (gpt-oss-safeguard-20b, augmented condition,
10 prompts: 7 concrete + 3 vague)
---------------------------------------------------------------
Sampled the same SAMPLE_SEED=300 catalog as the smoke harness and
ran the full pipeline (IdentifyPurpose pre-pass + ExtractConstraints
pre-pass + ClassifyDomain on the augmented user message). The 10
prompts spanned all three purpose buckets and three concreteness
shapes (vague, single-discipline concrete, multi-discipline
concrete).

Per-field findings:

- domain (DomainFit): All 28 emitted values are real Title Case
  noun phrases naming actual expert disciplines. No empty strings,
  no fabricated labels. The narrowness principle is honored:
  Arachnology (not Entomology), Water Treatment Engineering (not
  Environmental), Industrial Automation (not Engineering),
  Climate Geoengineering (not Environmental Science).

- fit (DomainFit): All values are "high" or "medium" (no "low"
  leaks reaching the cleanup pipeline). High is reserved for
  disciplines whose specialists could plausibly own the plan;
  medium for materially-affecting but not-central disciplines.
  Software Engineering=high/method on the paperclip factory is a
  thoughtful call — software is critical to the automation but
  isn't the outcome.

- role (DomainFit): Roles observed across the sample: outcome,
  method, constraint. The other four literals (market,
  stakeholder, tool, unclear) were not triggered because none of
  the sampled prompts had a clear B2B-customer, named-actor, or
  generic-tool shape. ONE PRECISION CONCERN: on the most complex
  prompt in the sample, the model emitted three simultaneous
  role="outcome" entries (Aerospace Engineering + Climate
  Geoengineering + International Law). The role spec reads "this
  domain owns the project's main success criterion," which implies
  one outcome. The model is using "outcome" to mean "important
  deliverable," which is looser than the spec. derive_primary
  still produces a sensible primary (it picks the first
  high+outcome) but the role distinction is being weakened on
  multi-faceted prompts. Worth a future principle-clarification
  pass — "exactly one fit may carry role=outcome; equally
  load-bearing peers go to method, constraint, or stakeholder"
  — but this is not a regression and the pipeline absorbs it.

- reason (DomainFit): Every reason is within the ≤15-word
  constraint and factually grounded in the prompt or its extracted
  constraints. The model successfully synthesises across the
  augmented user message — for example, naming "Friday events with
  VIP ticket sales" on a public-events prompt where that detail
  came from the ExtractConstraints pre-pass, not the original
  prompt.

- domain_fits (DomainFitAssessment): Cardinality is correct (1-4
  for concrete prompts; 0 for vague). No duplicates. The 4-cap
  was reached on prompts that genuinely span four disciplines.

- confidence (DomainFitAssessment): Every concrete prompt got
  "high"; every vague prompt got "low". No false-confidence cases
  on the vague side; no underconfidence on the concrete side. For
  this sample the calibration is right.

- rationale (DomainFitAssessment): All within ≤40 words and all
  coherent. They reference the discipline picks and explain why
  each role applies, not just restate the prompt.

- warnings (code-side): Empty across all 10. The cleanup pipeline
  (drop low-fit, dedupe, force-confidence-on-Unclear, clear-fits-
  on-Unclear, truncate beyond cap) is dormant — the model is
  emitting schema-compliant output without needing post-process
  mutation. The empty-list rationale text on vague prompts comes
  from the LLM directly, not from a "forced primary to Unclear"
  mutation.

Net: across this 10-prompt sample, every required field is filled
with meaningful, prompt-grounded data; the only quality issue is
the multi-outcome role usage on complex prompts (noted above).
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
            "expert discipline — what a specialist who would lead "
            "this project calls themselves. Pick the narrowest "
            "discipline the prompt's signals support."
        )
    )
    # Accept "low" too — the system prompt asks for medium/high only,
    # but small models will sometimes ignore that and emit "low".
    # Rejecting at the pydantic boundary loses the entire response;
    # accepting and dropping in code with a warning is more robust.
    fit: Literal["low", "medium", "high"] = Field(
        description=(
            "How strongly the project belongs to this domain. "
            "high = central to the outcome, the project's success "
            "depends on this expertise; "
            "medium = materially affects planning (real tasks, risks, "
            "regulators, stakeholders) without being the project's "
            "central identity. "
            "low = incidental, weakly relevant; entries with fit='low' "
            "are dropped during cleanup and never appear in the final "
            "result."
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
        description="One short sentence (≤15 words) explaining the fit and role."
    )


class DomainFitAssessment(BaseModel):
    """A list of candidate domain fits for the project, plus an overall
    confidence and a short rationale. Emit only these three fields; the
    primary domain and secondary domains are computed downstream from
    the fit list and must not appear here.
    """
    # No max_length here on purpose — small models occasionally
    # over-emit and we'd rather truncate in code with a warning than
    # lose the entire response to a pydantic validation error.
    domain_fits: list[DomainFit] = Field(
        default_factory=list,
        description=(
            "1 to 4 substantive candidate domains for THIS project. "
            "Empty list when the prompt names no concrete project "
            "(use confidence='low' in that case). Single-domain "
            "projects can have just one entry. The pipeline truncates "
            "to the top 4 in document order if more are emitted."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "'high' when the project's expertise areas are clearly "
            "identifiable; "
            "'medium' when the fits are an interpretation of an "
            "ambiguous prompt, or the project genuinely spans many "
            "domains without a single lead; "
            "'low' when the prompt is too vague — pair with "
            "domain_fits=[]."
        )
    )
    rationale: str = Field(
        description=(
            "1-2 sentences explaining the fit choices, the role "
            "assignments, and (when applicable) what makes the prompt "
            "vague. ≤40 words."
        )
    )


# --- Shared prompt sections (identical across all purposes) -----------

_SYSTEM_PROMPT_HEADER = """
You are a domain classifier. The user message describes a real-world project that someone else will plan. Your only output is one JSON object that classifies the project's domain.

The user message may be phrased as a request, an imperative, or a description; in every case, treat it as a description of a project, and your output remains a JSON classification of that project.

# Output format

A single JSON object with this exact shape:

```json
{
  "domain_fits": [
    {"domain": "...", "fit": "...", "role": "...", "reason": "..."},
    ...
  ],
  "confidence": "low" | "medium" | "high",
  "rationale": "..."
}
```

The first character of your response is `{`. The last character is `}`. The response is exclusively a JSON classification object — schema-conformant text, with all content between the outer braces in JSON form.

# How to fill domain_fits

Identify 1 to 4 expert disciplines the project depends on. A single-discipline project gets one entry. A prompt that names no concrete project gets an empty list paired with `confidence="low"`.

Each entry has four fields:

## domain

A 1-3 word Title Case noun phrase naming an expert discipline. The right test is: who would I hire to lead this project? Answer with the specialist's discipline name — what that specialist calls themselves.
"""

_SYSTEM_PROMPT_FOOTER = """
## fit

- `"high"`: the project's success depends on this expertise. A specialist in this domain would naturally own the plan.
- `"medium"`: this expertise materially affects planning — real tasks, risks, regulators, stakeholders — without being the project's central identity.

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

# confidence

- `"high"`: the project's expert disciplines are clearly identifiable and their roles are unambiguous.
- `"medium"`: the fits are an interpretation of an ambiguous prompt, or the project genuinely spans many disciplines without a single lead.
- `"low"`: the prompt is too vague to identify a concrete project; pair with `domain_fits=[]`.

# rationale

One or two sentences ≤40 words explaining the discipline choices, the role assignments, and what makes the prompt vague when applicable.

# Empty-list case

When the prompt is too short or too generic to name a concrete project — when the prompt names no deliverable, no outcome, no audience, no operation, no substance, no medium — emit `domain_fits=[]`, `confidence="low"`, and a one-sentence rationale identifying what specific information is missing.

# Pipeline reminder

The pipeline derives `primary_domain` and `secondary_domains` from your `domain_fits` — you do not emit them. Focus on getting the fit list right.
"""

# --- Purpose-specific guidance blocks ---------------------------------

_BUSINESS_GUIDANCE = """
# Purpose-specific guidance: business projects

This project is commercial, professional, infrastructure, public-welfare, governmental, entrepreneurial, or large-scale societal.

Choose the narrowest discipline the prompt's signals support. Read the user message for named subfields, named techniques, named instruments, named substances, named media, named application areas, named regulators, named populations, named geographies. Each named thing pulls the answer toward a specific discipline; use the discipline name a practitioner of that thing would call themselves.

Umbrella labels — Research, Engineering, Science, Technology, Business, Industry, Energy, Environmental, Environmental Science, Healthcare — are appropriate when the prompt produces no named subfield, technique, instrument, substance, or medium. When specific names are present, use the specialist discipline; the umbrella, if relevant at all, becomes a secondary entry.

When two specialist disciplines fit equally well, pick the one that owns the project's main success criterion as the primary outcome and put the others in method, constraint, market, stakeholder, or tool roles.
"""

_PERSONAL_GUIDANCE = """
# Purpose-specific guidance: personal projects

This project is a private life matter. The defining trait is that the project is private life rather than commercial, governmental, or organisational; participation by multiple people (a couple, a family, a household, a friend group) is fine and does not promote it to business. Personal therefore covers two shapes:

- one individual's own task, hobby, vacation, household activity, life decision, self-care, or self-improvement
- family- or friend-scale shared events and matters such as a wedding, a funeral, a family reunion, a birthday, an anniversary, a parenting decision, an eldercare arrangement, or a household move

The participants act on their own behalf (or on behalf of their family, household, or friend group), not on behalf of an employer, a customer base, or a public or governmental remit.

For personal projects, `"Personal"` is itself a valid expert discipline name and is usually the right primary domain. Use `"Personal"` as the primary outcome whenever the project fits either of the two shapes above — regardless of which off-the-shelf tools, apps, hobby techniques, or consumer products are involved.

Use a more specific discipline as the primary outcome only when the prompt names a professional service the participants are hiring (Healthcare for a clinical procedure, Construction for a permitted build, Event Planning for a paid wedding planner running the event), a regulator the project must satisfy, or expertise that the participants cannot reasonably supply on their own.

Specialist disciplines that describe a hobby, domestic technique, or private-event organisation (Horticulture, Cooking, Gardening, Travel Planning, Event Planning, Carpentry, and similar) typically appear with `role="method"` while `"Personal"` carries `role="outcome"`. Off-the-shelf apps, websites, AI assistants, and consumer products used in the project carry `role="tool"` and never become the primary outcome.
"""

_OTHER_GUIDANCE = """
# Purpose-specific guidance: other projects

This project is in the "other" bucket — a catch-all that includes academic studies, hypothetical scenarios, technical inquiries, government and public-sector initiatives, non-profit organisations, NGOs, charities, foundations, community-led initiatives, AND projects that the upstream pre-pass could not confidently place in business or personal. The pre-pass picks "other" when in doubt, so the bucket sometimes contains projects that would naturally belong in business or personal but lacked clear identifying signals.

Money flow is not a purpose signal. Most projects involving multiple people or longer time spans involve real money — budgets, grants, donations, sponsorship, fundraising, volunteer-time-as-cost — regardless of which bucket they sit in. The notable exception is a small personal project (a lifestyle change, a hobby, a single-household task) which can be near-zero cost. The presence of money signals in the prompt does not by itself promote a project into the business bucket; what matters is whether the outcome is profit-seeking.

## Step 1 — the concreteness rule (always answer this first)

Before identifying any discipline, identify whether the prompt describes a concrete project. A concrete project names at least one of:

- a deliverable (a paper, a study, a system, a model, a corpus, a built artifact, a software product, a fundraising campaign, a regulation, a program)
- a question to investigate (a hypothesis, a measurement, a comparison, a phenomenon, a relationship between variables)
- an outcome the project aims to produce (a finding, a proof, a working prototype, an answer to a stated question, an improvement in a named metric, a sum of money raised for a named cause, a service running, a regulation enacted)
- an entity to study or act on (a named species, place, population, substance, historical event, text, artifact, beneficiary group, market segment)

If none of those is named in the prompt, the prompt has not yet described a project. The correct output is:

- `domain_fits = []`
- `confidence = "low"`
- `rationale =` a one-sentence statement naming which kind of concrete element is missing.

In that case, the empty-list answer is the final answer; step 2 only applies when step 1 yields a concrete project. A project description must name what is being delivered, investigated, produced, or studied or acted on. Prompts that pair generic imperative verbs with abstract or pronominal objects fall short of this requirement, and the right output is the empty-list answer.

## Step 2 — the discipline pick (only when step 1 yields a concrete project)

When step 1 yields a concrete project, pick the narrowest specialist expert discipline the prompt's signals support — what a specialist who would lead the project calls themselves. The same load-bearing principle as the business prompt applies here: a project that landed in "other" because of an upstream confidence call still gets classified by what it actually is, not by the bucket it arrived through.

For specific project shapes:

- **Academic study** → the named scientific field (Astrophysics, Linguistics, Genetics, Marine Biology, Volcanology, and similar). Use `"Research"` as fallback only when the study names no identifiable field.
- **Hypothetical scenario** → the discipline a real version would belong to (a hypothetical Mars colony is Aerospace; a thought experiment about quantum measurement is Physics).
- **Government, public-sector, NGO, charity, foundation, or community-led initiative** serving a population, community, or beneficiary group → the named policy area or non-profit specialty (Public Health, Public Policy, Education Policy, International Development, Humanitarian Aid, Nonprofit Management, and similar); pick the narrowest that fits.
- **Philosophical argument, ethical question, or conceptual framework** → Philosophy. Apply this only when the prompt names a specific philosophical question, not as a default for unspecific prompts.
- **Other shapes** (a manufacturing project, a software product, a construction project, a healthcare service, a transportation system, and so on) → the narrowest specialist discipline the prompt's signals support, just as the business prompt would. Umbrella labels (Research, Engineering, Science, Technology, Business, Industry, Energy, Environmental, Environmental Science, Healthcare) are reserved as fallback only when no specific subfield is named.

## Final check

Before emitting your JSON, re-read the prompt one more time and locate the specific named deliverable, question, outcome, or entity. When you can point to one, step 2 applies and you pick the discipline accordingly. When you cannot, the answer is `domain_fits = []` with `confidence = "low"`.
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
      1. fit='high' and role='outcome'
      2. fit='medium' and role='outcome'
      3. fit='high' (any role)
      4. 'Unclear'
    """
    for f in fits:
        if f.fit == "high" and f.role == "outcome":
            return normalize_label(f.domain)
    for f in fits:
        if f.fit == "medium" and f.role == "outcome":
            return normalize_label(f.domain)
    for f in fits:
        if f.fit == "high":
            return normalize_label(f.domain)
    return "Unclear"


def derive_secondaries(fits: list[DomainFit], primary: str, cap: int = 3) -> list[str]:
    """Pick up to `cap` secondary domains: medium/high-fit, not the primary."""
    primary_key = label_key(primary)
    seen = {primary_key}
    out: list[str] = []
    for f in fits:
        domain = normalize_label(f.domain)
        key = label_key(domain)
        if not domain or key in seen:
            continue
        if f.fit not in ("medium", "high"):
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
    ) -> "ClassifyDomain":
        """Classify a project description against a purpose-specialised prompt.

        purpose: one of "personal" / "business" / "other" / None. Picks
        which of the three system prompts is sent. None or any unknown
        value falls back to the business prompt (the most general).
        """
        if not hasattr(llm, "as_structured_llm"):
            raise ValueError("llm must provide as_structured_llm().")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")

        logger.debug(f"User Prompt:\n{user_prompt}")

        system_prompt = system_prompt_for_purpose(purpose)

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(DomainFitAssessment)
        start_time = time.perf_counter()
        try:
            chat_response = sllm.chat(chat_message_list)
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.debug(f"LLM chat interaction failed [{llm_error.error_id}]: {e}")
            logger.error(f"LLM chat interaction failed [{llm_error.error_id}]", exc_info=True)
            raise llm_error from e

        end_time = time.perf_counter()
        duration_seconds = round(end_time - start_time, 3)
        raw_content = chat_response.message.content or ""
        response_byte_count = len(raw_content.encode("utf-8"))
        logger.info(
            f"LLM chat interaction completed in {duration_seconds}s. "
            f"Response byte count: {response_byte_count}"
        )

        assessment: DomainFitAssessment = chat_response.raw
        if assessment is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")

        warnings: list[str] = []

        # Normalize, dedupe, drop low-fit entries, cap at 4.
        cleaned_fits: list[DomainFit] = []
        seen_fits: set[str] = set()
        for f in assessment.domain_fits:
            domain = normalize_label(f.domain)
            if not domain:
                warnings.append("Dropped fit with empty domain label.")
                continue
            key = label_key(domain)
            if key in seen_fits:
                warnings.append(f"Dropped duplicate fit domain: {domain}")
                continue
            if f.fit == "low":
                warnings.append(f"Dropped low-fit candidate: {domain}")
                continue
            if len(cleaned_fits) >= 4:
                warnings.append(f"Truncated extra fit beyond cap of 4: {domain}")
                continue
            seen_fits.add(key)
            cleaned_fits.append(
                DomainFit(
                    domain=domain,
                    fit=f.fit,
                    role=f.role,
                    reason=normalize_label(f.reason),
                )
            )

        # Derive primary and secondaries from the (cleaned) fit list.
        primary = derive_primary(cleaned_fits)
        secondaries = derive_secondaries(cleaned_fits, primary)

        # Confidence: keep model's value, except force "low" when primary is Unclear.
        confidence = assessment.confidence
        if primary == "Unclear":
            if confidence != "low":
                warnings.append(
                    f"Forced confidence='low' because derived primary is 'Unclear' "
                    f"(model emitted '{confidence}')."
                )
                confidence = "low"
            if cleaned_fits:
                warnings.append(
                    f"Cleared {len(cleaned_fits)} fits because derived primary is 'Unclear'."
                )
                cleaned_fits = []

        rationale = assessment.rationale.strip()

        json_response: dict = {
            "primary_domain": primary,
            "secondary_domains": secondaries,
            "confidence": confidence,
            "domain_fits": [f.model_dump() for f in cleaned_fits],
            "rationale": rationale,
            "warnings": warnings,
        }

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration_seconds"] = duration_seconds
        metadata["response_byte_count"] = response_byte_count

        markdown = cls._convert_to_markdown(
            primary=primary,
            secondaries=secondaries,
            confidence=confidence,
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
        confidence: str,
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
            f"**Confidence:** {confidence.title()}",
            "",
            f"**Rationale:** {rationale}",
        ]
        if fits:
            lines.append("")
            lines.append("**Domain fits:**")
            lines.append("")
            lines.append("| Domain | Fit | Role | Reason |")
            lines.append("|---|---|---|---|")
            for f in fits:
                reason = f.reason.replace("|", "\\|")
                lines.append(
                    f"| {f.domain} | {f.fit.title()} | {f.role} | {reason} |"
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
    # classifier whether the project is personal, business, or other —
    # which (per IdentifyPurpose's rubric) separates "water my
    # houseplants" (personal) from a commercial water-treatment program
    # (business). The constraint pre-pass surfaces explicit signals
    # (named substances, named regulators, named geographies). v5 trusts
    # both signals to push role assignments toward Personal where
    # appropriate and toward narrow specialist disciplines elsewhere.
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

    # Replay the prior sampling sequence faithfully so we exclude every
    # ID that has already been tested:
    #   - seeds 7 and 8 each shuffled full sorted_items and took 20.
    #   - seed 100 then shuffled (sorted_items minus 7's and 8's picks)
    #     and took 40.
    import random
    used_ids: set[str] = set()
    for prior_seed in (7, 8):  # each applied to full sorted_items
        prior_shuffled = list(sorted_items)
        random.Random(prior_seed).shuffle(prior_shuffled)
        for item in prior_shuffled[:20]:
            used_ids.add(item.id)
    pool_after_78 = [item for item in sorted_items if item.id not in used_ids]
    prior_shuffled = list(pool_after_78)
    random.Random(100).shuffle(prior_shuffled)
    for item in prior_shuffled[:40]:
        used_ids.add(item.id)
    fresh_pool = [item for item in sorted_items if item.id not in used_ids]

    SAMPLE_SEED = 300
    sample_size = min(20, len(fresh_pool))
    rng = random.Random(SAMPLE_SEED)
    shuffled = list(fresh_pool)
    rng.shuffle(shuffled)
    catalog_sample = shuffled[:sample_size]

    vague_prompts = [
        TestPrompt("vague-help", "Help me make a plan for my project."),
        TestPrompt("vague-thing", "I want to do a thing."),
        TestPrompt("vague-improve", "Improve things."),
    ]

    sample_items = list(catalog_sample) + vague_prompts

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
        """Run classify_domain on every sample item under v6 routing.

        purpose_info_by_idx is required — v6 always routes the system
        prompt by purpose, so the purpose pre-pass is mandatory. Each
        entry is (purpose_value, purpose_md). When purpose_value is
        empty (pre-pass error or unknown value) the dispatch falls back
        to the business prompt.

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
        f"=== Domain classification (fit-derivation) — fresh sample of "
        f"{len(catalog_sample)} catalog prompts (SAMPLE_SEED={SAMPLE_SEED}, "
        f"excluded {len(used_ids)} prior IDs) + {len(vague_prompts)} vague — "
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
                    conf = json_response.get("confidence")
                    primaries[condition] = primary or "<none>"
                    print(
                        f"  [{tag}] primary={primary}, "
                        f"secondary={secondary}, conf={conf}"
                    )
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
