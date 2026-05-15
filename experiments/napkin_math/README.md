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
PlanExe report
  -> extract-parameters
  -> validate-parameters
  -> repair-parameters, optional
  -> generate-bounds
  -> generate-calculations
  -> run-scenarios
  -> monte-carlo
```

Each stage has a narrow responsibility. This keeps the system easier to debug and prevents a single prompt from trying to do everything.

---

# Stage 1: extract-parameters

## Purpose

`extract-parameters` reads a PlanExe report and returns a compact JSON modelling seed.

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
  "recommended_first_calculations": []
}
```

## Hard caps

The extractor should return at most:

```text
8 key_values
5 derived_questions
5 missing_values_to_estimate
5 recommended_first_calculations
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
  "depends_on": ["registered_vulnerable_population", "outreach_contact_rate_target"],
  "modelling_priority": "critical",
  "uncertainty": "medium",
  "source_text": "60% proactive outreach contact rate to the registered vulnerable population"
}
```

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

---

# Stage 2: validate-parameters

## Purpose

`validate-parameters` checks whether the extractor output is structurally valid and usable by downstream code.

It does not decide whether the modelling choices are perfect. It verifies that the JSON is consistent, bounded, dependency-safe, and machine-readable.

## Input

The JSON output from `extract-parameters`.

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
      "derived_questions": 5,
      "missing_values_to_estimate": 5,
      "recommended_first_calculations": 3
    },
    "rule_id_breakdown": {}
  }
}
```

## Error vs warning

`ERROR` means downstream code should not continue without repair.

`WARN` means the output is still valid but should be reviewed.

A document is valid if and only if:

```text
error_count == 0
```

Warnings do not make the output invalid.

## Validation categories

The validator checks:

```text
JSON parse validity
top-level structure
required fields
array lengths
comment/source_text word caps
enum values
fraction formatting
id uniqueness
snake_case ids
depends_on references
formula RHS references
source_text cleanliness
```

## Important validator rules

### Global id declaration

Every id used in `depends_on` must be declared globally in one of:

```text
key_values[*].id
missing_values_to_estimate[*].id
derived_questions[*].id
recommended_first_calculations[*].id
```

This prevents formulas from referencing variables that the code generator cannot resolve.

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

Simple probability or math notation is allowed:

```text
gate_pass_probability = P(contact_rate >= contact_rate_target) * P(utilization >= utilization_target)
```

But variable-like arguments must be declared.

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

A repaired parameter JSON with the same schema as `extract-parameters`.

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
    "rationale": "Approximate range for 65+, chronic illness, social isolation, and housing-risk overlap."
  },
  "protection_conversion_rate": {
    "unit": "fraction",
    "low": 0.30,
    "base": 0.55,
    "high": 0.75,
    "rationale": "Reflects delivery leakage between contact and usable protection."
  }
}
```

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
1. extract-parameters
2. validate-parameters
3. repair-parameters
4. generate-bounds
5. generate-calculations
6. run-scenarios
7. monte-carlo
```

The first milestone is complete when:

```text
extract-parameters output passes validate-parameters with valid=true
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

All six active pipeline stages are implemented as skills under
`.claude/skills/` and have been tested end-to-end on two unrelated
PlanExe reports:

- a public-health resilience plan (Leipzig Heat Response)
- a commercial consumer-electronics plan (Estonian Faraday enclosure)

Both reports round-trip cleanly through the full chain — extract,
validate (`valid: true`), bound, calculate, scenario, monte-carlo —
into versioned output directories under
`output/<version>/<report-name>/`:

```text
parameters.json     extract-parameters
validation.json     validate-parameters
bounds.json         generate-bounds
calculations.py     generate-calculations
scenarios.json      run-scenarios
montecarlo.json     monte-carlo
```

The same skills handle both domains without per-domain customisation,
so the pipeline is not plan-type-specific.

`repair-parameters` (Stage 3) remains optional and unbuilt. The
extractor has so far produced JSON that passes validation cleanly on
its own; the repair stage will be built if/when an extraction reliably
fails in a way local schema fixes can resolve.

