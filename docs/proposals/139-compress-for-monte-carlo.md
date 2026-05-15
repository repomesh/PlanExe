# Compressing PlanExe sections for Monte Carlo parameter extraction

## Purpose

Builds on [proposal 137](137-section_filtering_for_parameter_extraction.md).
That proposal answered *which* PlanExe sections to feed a parameter-extraction
LLM. This proposal describes *how* to compress those sections so the
extractor receives a clean, source-faithful digest rather than raw
multi-tens-of-kilobytes prose.

The compressed digest is intended for downstream Monte Carlo / napkin-math
modelling.

## Problem

Feeding raw PlanExe section text to a parameter-extraction LLM has several
failure modes that contaminate the simulation:

- **Narrative dilution.** LLM-generated section bodies contain persuasive
  framing, role descriptions, and methodology prose. The extractor wastes
  attention on prose that has no numeric content.
- **Bare numbers.** Numeric values appear inline as narrative
  ("we plan to commit 15% of the budget…") rather than as labelled
  commitments. A bare percentage or currency amount is easy to misattribute
  during extraction.
- **Mixed-language fragments.** A plan written for a multi-language context
  (e.g. a Greenland project with Danish legal and financial terms mixed
  into English prose) produces hybrid sentences that neither the extractor
  nor a downstream model can use cleanly.
- **Stress magnitudes as plan facts.** Premortem-style downside numbers
  ("kiln breakdown loses 4–8 weeks of revenue") look like plan commitments
  to a literal extractor unless they are explicitly labelled as stress
  tests.
- **Rejected-alternative leakage.** A Strategic Decisions section
  enumerates every option the planner considered, including the ones the
  plan did not pick. A literal extractor turns rejected alternatives into
  model parameters and ends up modelling the wrong plan.

## Approach

Compress each relevant section into a structured digest *before* the
extractor sees it. The compressor is a six-call chained orchestration that
produces one `CompressedReportSection`:

1. `section_summary` — plain-English description of what the section
   contributes to modelling
2. `numeric_values` — labelled numbers with units and modelling roles
3. `load_bearing_assumptions` — foundational claims whose failure changes
   plan viability
4. `gates_and_thresholds` — pass/fail conditions in `If <X>, then <Y>` form
5. `risks_and_shocks` — downside triggers with operationally specific
   impact
6. `missing_data_to_estimate` — primitive inputs the source does not
   supply

Each call uses a single-field Pydantic schema. The chat history
accumulates so each later call sees the prior calls' output and can avoid
duplicating items across buckets.

## Sections compressed

| Compressed digest | Source content | Why this source |
|---|---|---|
| `compress_selected_scenario` | `SelectScenarioTask` inputs + `selected_scenario.json` | The chosen plan being modelled, not the menu of options |
| `compress_review_plan` | `ReviewPlanTask` inputs + `review_plan.md` | Validation gates, KPI thresholds, missing-evidence flags |
| `compress_premortem` | `PremortemTask` inputs + `premortem.md` | Failure paths, tripwires, downside shocks |
| `compress_expert_criticism` | `ExpertReviewTask` inputs + `expert_criticism.md` | Hidden assumptions and quantified expert estimates |

Each compress job ingests the same multi-file blob that the corresponding
Luigi task receives, plus that task's own output appended. This gives the
compressor the same surface the original LLM saw, so it can extract
parameters both from the inputs and from what the LLM said about them.
File-name headers (`File 'strategic_decisions.md':\n…`) match the format
the Luigi task itself uses when building its query.

### There is no `compress_strategic_decisions`

The full Strategic Decisions section enumerates every alternative
considered, including the ones the plan did not pick. Compressing it
standalone would risk turning rejected alternatives into model parameters.
The `selected_scenario` digest captures what the plan actually committed
to; the underlying `strategic_decisions.md` content still arrives via the
multi-file blobs feeding the other three digests, so its information is
not lost — only the standalone compression path is removed.

## The per-item schema

The LLM produces `ScoredItem` for each entry in each list bucket. The
pipeline then attaches a code-computed `quote_verified` flag and exposes
the result as `PublicScoredItem`. The public list buckets on
`CompressedReportSection` contain `PublicScoredItem` values.

| Field | Set by | Purpose |
|---|---|---|
| `line_english` | LLM | Clean English version of the content |
| `line_original` | LLM | Same content in the source's primary language (identical to `line_english` for English-only sources; preserves native technical and legal terminology for multilingual sources) |
| `modelling_relevance` | LLM | 1–5 Likert: how useful for Monte Carlo / napkin-math modelling |
| `source_evidence` | LLM | 1–5 Likert: how directly the source supports this exact line |
| `source_status` | LLM (with a code-side override on `missing_data_to_estimate`) | Epistemic tag — see taxonomy below |
| `source_quote` | LLM | ≤12-word fragment from the source backing the line |
| `quote_verified` | Code | `True` if `source_quote` appears in the section markdown after normalisation. Lives on `PublicScoredItem`, not on `ScoredItem` — the LLM never sees this field. |

### Source-status taxonomy

| Value | Meaning |
|---|---|
| `explicit` | A plan commitment the source states directly: a committed budget, an allocated reserve, a declared deadline, a contracted rate, a committed staff count. Reserved for items the plan is *binding itself to*. |
| `derived` | A value the plan implies but does not state directly, computable from one or more `explicit` values. |
| `inferred` | Covers two cases: (a) a plausible assumption the model added that the source does not state at all, and (b) an item the source *does* state but only as an assumption, aspiration, expected behaviour, or non-binding claim that the simulation should stress-test. "Local users will accept the high rental rate" is `inferred`, even when the source contains that exact sentence. |
| `stress_test` | A downside scenario magnitude (cost of failure, duration of disruption, lost revenue under a what-if). Never a plan fact. Premortem shock magnitudes default to this. |
| `missing` | A primitive input the plan needs but the source does not supply. Code-forced on every item in `missing_data_to_estimate`. |

The disambiguation order the LLM applies when picking a tag: stress_test
beats explicit when the item quantifies a failure outcome (even if the
source states the number); explicit requires that the plan is binding
itself, not merely mentioning the value; inferred covers both
model-added guesses and source-stated non-binding claims; missing is
forced on the missing-data bucket.

## Robustness mechanisms

### Code-side quote verification

The LLM rates `source_evidence` itself, which is gameable. The pipeline
independently substring-checks each item's `source_quote` against the
section markdown (case-insensitive, unicode-dash-tolerant, whitespace-
collapsed) and stores `quote_verified: bool` on the item. The downstream
consumer sees the model's self-rating *and* the code's verification side
by side and can weigh them differently.

### Over-produce, drop the weakest

Each list bucket asks the LLM to surface more candidates than the public
digest will keep. Python then sorts by
`modelling_relevance × source_evidence` (with a `+10` bonus for
`quote_verified`) and keeps the top six per bucket. The full set including
dropped candidates lives in the per-bucket metadata for inspection.

### Inline tags in the markdown render

Each list bullet carries an inline
`[status | e=N r=N | quote: verified|unverified]` tag so a downstream LLM
reading the markdown digest can weigh items by epistemic confidence
without parsing the JSON.

### Per-bucket retry

If a single bucket call fails (truncated JSON, missing required field,
schema echo), the pipeline retries that bucket up to three times with the
same chat history. Buckets that succeeded earlier in the chain are not
re-run.

### Forced status for the missing-data bucket

Items in `missing_data_to_estimate` are by definition about absent
values. The pipeline overwrites `source_status` to `missing` for every
item in that bucket, regardless of what the LLM emits — the bucket name
already determines the right status and an LLM that tags a missing-value
item as `explicit` (because the *need* was explicit in the source) would
mislead the extractor.

## Anti-creativity rules

The shared system preamble forbids the LLM from inventing values that are
not in the source. Specifically banned: benchmark percentages, generic
shock sizes, utilization thresholds, salary shares, equipment cost
guesses, growth rates, churn rates, cybersecurity/insurance/disaster
impact percentages, and other "typical business" filler. If a modelling
variable matters but the source is silent, the item belongs in
`missing_data_to_estimate`, not in `numeric_values`, `gates_and_thresholds`,
or `risks_and_shocks`.

The `selected_scenario` guidance carries an additional hard rule: only
items belonging to the selected baseline scenario are allowed. Rejected
alternatives may be named in `source_quote` for disambiguation only — they
may not appear as numeric_values, gates, risks, or assumptions, and gates
of the form `If the <rejected> scenario were chosen, then …` are
explicitly forbidden.

## Multilingual support

The `line_english` / `line_original` split solves the hybrid-sentence
problem (sentences mixing two languages mid-clause, which neither an
English-only nor a native-language reader can use). Markdown renders only
`line_english`; the JSON keeps both fields. Downstream English-only
consumers read the clean English version; consumers that need verbatim
source terminology read `line_original`.

For a fully-English source the two fields are identical at no real cost
(the LLM produces the same string twice). The discipline pays off for any
source that contains native legal, technical, or place-name terminology.

## Model selection

Compression currently runs on
`openrouter-gemini-2.5-flash-lite-preview-09-2025`. The largest Luigi
input blob (the 14-file `premortem` concatenation) is roughly 226 KB
≈ 57 K tokens, which exceeds the 16 K context window of smaller models
such as `openrouter-llama-3.1-8b-instruct-nitro`. The compressor
therefore needs a model with a large input window. The model is
configured via the `COMPRESS_FULL_LLM` environment variable; sample and
output directories use `COMPRESS_FULL_SAMPLE_DIR` and
`COMPRESS_FULL_OUTPUT_DIR`.

## Status

The current bundle (`selected_scenario` + `review_plan` + `premortem` +
`expert_criticism`) is graded usable for serious pipeline testing.
Recent external review (ChatGPT) put all four files at **B+** overall:

- Selected scenario: no rejected-alternative leakage; staffing-model
  description is unambiguous; missing-data items are primitive
  (electricity DKK/kWh, monthly shipping cost, FTE salary burden, etc.).
- Review plan: clean executable gates with deadlines and numeric
  thresholds; consistent `if/then` form; baseline anchors clearly
  separated from `stress_test` shocks.
- Premortem: stress magnitudes consistently tagged `stress_test`
  (reliably 6/6 on the risks bucket in repeated runs after the
  three-iteration robustness fix to the source_status definitions);
  baseline plan facts kept separate.
- Expert criticism: useful quantified estimates with the right epistemic
  tags; mixed-language fragments eliminated.

Per-section runtime is ~12–20 s for the six chained LLM calls. Each
`numeric_values` call typically produces 6–8 candidates, of which 5–8
pass substring verification; the top 6 reach the public list. Gates use
the `If <condition>, then <consequence>` form consistently. The
Danish/English hybrid sentences that earlier attempts produced are gone.

### Known remaining issues

- **`explicit` is still occasionally over-applied to load-bearing
  assumptions.** The `inferred` definition was broadened to cover
  source-stated non-binding claims (assumptions, aspirations, expected
  user behaviour), which reduced the over-spill substantially (total
  `inferred` count across the four files roughly 5× in side-by-side
  runs), but the LLM does not always catch every case. Items like
  "the chosen staffing model requires instructor absence not causing
  session cancellations" still sometimes land in `explicit` even
  though they are claims the simulation should stress-test. The
  external reviewer's suggested split — `explicit_numeric` vs
  `load_bearing_assumption` — would address this completely, at the
  cost of one more enum value.
- **Trade-off statements occasionally surface as gates.** A line like
  `"If Katuaq partnership is formalized, then administrative overhead
  increases"` reads as a trade-off, not an executable pass/fail gate.
  These belong in `missing_data_to_estimate` (the missing quantified
  overhead) rather than `gates_and_thresholds`.
- **Per-run quality variance.** Occasional unit-mismatch phrasings,
  one-off hallucinated artifacts (e.g. "material buffer lease
  agreement"), and non-sequitur gate consequences appear sporadically.
  These are per-LLM-run noise rather than systemic prompt failures.
  Quote-substring verification catches a fraction of them via the
  `quote: unverified` tag, but a strict downstream consumer should
  always weight unverified items lower regardless of the LLM's
  self-rated `source_evidence`.
- **Missing-data items occasionally drift into derived quantities.**
  An item like "Required percentage of operating contingency that must
  be consumed by labor reclassification" is a derived ratio, not a
  primitive. The prompt asks for primitives but the model still
  occasionally emits derived ones.
- **Currency-unit consistency.** "Dollar amount" phrasing still
  occasionally slips into a DKK plan.

### Future work, ordered by probable value

- Split `explicit` into `explicit_numeric` (binding numeric commitments)
  and `load_bearing_assumption` (source-stated non-binding claims to
  stress-test). This is the cleanest fix for the residual
  over-confident-explicit pattern; the cost is one more value for the
  LLM to disambiguate across.
- Sharpen the `gates_and_thresholds` prompt to reject lines that read as
  qualitative trade-offs without a pass/fail edge, and route the missing
  threshold into `missing_data_to_estimate`.
- Add a currency-consistency rule keyed off the source's dominant
  currency to catch the "dollar amount in a DKK plan" pattern.
- Extend the scoring/tagging pattern to additional Luigi outputs
  (`data_collection`, `consolidate_assumptions`) if downstream extraction
  needs them as inputs.
- Consider a dedup / merge step for risks and assumptions when a section
  paraphrases the same shock multiple times.
- Optionally: a separate `expert_estimate` source_status for
  critic-proposed quantified impacts, distinguishing them from
  premortem-style `stress_test` numbers.

## Insights from iterating with reviewer feedback

The current design landed after many rounds of reviewer feedback driving
prompt and architecture changes. A few themes recurred. Recording them so
the next iteration does not re-discover them.

### Compress the inputs, not the outputs

The initial instinct was to compress each section's *output* (e.g. take
`premortem.md` and reduce it). That produced thin digests because most of
what is interesting about a section is what was *fed into the LLM that
wrote it*, not the prose the LLM produced. Switching to compressing the
same multi-file blob that the corresponding Luigi task receives (plus
that task's own output appended) was the single biggest quality jump in
the whole iteration. The compressor now sees the same surface the
original LLM saw and can extract parameters that were available to the
original call but did not survive into the prose.

### Compress the *selected* scenario, not Strategic Decisions

The Strategic Decisions section enumerates every alternative the planner
considered. Compressing it naively turns rejected alternatives into model
parameters — the extractor ends up modelling a plan the planner did not
pick. Switching to the selected-scenario blob, with an explicit
scenario-boundary rule in the prompt, was the second big architectural
correction. Rejected-alternative content still arrives through
`strategic_decisions.md` inside the other three Luigi blobs, but the
selected scenario keeps it out of `numeric_values`, `gates`, and `risks`.

### Tag, don't drop

An earlier design dropped items whose `source_evidence` was below a
threshold. The reviewer's complaint was always the opposite of what the
filter assumed: dropping a low-confidence item lost real information,
while keeping a high-confidence-self-rated-but-fabricated item poisoned
the model. The current design keeps everything the LLM produced and
relies on inline tags so the downstream consumer can de-weight items it
does not trust. Redundancy beats conciseness when the downstream consumer
is itself an LLM that can filter.

### Self-reported confidence is gameable; verify with code

The LLM rates its own `source_evidence`. Given the chance it will rate
everything 5/5. The cheapest counter is code-side substring verification:
the LLM also produces a `source_quote`, and the pipeline checks whether
that quote is present in the section markdown after light normalisation.
The `quote_verified: bool` flag is computed truth, not opinion. The
downstream consumer sees both the model's self-rating *and* the code's
verification and can weight them differently.

### Multi-call is more reliable than mega-prompt

An early attempt asked one LLM call to return all six fields of the
digest at once. Small models choked on the nested schema (truncation,
field-order confusion, schema echoing). Splitting into six chained calls
— one per field — made each response small enough to fit reliably and let
each call have its own focused prompt. Per-call retry can recover from
transient failures without losing the buckets that already succeeded.

### Chat-history threading prevents bucket bleed

When the six calls were independent, `risks_and_shocks` frequently
restated `gates_and_thresholds` verbatim because each call started with a
blank context. Accumulating prior assistant turns into the chat history
(the pattern used in `diagnostics/premortem.py`) lets each later call see
what has already been produced and avoid duplicating it.

### Stress magnitudes are not plan facts

Premortem shock numbers — "kiln breakdown loses 4–8 weeks", "labour
reclassification consumes 60–90% of contingency" — *are* useful to the
simulation, but as scenario stress tests, not as plan commitments. Until
the `stress_test` source_status was added, the reviewer kept flagging
that these magnitudes looked indistinguishable from `2M DKK Year 1
budget` to a literal extractor. The taxonomy split lets the extractor
treat them differently without losing the information.

### Two language fields, not English-only enforcement

An obvious response to mixed-language fragments is to demand
English-only output. That works until the source contains untranslatable
legal or place-name terminology — at which point the LLM produces hybrid
sentences ("in højsæsonen (peak season) could result in 4-6 ugers total
driftsstop") that are worse than either pure-English or pure-native. The
fix is asking for *both* versions cleanly: `line_english` for the
English-only consumer, `line_original` for the consumer that needs
verbatim source terminology. For a fully-English source both fields are
identical at no real cost.

### Negative imperatives backfire

Rules of the form "X must NEVER appear" often have the opposite effect
on a small LLM: the prohibited construction shows up *more* often,
probably because the prompt has now mentioned it. Positive imperatives
("always write gates as `If <condition>, then <consequence>`") work
better. Most of the prompt is now phrased positively even when the
underlying intent is to forbid something.

### Concrete examples get parroted; use placeholder templates

When the prompt showed concrete example values (`50,000 EUR`,
`2027-03-01`), small models lifted them verbatim into outputs for plans
that were in DKK and dated 2026. Switching to placeholder-shaped
templates (`<amount> <currency-from-source>`, `<date-from-source>`)
eliminated the parroting. Templates also generalise: the prompt no
longer carries currency or locale bias.

### Force semantics in code when the bucket already determines them

The `[explicit]` tag means "literally in the source" — except in the
`missing_data_to_estimate` bucket where the *content* is by definition
absent. Asking the LLM to honour this nuance was unreliable. Forcing
`source_status="missing"` in code for every item in that bucket — and
saying so in the prompt — closed the semantic clash without depending on
the model to remember it.

### Per-run LLM variance is a fundamental limit

After a certain quality level, prompt tweaks stop yielding clear
improvements. Per-LLM-run noise dominates: an oddly worded gate, an
invented "lease agreement", a unit mismatch. These are not reproducible
across runs and not systemically fixable from the prompt. The proper
response at that point is independent verification (the `quote_verified`
mechanism) and surfacing the score-pair to the downstream consumer, not
adding more prompt rules.

### Verify each reviewer complaint before acting on it

Reviewer feedback was load-bearing but not infallible. At least twice it
flagged "routing bugs" or "duplicate headings" that turned out to be
correct content or non-existent. A two-minute substring check or content
inspection before making a prompt change saved chasing ghosts. Treat
external feedback as a candidate signal, not a directive.

## Implementation

The compressor lives in `worker_plan/worker_plan_internal/parameter_extraction/`:

- `compress_report_section.py` — schemas, system and per-bucket prompts,
  six-call chained orchestration, code-side annotation and forced-status
  override, markdown render
- `run_compress_full.py` — driver that builds each job's multi-file blob
  in the same shape the corresponding Luigi task uses, then runs all four
  compress jobs
- `tests/test_compress_report_section.py` — schema shape, section-type
  normalisation, markdown render, forced-status override, and
  English/original-language split

Invoke as:

```
python -m worker_plan_internal.parameter_extraction.run_compress_full
```

with optional `COMPRESS_FULL_LLM`, `COMPRESS_FULL_SAMPLE_DIR`, and
`COMPRESS_FULL_OUTPUT_DIR` overrides.
