# PlanExe Parameter Modelling Pipeline

This pipeline turns a PlanExe report into a small, validated modelling specification that can later be used to generate napkin-math calculations, deterministic scenarios, bounds, and Monte Carlo simulations.

The goal is not to fully model the plan in one step. The goal is to extract the few key values that matter, validate them, estimate missing inputs, and then generate simple first-principles calculations.

## Why this exists

PlanExe reports often contain many numbers, risks, goals, decisions, timelines, and KPIs. Most of those are not useful for immediate modelling.

This pipeline focuses on identifying the values that answer questions like:

- What must be true for this plan to work?
- What are the main denominators?
- What are the pass/fail thresholds?
- What are the bottlenecks?
- What values are missing but required?
- What should be calculated before Monte Carlo?

For example, in a public-health plan, the key values may be vulnerable population, outreach rate, intervention effectiveness, baseline harm rate, and budget gates. In an event plan, they may be attendee demand, ticket yield, sell-through, fixed costs, sponsorship, and break-even attendance.

## Pipeline overview

```text
PlanExe report (HTML or extracted text)
  -> [optional] compress_report_section + prepare_extract_input.py
       (produces extract_parameters_input.md, the "digest")
  -> extract-parameters-from-full                  (full HTML input)
        OR
     extract-parameters-from-digest      (digest input — same output schema)
  -> validate-parameters
  -> repair-parameters, optional
  -> generate-bounds
  -> generate-calculations
  -> run-scenarios
  -> monte-carlo                          (Python runner: experiments/napkin_math/run_monte_carlo.py)
```

Each stage has a narrow responsibility. Stages 1-6 are LLM-driven skills under `.claude/skills/`. Stage 7 (Monte Carlo) is the Python script `run_monte_carlo.py`, invoked by the `monte-carlo` skill — the LLM cannot actually sample distributions in-prompt, so the simulation is deterministic Python with a seeded RNG.

There are two extractor skills because PlanExe reports can be very large. `extract-parameters-from-full` reads the raw HTML. `extract-parameters-from-digest` reads the much smaller pre-compressed digest produced by `prepare_extract_input.py`. They emit the same JSON shape, so downstream stages do not care which one ran.

---

# Stage 1: extract-parameters-from-full

## Purpose

`extract-parameters-from-full` reads a PlanExe report and returns a compact JSON modelling seed.

It should identify only the few most important values for napkin math. It is intentionally non-exhaustive.

The output should be small enough for a human to inspect and structured enough for code to process.

## Input

A PlanExe report, usually HTML or extracted text.

## Output

A JSON object with this shape:

```json
{
  "plan_summary": {
    "plan_name": "",
    "plan_type": "",
    "primary_goal": "",
    "modelling_frame": ""
  },
  "key_values": [],
  "derived_questions": [],
  "missing_values_to_estimate": [],
  "recommended_first_calculations": [],
  "unmodelled_gates": []
}
```

`unmodelled_gates` is optional. It may be omitted entirely on plans where every viability claim can be expressed as an executable formula.

## Hard caps

The extractor should return at most:

```text
8 key_values
5 derived_questions
5 missing_values_to_estimate
5 recommended_first_calculations
5 unmodelled_gates
```

It may return fewer. It should not pad the output just to fill the caps.

## What `key_values` are

`key_values` are the most important modelling values found or inferred from the report.

Each key value has this shape:

```json
{
  "id": "outreach_contact_rate_target",
  "label": "Outreach contact rate target",
  "category": "funding_gate",
  "value_type": "explicit",
  "unit": "fraction",
  "value": 0.6,
  "comment": "Pass/fail KPI of the Month 4 gate; share of registered vulnerable residents successfully contacted.",
  "formula_hint": "people_contacted = registered_vulnerable_population * outreach_contact_rate_target",
  "output_name": "people_contacted",
  "output_unit": "people",
  "depends_on": ["registered_vulnerable_population", "outreach_contact_rate_target"],
  "modelling_priority": "critical",
  "uncertainty": "medium",
  "source_text": "60% proactive outreach contact rate to the registered vulnerable population"
}
```

`output_name` and `output_unit` are required whenever `formula_hint` is non-null (and `null` when `formula_hint` is `null`). Downstream consumers — `generate-calculations`, `run-scenarios`, `monte-carlo` — read these directly and do not parse `formula_hint` or pattern-match on tokens. The LLM is the single authority for both fields.

When you want the same calculation to live in `recommended_first_calculations` rather than embedded in a key_value, leave `formula_hint` (and `output_name`/`output_unit`) `null` on the key_value and declare the calculation there. Duplicating the formula in both places is a structural error caught by validation.

## Value types

```text
explicit             directly stated in the report
derived              calculable from other values
inferred             strongly implied but not directly stated
missing_but_needed   needed for modelling but absent from the report
```

## Important extraction principles

The extractor should prefer values that materially affect viability, scale, cost, capacity, impact, or risk.

It should not extract every number in the report.

It should prefer modelling denominators, thresholds, and bottlenecks over descriptive facts.

Examples of high-value modelling variables:

```text
total budget or available budget
gate funding amount
pass/fail KPI threshold
target population
conversion/contact/adoption rate
capacity or throughput
unit cost
reserve or contingency
baseline risk
intervention effectiveness
break-even threshold
```

## True denominator vs internal denominator

A common problem is that plans report an internal KPI denominator, but the real-world denominator is different.

Example:

```text
60% contact rate of registered vulnerable residents
```

This is not the same as:

```text
60% of all vulnerable residents
```

The extractor should preserve this distinction.

Useful modelling chain:

```text
total_target_population
  -> registered_population
  -> contacted_population
  -> protected_population
  -> avoided_harm
```

When the cap forces a choice between the true real-world denominator and the internal program denominator, prefer the true denominator in `key_values` and place the internal denominator in `missing_values_to_estimate`, unless the internal denominator is itself the direct pass/fail gate.

## Contact, protection, and effectiveness

Do not collapse these concepts:

```text
contact_rate                 share of people successfully reached
protection_conversion_rate   share of reached people who receive a usable intervention
intervention_effectiveness   reduction in adverse outcomes among protected people
```

Bad:

```text
protected_people = contacted_people * intervention_effectiveness
```

Better:

```text
protected_people = contacted_people * protection_conversion_rate
avoided_harm = protected_people * baseline_event_rate * intervention_effectiveness
```

## Dependency discipline

`depends_on` must list formula inputs, not formula outputs.

For a formula:

```text
output_id = input_a * input_b
```

`depends_on` should be:

```json
["input_a", "input_b"]
```

It should not include `output_id` unless the RHS also uses it.

All ids in `depends_on` must be declared globally in one of:

```text
key_values
missing_values_to_estimate
derived_questions
recommended_first_calculations
```

`depends_on` must not introduce new variables.

When a formula depends on the output of another computed entry (e.g. `combined_viability_surplus_dkk` depends on `contingency_reserve_dkk`, which is itself the `output_name` of an entry in `recommended_first_calculations`), the **`id` of that producing entry must equal its `output_name`** so the dependency resolves. In other words, for entries in `recommended_first_calculations` and for `derived_questions`, prefer `id == output_name` so cross-stage references work.

If a formula needs an input that is not declared, the extractor should either:

```text
1. add it to missing_values_to_estimate if it is an external input or assumption,
2. add it to recommended_first_calculations if it is a derived intermediate value, or
3. rewrite the formula to avoid that input.
```

## Formula rules

`formula_hint` is not executable Python. It is a simple implementation hint for later stages.

Allowed examples:

```text
people_contacted = registered_vulnerable_population * outreach_contact_rate_target
cost_per_protected_person = total_budget / people_protected
mcr_events_supported = minimum_contingency_reserve / level3_activation_cost
```

Percentages should be represented as fractions:

```text
60% -> value: 0.6, unit: "fraction"
```

## Unmodelled existential gates

Some plans depend on gates the deterministic Python model cannot evaluate:

- legal or regulatory authorization that the model treats as already granted;
- political acceptance, legitimacy, or non-reversal that no input represents;
- compliance infrastructure (AML/KYC banking partners, certifications, operating licences) the model treats as given;
- an external actor's binding commitment (a grid operator, banking consortium, court) treated as a fixed input rather than a probabilistic gate.

These gates have no quantifiable threshold the Monte Carlo can test, but their failure would end the plan independently of any financial or operational threshold the model evaluates. When the source report names such a gate, the extractor declares it in `unmodelled_gates`:

```json
{
  "id": "regulatory_authorization_gate",
  "label": "Federal land-use authorization",
  "why_it_matters": "The plan relies on post-facto authorization for federal land use; expert criticism calls for comprehensive legal submission within 10 days as a precondition.",
  "source_anchor": "expert_criticism",
  "consequence_if_false": "Project shutdown before any financial gate can be evaluated; sponsor capital stranded."
}
```

`source_anchor` is one of: `executive_summary`, `project_plan`, `selected_scenario`, `assumptions`, `review_plan`, `premortem`, `expert_criticism`, `data_collection`.

The array is **optional**. Most plans whose viability can be expressed entirely as executable formulas should omit it or use `[]`. The field exists so that plans whose dominant failure modes are legal/political/compliance can flag those failure modes explicitly, instead of letting the assessment read as a complete feasibility verdict when it is actually a financial stress test.

Do not use `unmodelled_gates` as a dumping ground for risks. Only include gates whose failure would end the plan independently of the financial or operational thresholds the model tests.

---

# Stage 2: validate-parameters

## Purpose

`validate-parameters` checks whether the extractor output is structurally valid and usable by downstream code.

It does not decide whether the modelling choices are perfect. It verifies that the JSON is consistent, bounded, dependency-safe, and machine-readable.

## Implementation

`validate-parameters` is a deterministic Python script: `experiments/napkin_math/validate_parameters.py`. It runs in milliseconds, costs no tokens, and is the producer for the `validation.json` artifact the rest of the pipeline (`summarize_assessment.py`) consumes. The skill at `.claude/skills/validate-parameters/` is a thin wrapper around this script.

## How to run

```sh
/opt/homebrew/bin/python3.11 experiments/napkin_math/validate_parameters.py \
  --parameters <path>/parameters.json \
  [--output    <path>/validation.json]
```

Default output: `<dir-of-parameters>/validation.json`. Exit code is 0 on `valid: true`, 1 on validation errors, 2 on JSON parse failure. The script prints the output path on stdout.

## Input

The JSON output from `extract-parameters-from-full` or `extract-parameters-from-digest` (both produce the same schema).

## Output

A validation report:

```json
{
  "valid": true,
  "error_count": 0,
  "warn_count": 0,
  "violations": [],
  "summary": {
    "counts": {
      "key_values": 8,
      "derived_questions": 3,
      "missing_values_to_estimate": 4,
      "recommended_first_calculations": 5,
      "unmodelled_gates": 3
    },
    "rule_id_breakdown": {},
    "checks_performed": [
      "json_parse",
      "top_level_structure",
      "..."
    ]
  }
}
```

Each entry in `violations` has the shape:

```json
{
  "rule_id": "no_dead_end_variables",
  "severity": "ERROR",
  "path": "$.key_values[3]",
  "message": "key_value `operating_weeks_per_year` is not consumed by any calculation",
  "suggested_fix": "use it in a derived_question or recommended_first_calculation, or drop it"
}
```

`summary.checks_performed` is the authoritative list of what the validator actually ran. `summarize_assessment.py` reads it verbatim and surfaces it as the "Validated" line under `## Confidence and trust boundaries` in `assessment.md`. `summary.rule_id_breakdown` is a `{rule_id: count}` map of how often each rule fired.

## Error vs warning

`ERROR` means downstream code should not continue without repair.

`WARN` means the output is still valid but should be reviewed.

A document is valid if and only if:

```text
error_count == 0
```

Warnings do not make the output invalid.

## The 16 checks

| # | Check | Severity | What it checks |
|---|---|---|---|
| 1 | `json_parse` | ERROR | the file parses as JSON. A parse failure is reported as a single violation with this rule_id and exit code 2. |
| 2 | `top_level_structure` | ERROR | the top-level object has `plan_summary`, `key_values`, `derived_questions`, `missing_values_to_estimate`, and `recommended_first_calculations`. `unmodelled_gates` is optional. |
| 3 | `required_fields` | ERROR | each entry carries the required keys for its array (e.g. every `key_values` entry has `id`, `label`, `category`, `value_type`, `unit`, `value`, `comment`, `formula_hint`, `output_name`, `output_unit`, `depends_on`, `modelling_priority`, `uncertainty`, `source_text`; every `unmodelled_gates` entry — when the field is present — has `id`, `label`, `why_it_matters`, `source_anchor`, `consequence_if_false`). |
| 4 | `array_length_caps` | ERROR | ≤8 `key_values`, ≤5 `derived_questions`, ≤5 `missing_values_to_estimate`, ≤5 `recommended_first_calculations`, ≤5 `unmodelled_gates`. |
| 5 | `global_id_uniqueness` | ERROR | every `id` is unique across all four arrays. |
| 6 | `snake_case_ids` | ERROR | every `id` matches `^[a-z][a-z0-9_]*$` (lowercase letters, digits, underscores, no leading digit). |
| 7 | `depends_on_declared` | ERROR | every id in any `depends_on` matches a declared `id` OR `output_name` somewhere in the file. See "depends_on accepts ids and output_names" below. |
| 8 | `formula_rhs_declared` | ERROR | every snake_case identifier on the RHS of any `formula_hint` is declared (or is the entry's own `output_name`). Built-in functions (`min`, `max`, `abs`, `sum`, `round`, `int`, `float`) are exempt; numeric literals are not identifiers so they fall out naturally. |
| 9 | `fraction_value_range` | ERROR | if a `key_value` has `unit == "fraction"`, its `value` must be in `[0, 1]` or `null`. A 60% value must be `0.6`, not `60`. |
| 10 | `comment_word_caps` | ERROR | each `key_value.comment` is ≤25 words. |
| 11 | `source_text_word_caps` | ERROR | each `key_value.source_text` is ≤20 words. |
| 12 | `output_name_present_when_formula_hint` | ERROR | when `formula_hint` is non-empty, `output_name` must be set. The downstream `monte-carlo` and `run-scenarios` runners read `output_name` directly; they do not parse the formula's LHS. |
| 13 | `output_unit_present_when_formula_hint` | ERROR | when `formula_hint` is non-empty, `output_unit` must be set. |
| 14 | `no_dead_end_variables` | ERROR | every `key_value` and `missing_values_to_estimate` entry is consumed (transitively) by some calculation. A variable extracted "for context" but never multiplied/subtracted/divided into a calculation output is dead weight: it pollutes bounds, shows up as a non-driver in sensitivity reports, and clutters the assessment without adding signal. See "How no_dead_end_variables is computed" below. |
| 15 | `threshold_friendly_naming` | WARN | `output_name`s ending in `_gap` / `_deficit` / `_shortfall` are flagged because they read ambiguously when tested against a `>= 0` / `<= 0` threshold. Preferred suffixes: `_surplus`, `_buffer`, `_margin`, `_coverage`. WARN-only because the validator does not see `montecarlo_settings.json` and can't tell which outputs are actually threshold-tested. |
| 16 | `shared_pool_legitimacy` | (no-op) | listed in `checks_performed` for completeness; enforcement is upstream in the extractor's system prompt (requires reading source narrative to verify multiple subtracted pressures legitimately draw on one named pool, which is not a structural check). |

## Important validator rules

### depends_on accepts ids and output_names

Every id used in `depends_on` must match a declared identifier somewhere in the file. The validator accepts either form:

```text
key_values[*].id                          OR  key_values[*].output_name
missing_values_to_estimate[*].id
derived_questions[*].id                   OR  derived_questions[*].output_name
recommended_first_calculations[*].id      OR  recommended_first_calculations[*].output_name
```

The output_name path matters in practice. The extractor often gives `derived_questions` `q_*`-style ids whose `output_name` differs from the id — for example, an entry with `id: q_weakest_program_gate` may have `output_name: weakest_program_gate_surplus_eur`. A downstream aggregate that consumes this value naturally references the output_name (the computed quantity), not the question's id. Both are legitimate; the validator treats them identically.

This prevents formulas from referencing variables that the code generator cannot resolve.

### How no_dead_end_variables is computed

The validator builds the set of "referenced" identifiers in two passes:

1. **Direct.** Every id in `depends_on` of any `derived_questions` or `recommended_first_calculations` entry, plus every snake_case identifier on the RHS of any of their `formula_hint`s.
2. **Transitive.** Iteratively: if a `key_value`'s `output_name` is in the referenced set, then every RHS variable of that key_value's `formula_hint` is also referenced. Repeat until the set stabilises.

A `key_value` or `missing_values_to_estimate` entry is dead-end if neither its `id` nor its `output_name` ends up in the referenced set. Recommended fixes (in priority order):

1. Add a calculation that uses the variable. For a trigger value, the natural form is `<x>_margin = actual_share - threshold_share`, and the corresponding `actual_share` must also be added if absent.
2. If no useful calculation exists, drop the variable.

It is better to return six well-connected `key_values` than eight where two are dead-ends. The array caps are a ceiling, not a target.

### Formula RHS declaration

Every identifier on the right-hand side of a `formula_hint` must be globally declared.

The left-hand side may introduce the output id.

Example:

```text
people_contacted = registered_vulnerable_population * outreach_contact_rate_target
```

RHS ids that must be declared:

```text
registered_vulnerable_population
outreach_contact_rate_target
```

LHS output:

```text
people_contacted
```

The LHS does not need to be declared elsewhere if it is the current entry's id.

### Numeric literals

Numeric literals are allowed and do not need declaration.

Example:

```text
kit_procurement_allocation = pre_gate_budget * 0.4
```

`0.4` does not need an id.

### Function-style formulas

The validator exempts these built-in function names from RHS declaration: `min`, `max`, `abs`, `sum`, `round`, `int`, `float`. Variable-like arguments inside the parentheses must still be declared.

```text
weakest_financial_gate_surplus_eur = min(clearing_capacity_surplus_eur, regulatory_risk_buffer_surplus_eur, royalty_cost_coverage_surplus_eur)
rental_revenue_shortfall = max(0, expected_revenue - achievable_revenue)
```

The validator does not extract probability-style `P(...)` notation. If the extractor emits a formula with `P(x >= y)`, the validator will report each variable-like identifier inside the parentheses as `formula_rhs_declared`-eligible. Prefer simple algebraic formulas over custom function syntax.

## Exit codes

```text
0 — valid: true
1 — valid: false (one or more ERROR-level violations)
2 — JSON parse failure (a single json_parse violation; valid: false)
```

A pipeline driver can branch on the exit code without parsing `validation.json`.

## What happens next

`validation.json` is consumed by `summarize_assessment.py`:

- `validation.valid` becomes `assessment.machine_summary.validation_status` (`valid` / `invalid` / `unknown`).
- `validation.summary.checks_performed` is surfaced verbatim as the "Validated" line under `## Confidence and trust boundaries` in `assessment.md`.
- The "Not validated" list in `assessment.md` is a canonical disclaimer (real-world accuracy of bounds, independence assumptions, external feasibility, factual truth of source claims) that the validator does **not** address — those are not structural checks.

If `validate-parameters` returns `valid: false`, the right next step is to regenerate `parameters.json` (re-run `extract-parameters-from-digest` or `extract-parameters-from-full`) or to hand-edit it and re-validate. The historical `repair-parameters` stage below was a planned LLM-driven repair step that has not been implemented.

---

# Stage 3: repair-parameters, optional

## Purpose

`repair-parameters` takes an invalid extractor output and a validation report, then fixes the JSON.

This stage should be used only when `validate-parameters.valid == false`.

## Input

```text
1. extracted parameter JSON
2. validation report
```

## Output

A repaired parameter JSON with the same schema as `extract-parameters-from-full`.

## Typical repairs

```text
Add missing dependency ids to missing_values_to_estimate.
Move formula outputs out of depends_on.
Add RHS inputs to depends_on.
Convert 60 to 0.6 for fraction values.
Rename invalid ids to snake_case.
Remove extra fields.
Trim comments or source_text to word limits.
Remove duplicate ids.
```

## Repair rule

Repairs should be minimal. Do not reinterpret the whole plan if a local schema repair is enough.

---

# Stage 4: generate-bounds

## Purpose

`generate-bounds` adds low/base/high assumptions for missing or uncertain values.

It prepares the model for deterministic scenarios and later Monte Carlo.

## Input

A valid parameter JSON.

## Output

A bounds JSON, keyed by variable id.

Example:

```json
{
  "vulnerable_population_share": {
    "unit": "fraction",
    "low": 0.10,
    "base": 0.20,
    "high": 0.30,
    "rationale": "Approximate range for 65+, chronic illness, social isolation, and housing-risk overlap.",
    "source": "assumption",
    "sampling_discipline": "fraction",
    "non_negative": true,
    "default_pass_probability": null
  },
  "month4_gate_release_eur": {
    "unit": "EUR",
    "low": 0,
    "base": 1500000,
    "high": 1500000,
    "rationale": "Binary gate-dependent release: 0 if Month 4 gate fails, 1.5M if it passes.",
    "source": "data",
    "sampling_discipline": "bernoulli_gate",
    "non_negative": true,
    "default_pass_probability": 0.7
  }
}
```

Required fields per bound entry:

| Field | Meaning |
|---|---|
| `unit` | unit string (e.g. `"fraction"`, `"DKK"`, `"people"`, `"hours_per_year"`) |
| `low`, `base`, `high` | the three numbers, with `low ≤ base ≤ high` |
| `rationale` | ≤30 words explaining the range |
| `source` | `"data"` (anchored in a real reference) or `"assumption"` |
| `sampling_discipline` | one of `fixed | bernoulli_gate | integer | fraction | continuous` — read directly by the Monte Carlo runner; no pattern-matching on unit strings |
| `non_negative` | boolean; when `true`, the runner clamps draws to `≥ 0` |
| `default_pass_probability` | required number in `[0, 1]` when `sampling_discipline == "bernoulli_gate"`; otherwise must be `null` |

Choose `sampling_discipline` by the variable's nature (people/units → `integer`, share/rate → `fraction`, currency → `continuous`, binary tranche/permit → `bernoulli_gate`, pinned constant → `fixed`). The runner does not infer this; missing or invalid values cause a `SCHEMA ERROR` exit.

## What needs bounds

Bounds are especially important for:

```text
missing_values_to_estimate
inferred key_values
high-uncertainty key_values
probability inputs
conversion rates
baseline event rates
costs with weak evidence
capacity assumptions
```

## Bounds are not facts

Bounds are modelling placeholders. They should be labelled as assumptions unless backed by data.

---

# Stage 5: generate-calculations

## Purpose

`generate-calculations` turns `formula_hint` entries into simple deterministic Python functions.

This should happen after validation, and preferably after bounds exist for missing inputs.

## Input

```text
1. valid parameter JSON
2. optional bounds JSON
```

## Output

Python code containing deterministic functions for recommended first calculations and derived questions.

Example:

```python
def people_contacted(registered_vulnerable_population: float, outreach_contact_rate_target: float) -> float:
    return registered_vulnerable_population * outreach_contact_rate_target


def cost_per_protected_person(total_budget: float, people_protected: float) -> float:
    if people_protected <= 0:
        return float("inf")
    return total_budget / people_protected
```

## Code-generation rules

Generated code should:

```text
Use function names based on calculation ids or formula LHS.
Use explicit arguments based on depends_on.
Add divide-by-zero guards.
Use floats for numeric modelling.
Avoid hidden global state.
Return dictionaries for grouped scenario outputs.
Keep functions small and inspectable.
```

## What not to do

Do not generate Monte Carlo first.

Do not generate a large application.

Do not invent a complex class hierarchy unless the formulas require it.

Start with deterministic functions.

---

# Stage 6: run-scenarios

## Purpose

`run-scenarios` applies low/base/high assumptions to the generated deterministic functions.

This gives an early reality check before Monte Carlo.

## Input

```text
1. valid parameter JSON
2. bounds JSON
3. generated calculation functions
```

## Output

A scenario table.

Example:

```text
scenario | vulnerable_population | people_contacted | people_protected | cost_per_protected_person
low      | 40,000                | 4,800            | 1,440            | €2,431
base     | 80,000                | 14,400           | 7,920            | €442
high     | 120,000               | 28,800           | 21,600           | €162
```

## Scenario purpose

Scenario tables answer:

```text
What happens in the downside case?
What does the base case require?
What has to be true for the upside case?
Which assumption dominates the result?
```

---

# Stage 7: monte-carlo

## Purpose

`monte-carlo` samples uncertain inputs and estimates distributions of outputs.

Monte Carlo should come after deterministic calculations and bounds are working.

Unlike Stages 1-6, this stage is **not** LLM-driven. The simulation runs in `experiments/napkin_math/run_monte_carlo.py` — a deterministic Python script with a seeded NumPy RNG. The `monte-carlo` skill is a thin wrapper that locates the inputs, builds optional settings, invokes the runner, and reports back. The LLM cannot actually draw 10k correlated samples in-prompt, so this stage was lifted out of the prompt.

## Input

```text
1. valid parameter JSON
2. bounds JSON
3. generated calculation functions (calculations.py)
4. optional run settings (n_runs, seed, distribution_default,
   outputs_of_interest, thresholds, gate_probabilities,
   correlation_groups)
```

## Output

A JSON document with per-output summary statistics, per-threshold pass
probabilities, a Pearson-correlation sensitivity ranking of input
drivers, and aggregated warnings.

```json
{
  "valid": true,
  "settings": { "n_runs": 10000, "seed": 12345, "distribution_default": "triangular" },
  "outputs": {
    "<output_id>": {
      "unit": "EUR",
      "count": 10000,
      "missing_count": 0,
      "mean": 0, "std": 0,
      "min": 0, "p05": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0, "max": 0
    }
  },
  "thresholds": {
    "<output_id>": {
      "operator": ">=", "value": 0,
      "success_count": 0, "valid_count": 10000, "probability": 0.0
    }
  },
  "sensitivity": {
    "<output_id>": { "top_inputs": [ { "id": "...", "correlation": 0.0 } ] }
  },
  "warnings": []
}
```

## Monte Carlo should not be first

Before Monte Carlo, the pipeline should already know:

```text
the main denominators
the missing inputs
the deterministic formulas
the low/base/high scenario behavior
```

Monte Carlo answers "how often?" It does not replace first-principles structure.

---

# Recommended implementation order

Build the stages in this order:

```text
1. extract-parameters-from-full
2. validate-parameters
3. repair-parameters
4. generate-bounds
5. generate-calculations
6. run-scenarios
7. monte-carlo
```

The first milestone is complete when:

```text
extract-parameters-from-full output passes validate-parameters with valid=true
```

The second milestone is complete when:

```text
generate-calculations can produce deterministic Python functions from a valid extraction
```

The third milestone is complete when:

```text
run-scenarios can produce low/base/high outputs without manual edits
```

The fourth milestone is complete when:

```text
monte-carlo can produce per-output distributions and per-threshold pass
probabilities from the same trio of artifacts
```

---

# Design principles

## Keep stages narrow

Each stage should do one thing.

Bad:

```text
One prompt extracts values, estimates bounds, writes code, runs scenarios, and critiques the plan.
```

Good:

```text
extract -> validate -> repair -> bound -> calculate -> scenario -> simulate
```

## Prefer explicit schemas

Every stage should have a defined input and output schema.

This makes errors visible and repairable.

## Treat LLM output as untrusted until validated

Even good model output should pass through validation before code generation.

## Prefer deterministic calculations before Monte Carlo

Monte Carlo is useful only after the deterministic model is sane.

## Keep assumptions editable

Missing and inferred values should remain visible assumptions, not hidden constants.

## Do not overfit to one report type

The same pipeline should work for:

```text
public health plans
event plans
startup plans
construction plans
software plans
education plans
climate plans
logistics plans
research plans
```

The extractor should adapt the modelling frame to the plan's purpose.

---

# Current status

All seven active pipeline stages have been tested end-to-end on three
unrelated PlanExe reports:

- a public-health resilience plan (Leipzig Heat Response)
- a commercial consumer-electronics plan (Estonian Faraday enclosure)
- a commercial community-arts plan (Nuuk Community Clay Workshop — DKK-denominated)

All three reports round-trip cleanly through the full chain — extract,
validate (`valid: true`), bound, calculate, scenario, monte-carlo —
into versioned output directories under
`output/<version>/<report-name>/`:

```text
parameters.json     extract-parameters-from-full (or extract-parameters-from-digest)
validation.json     validate-parameters
bounds.json         generate-bounds
calculations.py     generate-calculations
scenarios.json      run-scenarios          (LLM-driven)
montecarlo.json     monte-carlo            (Python runner)
```

The same skills handle all three domains without per-domain customisation,
so the pipeline is not plan-type-specific or currency-specific.

`repair-parameters` (Stage 3) remains optional and unbuilt. The
extractor has so far produced JSON that passes validation cleanly on
its own; the repair stage will be built if/when an extraction reliably
fails in a way local schema fixes can resolve.

## Smoke tests

A pytest-style suite at `experiments/napkin_math/tests/test_run_monte_carlo.py` (44 cases) covers the runner's edge cases: sampling-discipline semantics, schema validation for every required field, calculation execution failures, sensitivity ranking, threshold operators, determinism. These tests run in CI via `python test.py` and locally via the `test-napkin-math` skill, which also re-runs the `compress_report_section` pytest suite and the end-to-end smoke fixture under `tests/fixtures/smoke/`.

