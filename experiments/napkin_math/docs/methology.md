# PlanExe Napkin-Math Monte Carlo — Methodology

The PlanExe napkin-math pipeline turns a long PlanExe report into a small
deterministic model and runs 10,000 Monte Carlo simulations against it.
The last section is slideshow content intended for the assessment
slideshow, placed before the plan roster.

## Pipeline overview

Eight stages:

1. `compress_report_section` — compresses four long sections of the PlanExe
   report (Selected Scenario, Review Plan, Premortem, Expert Criticism)
   into inline-tagged digests. Each bucket runs a two-batch emission pass
   (the second pass sees the first pass's items and is asked only for what
   was missed), and the deterministic ranking layer accepts paraphrased
   quotes whose tokens are all present in the source. A code-side
   cross-bucket promoter reroutes gate-shaped tripwires that the LLM filed
   under `risks_and_shocks` into `gates_and_thresholds` before ranking.
2. `prepare_extract_input.py` — concatenates the four compressed digests
   with the four passthrough raw sections (Executive Summary, Project Plan,
   Assumptions, Data Collection) into one `extract_parameters_input.md`
   digest.
3. `extract-parameters-from-digest` — reads the digest and emits a small
   JSON: 4–8 key values, ≤5 missing inputs, ≤5 first calculations, ≤5
   unmodelled existential gates. Inputs carry an inline
   `[source_status | e=N r=N | quote: verified]` tag that records *how* the
   value is known. Two structural prompt rules govern the output:
   *source-arithmetic preservation* — when the report names a
   deterministic relationship (aggregate sum, burn-rate × duration,
   explicit decomposition block), the relationship is preserved as a
   calculation rather than collapsed into a flat bounded variable; and
   *threshold pairing* — every extracted threshold (floor, cap, ceiling,
   target volume / share / deadline) must be paired with a realised-vs-
   threshold margin / surplus calculation, never just declared as a
   value. The optional `dropped_signals` field records ids the extract
   chose not to carry forward, with a structural reason that the
   validator and audit consume.
4. `validate_parameters.py` — enforces 19 structural rules (id
   uniqueness, dependency declaration, formula-RHS declared, comment word
   caps, threshold-friendly naming, no dead-end variables,
   `aggregate_not_bounded` for sum-formula outputs, `requirement_has_margin`
   for `*_required` companion variables, `dropped_signals_schema`, …)
   before any simulation runs.
5. `generate-bounds` — proposes `low / base / high` triangular bounds for
   every missing input and for every key value whose `value_type` or
   `uncertainty` says it needs a distribution. Each bounds entry carries
   `source: "data"` or `source: "assumption"` and a one-sentence rationale.
   The source label is asymmetric: `data` is reserved for bases that the
   LLM moves off the commitment value because a named Premortem / Risk-
   register / Expert-Criticism passage forecasts a gap, and `assumption`
   is mandatory whenever the base sits on the commitment default. Bounds
   for any variable declared as the `output_name` of a calculation are
   stripped before sampling (calculation-output strip rule) so the runner
   does not double-count an aggregate. The bounds schema reserves a
   top-level `correlations` block; the LLM may declare grouped rank
   correlations and the runner surfaces them, but the Gaussian-copula
   sampler is not yet implemented (Phase 8) — declared correlations
   produce a loud warning, never a silent independent shim.
   `sampling_discipline` accepts `fixed / bernoulli_gate / integer /
   fraction / continuous / lognormal / pert`. The last two are
   schema-reserved: the LLM may select them for megaproject CAPEX (per
   Flyvbjerg's iron-law criterion in the bounds prompt) but the sampler
   raises `NotImplementedError` if a run actually requests them — there
   is no triangular fallback.
6. `generate-calculations` — emits one Python function per declared
   formula. The functions are pure: no I/O, no globals, no classes.
7. `run_monte_carlo.py` — the sampling and threshold-evaluation runner.
   This is the only stage that touches randomness.
8. `summarize_assessment.py` — renders the assessment document with the
   manifest, provenance map, gate verdicts, decision implications, failure
   drivers, missing-input rankings, and scenario sanity-check tables.

An optional advisory step, `audit_source_preservation.py`, sits outside
the eight stages. It compares the current `parameters.json` against a
prior baseline (`parameters.json` from the last accepted run) and
classifies every prior signal as `preserved_by_id`,
`preserved_by_output_name`, `preserved_as_formula_dependency`,
`explained_drop` (when the current `dropped_signals` carries a
semantically valid entry covering it), `likely_renamed` (snake-case
token Jaccard ≥ 0.4 to a current id or output_name), or
`absent_unexplained`. The audit is advisory and exits 0 unless its input
is malformed; it does not gate the pipeline. It exists so a v(N) → v(N+1)
diff can be classified mechanically as "rename" vs "structural
restructure" vs "acceptable drop" vs "silent regression" instead of by
hand.

## How a single run works

Given parameters.json, bounds.json, calculations.py, and
montecarlo_settings.json, the runner does the following for each of the
configured `n_runs` (defaulting to 10,000) trials:

1. **Sample each input from its triangular distribution.** Each bounded
   variable is drawn from `triangular(low, base, high)`. The
   `sampling_discipline` tag on the bounds entry post-processes the draw:
   - `continuous` — plain triangular draw clamped to `[low, high]`.
   - `fraction` — draw clamped to `[0, 1]` and then to `[low, high]`.
   - `integer` — continuous draw, rounded, re-clamped to `[low, high]`.
   - `bernoulli_gate` — Bernoulli trial with `default_pass_probability`;
     the result is `low` on failure and `high` on success.
   - `fixed` — `low == base == high`; the variable is genuinely pinned.
   - `lognormal`, `pert` — schema-reserved for megaproject CAPEX and
     fat-tail cost / duration variables; the Phase-8 samplers ship later
     and the runner raises `NotImplementedError` loudly if a run requests
     either today. There is no silent triangular fallback.
   Inputs that are not in bounds.json (key values with a single declared
   numeric `value`, or any variable that is the declared `output_name` of
   a calculation, whose bounds the runner strips before sampling) keep
   their declared / computed value across all 10,000 runs.

   Variables are sampled independently. The bounds schema may carry an
   optional top-level `correlations` block declaring rank-correlated
   groups (the typical pattern: cost variables that co-move under a
   shared inflation or vendor-pricing pressure). The runner reads the
   block but the Gaussian-copula sampler is not yet implemented; when a
   run sees a non-empty `correlations` block it emits a warning naming
   the group count and proceeds to sample independently, so joint-tail
   risk is structurally understated until the sampler ships.

2. **Run the deterministic calculations.** The runner invokes each function
   in `calculations.py` in declaration order. Inputs are pulled from the
   current run's input pool plus any earlier-stage outputs. There is no
   re-sampling within a run; the same draw of every input flows through
   every calculation.

3. **Evaluate each declared threshold.** Each entry in the `thresholds`
   block of `montecarlo_settings.json` is of the form
   `{ "operator": ">=", "value": 0 }` and points at the id of a computed
   output. The output is named so that *positive = pass* — the validator
   enforces the threshold-friendly naming rule at extraction time, so
   margins, surplus, and coverage variables read in the "positive = good"
   direction. The runner records pass / fail per threshold per run.

4. **Tally and aggregate.** After 10,000 runs the per-threshold pass rate
   is the empirical probability that the declared gate holds under the
   declared bounds. Bands:
   - **Robust** if pass rate ≥ 80%.
   - **Marginal** if 50% ≤ pass rate < 80%.
   - **Fragile** if 20% ≤ pass rate < 50%.
   - **Critical** if pass rate < 20%.
   The plan's overall risk band is the band of its worst declared gate.

The seed defaults to `12345` so two runs against the same parameters /
bounds / calculations produce identical output. Re-running after a bounds
tweak is the right way to do sensitivity analysis — change the bounds,
rerun, compare.

## Where the bounds come from

Two layers and one label.

**Layer one — uncertain inputs are flagged by rule.** During parameter
extraction every value gets a `value_type` and an `uncertainty` tag. A
bounds entry is then opened for any variable that is in
`missing_values_to_estimate`, has `value_type ∈ {inferred,
missing_but_needed}`, has `value: null`, has `uncertainty: high`, or has
`uncertainty: medium` paired with `modelling_priority ∈ {critical, high}`.
Variables that fail none of those tests are treated as facts and held
fixed across all 10,000 runs.

**Layer two — the triangular bounds are proposed.** For each flagged
variable, `low / base / high` is chosen informed by:

- *Source-report anchors* — explicit numbers the plan names directly
  (e.g., a stated cost range, a risk-register sensitivity, an expert-review
  sensitivity bracket). The plan's own framing comes first.
- *Source-status tags* on the digest line — `explicit`, `derived`,
  `inferred`, `stress_test`, or `missing`. `stress_test` figures from the
  Premortem are the right anchor for the *upper bound* on a cost variable
  or the *lower bound* on a coverage variable.
- *Spread heuristics* — `±10–20%` on low-uncertainty variables,
  `±25–50%` on medium-uncertainty variables, `≥±50%` (up to 2–5×) on
  high-uncertainty variables.
- *Sampling discipline* — fractions stay in `[0, 1]`, integer counts use
  whole-number bounds, bernoulli gates declare a default-pass probability.

**The label that exposes this to the reader.** Every bounds entry carries
`"source": "data"` (anchored on a source-report number that the rationale
must cite) or `"source": "assumption"` (extrapolated where the report is
silent). The label is **asymmetric on the commitment default**: for an
`actual_X` variable whose `base` sits on the plan's committed `X`, the
source tag is forced to `assumption` (the plan's commitment is a goal,
not evidence of realised outcomes). The tag is `data` only when the LLM
moves `base` off the commitment value because a named Premortem /
Risk-register / Expert-Criticism passage forecasts a gap, and the
rationale cites the passage. The asymmetry is rendered downstream by
`summarize_assessment.py`: `source: "data"` maps to
`basis: "report_derived"` and `source: "assumption"` maps to
`basis: "model_assumption"` in the `Basis` column of the assessment's
*Missing inputs ranked by impact* table — so the column tells the
reader whether a driver was anchored in the source report or
extrapolated by the model. The finer distinction between "anchored on
a plan-internal gap forecast" and "anchored on the bare commitment"
lives in the rationale string, not the `Basis` column.

Citations in the rationale are subject to a `SELF-AUDIT: CITATION
CONTEXT-LEAK` rule in the bounds prompt: a Risk N / Issue N / Decision N
token that appears lexically in the rationale must substantively support
the proposed range. Citing Risk 5 by number when Risk 5's topic is
unrelated to the variable is a context leak, not a citation.

The pipeline never claims the bounds *are* the truth. It claims the bounds
make every assumption visible and editable in a single 10-line JSON
fragment per variable.

## Where the thresholds come from

Each line in the `thresholds` block of `montecarlo_settings.json` points
at one calculation output and says *"this output, evaluated by this
operator against this value, is the gate."* The thresholds themselves are
lifted from the plan, not invented by the model. Every threshold carries a
`threshold_basis` tag:

- **`report_explicit`** — the plan states the threshold directly
  ("if X exceeds 1.20 …", "fleet uptime must hold above 90%"). This is
  the strongest provenance.
- **`report_inferred`** — the plan implies the threshold through framing
  but does not state it as a hard number. The proposed value carries a
  one-line rationale citing the implicit framing.
- **`report_derived`** — the threshold is calculable from other explicit
  plan numbers (e.g., a break-even volume derived from a stated budget
  and per-unit margin).
- **`model_defined`** — the calculation produces a margin or surplus
  whose *direction* is plan-defined but whose zero-crossing the plan does
  not name. The runner uses `>= 0` as the default because the
  threshold-friendly naming rule guarantees positive = pass.

The assessment renders this basis as a column in the *Gate verdicts*
table, so a skeptical reader can immediately see which gates are grounded
in source-report numbers and which were derived by the model.

## Worst-gate framing and its limits

The `overall_risk_band` field in the assessment manifest is the *band of
the plan's worst declared gate*. This is intentional and load-bearing:
when a plan declares multiple binary commitments, the failure of any one
of them is sufficient to fail the plan. The min-over-gates aggregation
respects that — it does not let a 100% pass on the budget gate paper over
a 1% pass on a coverage gate.

What it is *not*:

- It is not a calibrated whole-plan probability. The pass rate is
  conditional on the declared bounds and on the unmodelled gates holding.
- It is not a verdict on the plan as a whole. It is a verdict on whether
  the plan's *modelled gates* are credible under the declared bounds.
- It does not combine across gates with different units (USD vs hours vs
  fraction). The `Aggregation warning` block in the assessment names this
  explicitly.

The assessment also lists *unmodelled existential gates* — gates whose
failure would end the plan independently of any financial or operational
margin (regulatory approval, political signoff, supply continuity,
counterparty acceptance). These never enter the Monte Carlo. They are
listed so a reader sees at a glance that the modelled Critical/Fragile
verdict is conditional on those existential gates holding.

---

## Slideshow content

The two slides below are written to be inserted into the assessment
slideshow *before* the plan roster. They directly answer "where did the
distributions come from?" and "who decided the thresholds?" so the
roster slides land on a reader who already trusts the pipeline.

### Slide A — How the simulation works

- Each uncertain input is drawn **10,000 times** from a triangular
  distribution over its `low / base / high` bounds. Each draw flows through
  a deterministic Python calculation, and the result is checked against the
  declared threshold.
- Same seed (`12345`) reproduces the run exactly.
- The pass rate over 10,000 runs lands the gate in one of four bands:
  ≥80% **Robust**, 50–80% **Marginal**, 20–50% **Fragile**, <20% **Critical**.
- The plan's **overall risk band is the band of its worst declared gate**.
  A budget gate passing 100% does not paper over a coverage gate passing
  1%; the min-over-gates rule respects that each declared commitment must
  hold on its own.
- Existential gates that cannot be tested as numbers (regulatory approval,
  political signoff, supply continuity) are listed in `unmodelled_gates`.
  They qualify the modelled verdict but never enter the simulation.
- Inputs are sampled **independently**. The bounds schema reserves an
  optional `correlations` block; until the Gaussian-copula sampler ships,
  any declared correlation produces a loud warning and joint-tail risk is
  structurally understated. The schema also reserves the `lognormal` and
  `pert` disciplines for megaproject CAPEX — the LLM may select them but
  the runner raises a loud `NotImplementedError` rather than silently
  falling back to triangular.

*The model produces a categorical verdict per gate. It does not produce a
calibrated whole-plan probability.*

### Slide B — Where the numbers come from

**Bounds (the input distributions):**

- Uncertain inputs are flagged by rule: every entry in
  `missing_values_to_estimate`, plus any key value tagged `inferred`,
  `missing_but_needed`, `uncertainty: high`, or `uncertainty: medium` at
  critical / high modelling priority.
- Each uncertain input's `low / base / high` is anchored on **the plan's
  own numbers** — risk-register figures, expert-review sensitivities,
  scenario ranges — with assumption-driven spread (±10–50% by
  uncertainty band) only where the plan is silent.
- Every bounds entry carries a `source` label: **`data`** (anchored on a
  source-report number that the rationale must cite) or **`assumption`**
  (extrapolated where the report is silent). The label is asymmetric on
  commitment defaults — when `base` sits on a stated commitment, the tag
  is `assumption` (a commitment is a goal, not realised evidence); `data`
  is reserved for bases the LLM has moved *off* the commitment because a
  named Premortem / Risk-register / Expert-Criticism passage forecasts a
  gap. The assessment surfaces this as the `Basis` column in *Missing
  inputs ranked by impact* so the reader sees, for each driver, whether
  the bound came from the plan or was extrapolated.
- Citations in the rationale pass a `CITATION CONTEXT-LEAK` self-audit:
  a Risk N / Issue N / Decision N token that appears lexically must
  substantively support the proposed range, not just appear by number.

**Thresholds (the pass/fail gates):**

- Thresholds are **lifted from the plan, not invented**. Each threshold
  carries a `threshold_basis` tag rendered in the *Gate verdicts* table:
  - **`report_explicit`** — the plan states the threshold directly
    ("if uptime < 90%", "if budget exceeds €15B").
  - **`report_inferred`** — the plan implies the threshold; the proposed
    value carries a cited rationale.
  - **`report_derived`** — the threshold is computable from other
    explicit plan numbers.
  - **`model_defined`** — the calculation produces a margin / surplus
    whose direction is plan-defined but whose zero-crossing the plan
    does not name; the runner defaults to `>= 0`.
- The threshold-friendly naming rule guarantees *positive = pass* on every
  margin, surplus, and coverage variable, so the reader never has to
  guess which sign is the good one.

*Every distribution and every threshold in the simulation is traceable
back to a labeled source — either the plan or an explicit modelling
assumption. Nothing in the verdict is unattributed.*
