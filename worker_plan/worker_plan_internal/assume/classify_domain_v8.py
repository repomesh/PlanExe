"""
Classify the project domain into a primary domain (and 0-3 secondary
domains) so downstream stages can apply domain-appropriate expertise,
risks, and templates.

The LLM emits only a fit list (each entry: domain + role + reason +
fit level), plus an overall confidence and a short rationale. The
primary domain and secondaries are derived in code from the fits, so
the model cannot emit a primary that contradicts its own fit list.

v6: purpose-routed system prompts (carried over). The
IdentifyPurpose pre-pass classifies each prompt as personal /
business / other; the classifier then routes to one of three
purpose-specialised system prompts. v5's principle-only foundation
(narrowest expert discipline) is preserved.

v7 first-pass batching: the first pass runs as an adaptive loop
that asks the LLM for 3 candidate disciplines per batch and keeps
calling until 6 distinct candidates have been collected (or
MAX_CALLS=3 is reached). Pattern adapted from
identify_potential_levers.py. Subsequent batches inject the
already-produced candidate names into the user message and ask
for "3 MORE" that are different. Over-generation is intentional —
the second-pass primary selector benefits from a richer candidate
menu, and small models that would have produced 1-2 candidates in
a single call now produce a more diverse set across batches. If
batch 1 returns an empty fit list (the prompt is vague), the loop
exits early and the empty-fits path produces primary="Unclear".

v7 second pass: replace the deterministic priority-chain primary
picker (derive_primary: high+outcome > medium+outcome > high(any)
> Unclear) with a second LLM invocation that sees the cleaned fit
list as an enumerated candidate menu and picks one by index.
Rationale: derive_primary makes a fixed structural call (preferring
outcome over method, narrow over broad) but cannot weigh the
project's actual emphasis. Letting the model re-rank with the
fits and the prompt in front of it should produce better primaries
on multi-discipline prompts, particularly the multi-outcome
pattern observed in the v6 field probe (Solar Sunshade
emitting three role="outcome" entries). The primary-selection
call returns a primary_index and a rationale; both are surfaced
in the result. derive_primary is kept as a fallback when the
selection call fails or when there is only one candidate.

v7 moves the `rationale` field off DomainFitAssessment and onto
PrimarySelection. The first-pass classifier emits only the fit
list; the second-pass selector emits the chosen primary's index
and the human-readable rationale. For the 0-candidate (Unclear)
path where no second pass runs, the rationale is a hardcoded "no
candidates emitted" string. The 1-candidate case is routed
through the second pass (the LLM still picks index 0 by
construction, but its rationale catches small-model
hallucinations that produce a single fabricated fit on a vague
prompt).

The earlier v7 design also included a `confidence` field on
PrimarySelection. Smoke-run measurement showed it was binary in
practice (almost all "high" or "low", with "low" coming entirely
from the deterministic 0-candidate path), so it was removed —
the rationale carries the qualitative judgment, and downstream
consumers can compute "is this resolved?" from
`bool(domain_fits)`.

v8: replace the single ordinal `fit` field (low/medium/high) with
two independent 1-5 Likert scales, `importance` and `specificity`.
The High/Medium/Low scale was lossy for downstream lever
generation: several domains can all score "high" while playing
very different roles, and the scale couldn't distinguish a broad
domain that is critical for success from a narrow specialty that
exactly matches the project mechanism. The two-dimensional scale
separates "how much does this domain affect success?"
(importance) from "how directly does this domain match the
actual project mechanism?" (specificity), so downstream stages
can score each candidate as importance × specificity (1-25) and
threshold or weight by need.

  - importance (1-5): 1 = barely affects success; 5 = critical
    to success / blocking constraint or core capability.
  - specificity (1-5): 1 = very indirect or background context;
    5 = direct match to the core mechanism or the specific
    technique the project uses.

derive_primary's fallback path now picks the candidate with the
highest importance × specificity (ties broken by role="outcome",
then document order). The 1=1 case (importance=1 AND
specificity=1, the "completely useless" candidate) is dropped at
cleanup time, analogous to v7 dropping fit="low".

The schema design follows ChatGPT feedback to the user that
flagged High/Medium/Low as too lossy for lever generation. The
specific role-enum expansions ChatGPT also suggested
(core_outcome / core_method / engineering_constraint /
validation_method / regulatory_constraint / external_dependency
/ execution_support / stakeholder_context / market_context) are
deliberately not adopted in v8 — the role enum stays at v7's
seven literals to keep this change focused on the scoring
dimensions.

PROMPT> python -m worker_plan_internal.assume.classify_domain_v8
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
Primary domain is normally picked by the second-pass LLM (see
"second-pass primary selection" below). When the second-pass call
fails or fits is empty, derive_primary serves as a deterministic
fallback. Its ranking under v8:
  1. role="outcome" candidates first (over any other role).
  2. Within the chosen tier, highest importance × specificity wins
     (the 1-25 product of the two Likert scales).
  3. Ties broken by higher specificity (narrower match), then
     higher importance, then document order.
  4. "Unclear" when fits is empty.

Secondary domains are non-primary candidates in document order,
capped at 3. The cleanup pipeline already drops the
importance=1 AND specificity=1 candidates, so anything reaching
this stage is at least minimally relevant.

Confidence is taken from the LLM, but forced to "low" when the
derived primary is "Unclear". An empty / whitespace-only primary
also normalizes to "Unclear" with confidence="low".

Warnings
--------
The result carries a `warnings` list naming every silent mutation:
duplicate fits dropped, empty primary normalized, confidence
overridden, etc. Downstream consumers can use these to track
quality regressions without re-running the model.

v7 first-pass batching
----------------------
The first pass runs as an adaptive loop. Each LLM call asks for 3
candidate expert disciplines; the loop continues until 6 distinct
candidates are collected, MAX_CALLS=3 is reached, or a follow-up
batch adds zero new candidates (all duplicates / rejected). On
batch 2+, the user message is prefixed with the names already
produced and the instruction "Produce 3 MORE candidate expert
disciplines ... distinct disciplines that ... were not yet
listed." Batch 1 returning an empty fit list short-circuits the
loop (vague-prompt path).

Why over-generate? The second-pass primary selector picks from
the assembled candidate list, and a richer menu lets it re-rank
with more options. Small models that produce 1-2 reasonable fits
in a single call tend to produce a more diverse 4-6 across two
batches.

v7 second-pass primary selection
--------------------------------
v7 replaces the deterministic priority-chain primary picker with
a second LLM invocation that sees the cleaned fit list as an
enumerated candidate menu and returns:
  - primary_index — the index of the chosen candidate
  - rationale — one or two sentences justifying the pick

The `rationale` field has been moved off DomainFitAssessment (the
first-pass output) and onto PrimarySelection (the second-pass
output). The first-pass classifier now emits only the fit list —
`domain_fits` is its sole field. The second-pass selector is the
right place for the rationale because it has the candidate list
and the prompt in front of it and is making the actual primary
choice; explaining that choice in plain language is a task for
the same call.

An earlier v7 iteration also placed a `confidence` field on
PrimarySelection. Smoke-run measurement (10 cases × multiple
runs) showed it was binary in practice — almost all "high" or
"low" with no "medium" emissions even on close-call rationales,
and the "low" cases came entirely from the deterministic
0-candidate path (forced confidence="low" when fits is empty).
The field's signal was effectively `bool(domain_fits)`, so it was
removed. Downstream consumers compute "is this resolved?" from
the fit list directly and read the rationale for nuance.

The result's `rationale` is sourced as follows:
  - 0 candidates: hardcoded "no candidates emitted" string;
    primary_domain is "Unclear". No second pass runs.
  - 1+ candidates: the second-pass LLM emits the rationale.
    Routing the 1-candidate case through the LLM pays one extra
    call for a safety net — small models occasionally hallucinate
    a single fit on a vague prompt, and the second pass can flag
    weak grounding in its rationale instead of mechanically
    promoting it.
  - Fallback (LLM call fails): hardcoded fallback rationale
    describing the priority-chain fallback path. A warning
    records the failure.

derive_primary is kept as the deterministic fallback when the
second-pass call fails. Otherwise the second-pass LLM is the
authority over the primary domain, the confidence, and the
rationale.

v7 purpose-tag filter and purpose-aware second pass
---------------------------------------------------
Two coordinated changes that work together:

(1) Candidate domains whose normalized label matches the purpose
    category itself ("Personal" / "Business" / "Other") are
    filtered out at cleanup time and a warning is emitted. The
    purpose category is carried separately on the result, so
    including it as a candidate domain would duplicate that signal
    without naming an actual expert discipline.

(2) The second-pass primary-selection LLM receives the purpose tag
    in its user message under a "## Project purpose" heading, and
    PRIMARY_SELECT_SYSTEM_PROMPT has a "# Project purpose context"
    section with purpose-aware tie-breakers:
      - personal: prefer the discipline that names the activity
        itself (Horticulture for plant care, Cooking for meal
        prep, Travel Planning for vacation logistics).
      - business: standard outcome-over-non-outcome and
        narrowness-over-umbrella rules.
      - other: prefer the discipline that names the project's
        actual subject (academic field, real-version-of-
        hypothetical, policy / non-profit specialty).

The personal-purpose first-pass guidance was rewritten alongside
these changes to drop the "'Personal' is itself a valid expert
discipline" framing the cleanup filter would otherwise contradict.
The first-pass model is now told to emit specialist disciplines
(Horticulture, Cooking, Travel Planning, Healthcare, Construction,
Event Planning, Pet Care, Carpentry, Home Improvement) as
candidates for personal projects.

v7 smoke-run findings (2026-05-02)
----------------------------------
Houseplants [10] correctly handled across all four cells (both
models, both conditions): primary = Horticulture with Plant Care /
Indoor Gardening / Household Maintenance as secondaries. Combined
with `purpose: personal` on the result, downstream consumers see
"a personal Horticulture-flavored project." This is the design
intent landing — the purpose-tag filter removed the meta-label
that previously won by default, and the purpose-aware tie-breakers
told the second pass to prefer the activity discipline.

Solar Sunshade [4] (the multi-outcome motivating case): three of
four cells still pick a climate-or-deliverable-related primary
(Climate Engineering, Aerospace Engineering, International
Relations on the governance angle). One cell shifts to Aerospace
Engineering with the clean rationale "designing, building, and
launching the L1 sunshade is the core deliverable; Climate Science
is a broader outcome." Defensible reading; multi-outcome problem
still being addressed.

Vague-improve [23] llama still fails (Ecology baseline, Philosophy
augmented, both high-confidence). Same model running both first
and second pass cannot catch its own confabulation — the second-
pass selector receives a hallucinated candidate menu in pass 1 and
defends it in pass 2. The architectural fix remains: use a sharper
model for the second pass via the `primary_llm` parameter on
ClassifyDomain.execute (already wired). The smoke harness does
not currently exercise this — left for a future change.

Stability shifts: gpt-oss flips 12 -> 7 with the purpose-aware
tie-breakers (more stable). llama flips 8 -> 15 (more variable —
the longer second-pass prompt and richer candidate menu give the
small model more degrees of freedom). Confidence distribution
unchanged at 82 high / 10 low / 0 medium; models still don't use
medium even on close-call rationales.

v7 smoke-run findings: confidence-field removal (2026-05-02)
------------------------------------------------------------
Re-ran the smoke harness after dropping the confidence field
entirely from PrimarySelection and from the result schema. Output
schema is now: `primary_domain`, `secondary_domains`,
`domain_fits`, `rationale`, `warnings`. Verified zero `confidence`
or `conf=` references in the smoke log.

Behaviour with the removal:

  - Houseplants [10] stable on both models, both conditions:
    primary = Horticulture, secondaries = {Plant Care, Gardening,
    Household Maintenance, Time Management} variants. The
    purpose-aware second-pass design holds without the confidence
    field.
  - Solar Sunshade [4] improved: 4/4 cells pick a
    climate-or-deliverable-related primary this run (Environmental
    Engineering on llama baseline, Climate Engineering on the
    other three). The previous v7d run had Aerospace Engineering
    on gpt-oss augmented; this run gets Climate Engineering. The
    improvement is incidental LLM variance, but the multi-outcome
    case is still being handled correctly.
  - Vague-improve [23] llama still confabulates (Social Work this
    run; Ecology / Philosophy / Public Health / Plant Care across
    earlier runs). Different fabrication each run, same failure
    mode: same-model first-and-second-pass cannot catch its own
    hallucination. The rationale text now reveals the
    confabulation by claiming a focus that is not in the prompt
    ("a focus on improving unspecified aspects ... social welfare
    and community development") — useful signal for downstream
    consumers even without a confidence field. gpt-oss handles the
    case correctly via the empty-fits path.
  - Stability: llama flips 14/23, gpt-oss flips 9/23. Comparable
    to v7d. The confidence field had no measurable effect on the
    flip count.
  - Minor quality watch-out (not a regression): a couple of llama
    outputs use job titles instead of discipline names
    ("Environmental Engineer", "Escape Room Designer"). The
    existing first-pass guidance asks for "the discipline a
    specialist calls themselves" — small models occasionally
    drift to person-titles. Worth watching but not blocking.

Net: removing the confidence field is clean. The rationale now
carries the entire qualitative signal in the structured output;
on real prompts the rationales are coherent and prompt-grounded;
on confabulation cases the rationale itself reveals the made-up
content (the lack of grounding is visible in the language).
Downstream consumers compute "is this resolved?" from
`bool(domain_fits)` and read the rationale for nuance.

v7 smoke-run findings: test-leak scrub + llama-only run (2026-05-02)
-------------------------------------------------------------------
After scrubbing all test-relevant discipline names from the LLM-
facing prompts (see "Test prompts MUST NOT be referenced inside
the system prompt" above), re-ran the smoke harness with only
llama-3.1-8b enabled (gpt-oss disabled in LLM_NAMES; pre-pass
models still use gpt-oss for speed). The objective was to
re-measure llama's behaviour on cleanly principle-only prompts
and confirm the job-title-as-discipline drift observed in earlier
runs (e.g. "Environmental Engineer", "Escape Room Designer") was
addressed by the morphological field-vs-practitioner hints rather
than by named-discipline examples.

Findings:

- Job-title drift is GONE. Across all 23 prompts × 2 conditions
  (46 cells) on llama, no primary domain was emitted as a
  practitioner noun ending in -er / -ist / -or. The morphological
  hint in the schema description ("field nouns typically end in
  -y, -ics, -ing, -ure; practitioner nouns end in -er, -ist,
  -or") and the abstract "field of practice, not the
  practitioner" framing landed without needing example pairs.
- Solar Sunshade [4] still picks Climate Engineering on both
  conditions. The multi-outcome motivating case is still being
  handled correctly under the principle-only prompts.
- Houseplants [10] shifted: previously Horticulture (with the
  enumerated personal-purpose examples in the prompt); now
  Botany. Both are defensible answers; "Horticulture" was the
  applied-discipline framing and "Botany" is the academic-field
  framing. The shift is the expected side-effect of removing
  test-fit anchoring — the model now picks from its own
  knowledge rather than the prompt's examples. Combined with
  `purpose: personal` on the result, the output remains
  informative either way.
- Vague-improve [23] llama still confabulates (Urban Planning
  baseline with rationale "improve the city's infrastructure" —
  the prompt is 15 chars and says nothing about cities; Research
  augmented with rationale at least matching the prompt's actual
  word "improve"). Same architectural limit as prior runs:
  same-model first-and-second-pass cannot catch its own
  hallucination. Not a leakage-cleanup regression.
- Stability improved: llama flips dropped to 9/23 (was 14/23 in
  v7d and v7e). The cleaner prompts produced more stable
  baseline-vs-augmented answers.

Other notable shifts vs. prior runs (mostly defensible
alternatives, not regressions): [1] Squid Game Criminal Justice
-> Psychology, [9] Statue of Liberty Conservation Engineering ->
Civil Engineering, [11] Pasteurellosis Epidemiology ->
Veterinary Epidemiology, [15] Education-poverty Development
Economics -> Education Policy, [16] Reverse aging Gerontology ->
Regenerative Medicine. One sub-optimal pick: [17] Minecraft
escape room augmented picked Interior Design as primary with
Theme Park Design as secondary; either of those would be a
better primary, but neither is unreasonable.

Net: the leakage cleanup is a clear win. Job-title drift
disappeared without re-introducing test-mirror examples.
Stability improved on llama. The marquee multi-outcome win
(Solar Sunshade) holds. The remaining failure modes
(vague-improve confabulation, occasional sub-optimal narrow
picks) are model-quality issues, not prompt issues.

v7 smoke-run findings: held-out 10-prompt run (2026-05-02)
----------------------------------------------------------
First true validation of the v6/v7 prompts on prompts they have
never been tuned against. The smoke harness was switched to
SAMPLE_SEED=400, with seeds 7/8/100/300 added to the excluded-
IDs sequence so the new sample has zero overlap with anything
the prompts have been iteratively shaped against. Both llama and
gpt-oss were enabled. No vague prompts in this sample — the
goal was to evaluate prompts on unseen content, not to re-verify
the empty-fits path.

Held-out 10 catalog prompts:
  [1] covert intelligence operation
  [2] containerised dark-data ingestor fleet (long, ~11k chars)
  [3] neural-connectome research pilot
  [4] extreme-poverty sustainability solution
  [5] clean-water access strategy
  [6] police-robots deployment
  [7] small Python script (a bouncing-ball algorithm)
  [8] Pope-funeral planning
  [9] short metro-construction prompt (~70 chars)
  [10] reversible-suspended-metabolism research program (~7k chars)

Findings:

- Strong consistency on concrete prompts. 4 of 10 prompts had
  unanimous primary across all 4 cells (llama×{baseline,augmented}
  + gpt-oss×{baseline,augmented}): [2] Digital Preservation,
  [3] Neuroscience, [6] Robotics, [10] Cryobiology. These are
  textbook narrow-specialist picks, exactly what the principle-
  only design was supposed to produce.
- Reasonable variance on multi-discipline prompts. [1] Undercover
  / Clandestine / Intelligence Operations; [4] Humanitarian Aid /
  Development Economics / International Development; [5] Civil /
  Water Supply / Environmental Engineering; [8] Ceremonial
  Protocol / Funeral Planning / Event Management; [9] Urban
  Planning / Civil / Railway Engineering. All flips are between
  equally-narrow defensible alternatives — no umbrella drift, no
  job-title drift. Augmented condition often converges to the
  same answer across models.
- One real failure: [7] the Python bouncing-ball script. llama on
  baseline emitted Python code instead of JSON; the existing
  safeguard ("the user message describes a project; your output
  remains a JSON classification") was not enough for llama on a
  small-software-algorithm prompt. llama recovered under
  augmentation (purpose pre-pass markdown grounded it). gpt-oss
  handled both conditions correctly (Computer Graphics ->
  Animation). Same small-model imperative-as-instruction weakness
  observed in earlier runs; not introduced by the leakage
  cleanup.
- Stability: llama 5/10 flips on successful runs (6/10 counting
  [7]'s error->recovery); gpt-oss 4/10 flips. Slightly higher
  than in-sample (in-sample llama was 9/23 = 39% post-cleanup),
  but the absolute count is small and the flips are between
  equally-narrow alternatives.
- Rationales remain coherent and prompt-grounded. They quote
  prompt-specific details (e.g. "500 humanoid police robots",
  "vitrification protocols", "at-risk analog media") and
  explicitly demote the strongest alternatives.
- Confidence-removal verified: the result schema has no
  confidence field anywhere in this run; rationales carry the
  qualitative signal.
- Job-title drift: still gone. 0 cells across the 10 held-out
  prompts emitted a practitioner-noun primary.

Net: the principle-driven design generalizes to held-out prompts
without leaning on test-fit examples. The classifier produces
narrow-specialist labels with strong agreement on concrete
prompts and reasonable variance on multi-discipline prompts. The
remaining hard case (small-software-algorithm prompts on llama
baseline) is a known small-model limitation, not a v6/v7 design
issue. PlanExe's stated focus is real-world plans rather than
toy software algorithms, so the [7] failure mode is unlikely to
matter in production traffic.

v6 routing design (carried over)
--------------------------------
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

Test prompts MUST NOT be referenced inside the system prompt
-------------------------------------------------------------
The system prompts (the `_SYSTEM_PROMPT_HEADER`, the three
purpose-routed `_*_GUIDANCE` blocks, the `_SYSTEM_PROMPT_FOOTER`,
and the `PRIMARY_SELECT_SYSTEM_PROMPT`) MUST NOT contain any
content that mirrors the smoke harness's test prompts. Specifically:

- No discipline names that are the expected primary or secondary
  for any test prompt (e.g. naming "Horticulture", "Marine
  Biology", or "Game Design" as positive examples in the prompt
  invalidates the houseplants, GEOMAR, and Minecraft-escape-room
  test cases).
- No worked examples whose left-hand-side paraphrases a test
  prompt (e.g. "for a watering routine, Plant Care or
  Horticulture" mirrors the houseplants test prompt).
- No keywords or phrases lifted from any test prompt's text.
- No deliverable-type or activity-type enumerations that map
  one-to-one onto specific test prompts (e.g. listing
  "manufacturing project, software product, construction project"
  mirrors the paperclip factory, Reddit-for-AI, and Statue of
  Liberty test cases).

Why this rule is load-bearing: any test-prompt-mirroring content
in the system prompt is a form of training-on-the-test-set. The
classifier appears to improve on the smoke harness while not
learning the underlying principle. The improvement is a
tautology — the prompt now answers correctly on the test only
because it was told the answer. This pattern produced the
overfit cycle that motivated v5's principle-only rewrite.

Positive substitutes:

- State the principle abstractly. "Use the field of practice, not
  the practitioner" is principle-shaped; listing
  "Engineering not Engineer, Architecture not Architect" is
  example-shaped and risks test-leak when those happen to be
  test answers.
- When examples genuinely help comprehension, use morphological
  hints ("field nouns typically end in -y, -ics, -ing, -ure")
  rather than enumerated discipline names.
- Use abstract category descriptions ("the broad umbrella
  categories that subsume many subfields under one banner")
  instead of enumerated lists of test-relevant labels.

Operational check before any commit that touches an LLM-facing
prompt: run a string-search against the smoke harness's expected
discipline answers across the catalog sample. Any hit is a leak;
revise the prompt until the prompt is principle-only.

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
    # dropped during cleanup as the analog of v7's fit="low" drop.
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


# --- Second-pass primary-selection schema (v7) ------------------------

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
            "whole, including how it compares to the other candidates."
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

`rationale` is one or two sentences, ≤40 words, that explain why the chosen candidate is the project's primary discipline and (briefly) why each rejected candidate is not.

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

        logger.debug(f"User Prompt:\n{user_prompt}")

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
        TARGET_CANDIDATES = 6
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
                    # Analog of v7's fit="low" drop: a candidate that
                    # both barely affects success AND barely matches
                    # the project mechanism is effectively useless.
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

        # v7: pick primary via a second LLM pass whenever there is at
        # least one candidate. The 1-candidate case used to take a
        # fast-path that returned the sole candidate with confidence
        # derived from its `fit` level, but that path lost the
        # second-pass safety net: a small model that hallucinates a
        # single high-fit candidate on a vague prompt would receive
        # high confidence with no review. Routing 1-candidate through
        # the same second-pass LLM pays one extra call for the safety
        # net and lets the LLM judge whether the lone candidate is a
        # strong fit for the project's main success criterion.
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
    #   - seed 300 then shuffled (sorted_items minus 7/8/100's picks)
    #     and took 20 — these are the v6/v7 prompts the system prompts
    #     have been iteratively shaped against and must be held out
    #     of any new evaluation.
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
    pool_after_100 = [item for item in sorted_items if item.id not in used_ids]
    prior_shuffled = list(pool_after_100)
    random.Random(300).shuffle(prior_shuffled)
    for item in prior_shuffled[:20]:
        used_ids.add(item.id)
    fresh_pool = [item for item in sorted_items if item.id not in used_ids]

    # Held-out sample: 10 catalog prompts the v6/v7 system prompts have
    # never been measured against. No vague prompts in this sample —
    # the goal is to evaluate the prompts on prompts they have not
    # been shaped to handle, not to re-verify the empty-fits path.
    SAMPLE_SEED = 400
    sample_size = min(10, len(fresh_pool))
    rng = random.Random(SAMPLE_SEED)
    shuffled = list(fresh_pool)
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
        f"=== Domain classification (importance × specificity) — held-out sample of "
        f"{len(catalog_sample)} catalog prompts (SAMPLE_SEED={SAMPLE_SEED}, "
        f"excluded {len(used_ids)} prior IDs from seeds 7/8/100/300) — "
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
