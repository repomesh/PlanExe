# PlanExe Report Section Filtering for Parameter Extraction

## Purpose

This document describes which sections of a PlanExe HTML/Markdown report are worth sending to a parameter-extraction LLM for Monte Carlo / napkin-math modelling, and which sections can usually be removed to save tokens.

The goal is not to summarize the full plan. The goal is to preserve the parts that contain:

- explicit numeric values
- important assumptions
- uncertainty drivers
- capacity constraints
- budget and funding gates
- risks and shocks
- missing data
- viability thresholds
- quantities that should become model inputs, bounds, or calculations

A full PlanExe report contains many sections that are useful for humans but weak for quantitative modelling. Feeding the entire report wastes tokens and can distract the extractor.

---

## Recommended default: do not feed the full report

For parameter extraction, use a filtered modelling view instead of the full HTML.

Recommended modelling digest:

1. Goal and top-level constraints
2. Explicit numeric values
3. Assumptions and ranges
4. Critical decisions and trade-offs
5. Risks, shocks, and failure paths
6. Missing data / evidence needed
7. Staffing and capacity, only when relevant
8. Schedule gates, only when relevant

---

## Section classification

| Section | Default action | Parameter value | Notes |
|---|---:|---:|---|
| Executive Summary | Keep | High | Dense source of budget, deadline, contingency, success criteria, and top risks. |
| Project Plan | Keep | Very high | Often the best general-purpose source for SMART targets, dependencies, resources, risks, compliance, and mitigation. |
| Strategic Decisions | Keep, but compress | High | Good for identifying critical levers and uncertainty drivers, but verbose. |
| Assumptions | Keep | Very high | Usually the strongest source for model inputs, ranges, uncertainty, and Monte Carlo variables. |
| Review Plan | Keep or compress | High | Good for identifying validation questions, fragile assumptions, and gates. |
| Premortem | Keep or compress | High | Strong source of downside scenarios, shocks, and failure paths. |
| Expert Criticism | Keep or compress | High | Often identifies hidden assumptions, missing denominators, and weak claims. |
| Data Collection | Keep | High | Excellent source for `missing_values_to_estimate` and estimation methods. |
| Team | Conditional | Medium to high | Keep when staffing, FTE, capacity, shifts, or accountability affect viability. |
| Scenarios | Conditional | Medium | Useful for low/base/high framing, but often narrative-heavy. |
| SWOT Analysis | Conditional | Low to medium | Useful for qualitative risk discovery, weak for direct numeric extraction. |
| Initial Prompt Vetted | Conditional | Medium | Useful as original constraints/source-of-truth, but can duplicate summary/plan. |
| Governance | Usually omit | Low to medium | Keep only when governance/compliance failure is central to the model. |
| Work Breakdown Structure | Usually omit | Low | Very noisy unless doing schedule/resource simulation. |
| Questions & Answers | Usually omit | Low | Often duplicates other sections. Keep only if it contains unique clarifications. |
| Self Audit | Usually omit | Low to medium | Can contain useful critique but usually duplicates Review/Premortem/Expert Criticism. |
| Pitch | Omit | Low | Persuasive duplicate; high risk of narrative bias and repeated numbers. |
| Documents to Create and Find | Omit | Low | Describes artifacts, not plan viability parameters. |
| Related Resources | Omit from extraction | Low | May be useful later for bounds research, not first-pass extraction. |
| Prompt Adherence | Omit | Low | Meta-evaluation, not modelling data. |
| Gantt Interactive | Omit | Very low | Mostly UI and schedule visualization scaffolding. |
| Execute Plan | Omit | Very low | Action/acknowledgement content, not modelling data. |

---

## Sections to keep

### Executive Summary

Keep by default.

This section is usually compact and high-value. It often contains the plan's main quantitative anchors:

- total budget
- launch deadline
- contingency reserve
- top-level revenue or outcome mix
- key success criteria
- top risks
- strategic framing
- major go/no-go claims

For extraction, this section helps the model understand what the plan claims must be true.

Typical extracted parameters:

```text
total_budget
deadline
contingency_fraction
target_revenue_mix
conversion_target
success_threshold
critical_risk
```

---

### Project Plan

Keep by default.

This is usually the strongest general-purpose section for parameter extraction. It tends to include:

- SMART criteria
- dependencies
- resources required
- risk assessment
- mitigation plans
- regulatory/compliance requirements
- operational constraints
- capacity assumptions
- deadline gates

Typical extracted parameters:

```text
operational_readiness_date
staffing_count
budget
resource_buffer
regulatory_deadline
minimum_viable_rate
failure_mitigation_cost
required_capacity
```

This section is especially important because it often connects numbers to viability claims.

---

### Strategic Decisions

Keep, but compress.

This section is valuable because it identifies the parameters that matter most. It is also usually verbose and repetitive.

Keep:

- decision title
- core decision
- why it matters
- strategic choices
- trade-off / risk
- justification

Usually drop or compress:

- long synergy/conflict prose
- repeated narrative framing
- broad persuasion
- duplicate descriptions

Typical extracted parameters:

```text
critical_lever
tradeoff_variable
risk_driver
scenario_axis
uncertain_assumption
capacity_constraint
```

Strategic Decisions is often better for identifying *what should be modelled* than for extracting clean numeric values.

---

### Assumptions

Keep by default.

This is often the highest-density modelling section.

It is likely to contain:

- explicit assumptions
- uncertainty ranges
- low/base/high candidates
- cost assumptions
- demand assumptions
- conversion assumptions
- operational assumptions
- risk assumptions

Typical extracted parameters:

```text
unit_cost
conversion_rate
demand_fraction
material_buffer
utilization_rate
risk_probability
shock_cost
baseline_cost
```

If token budget is tight, prioritize this section over narrative-heavy sections.

---

### Review Plan

Keep or compress.

This section is useful because it often names what must be checked before the plan can be trusted.

Good source for:

- validation questions
- fragile assumptions
- unproven demand claims
- missing evidence
- pass/fail criteria
- stress-test targets
- modelling blind spots

Typical extracted parameters:

```text
gate_threshold
validation_metric
minimum_required_margin
required_utilization
unvalidated_assumption
critical_dependency
```

Review Plan helps the extractor distinguish decorative numbers from important modelling gates.

---

### Premortem

Keep or compress.

This is one of the best sections for downside modelling.

Good source for:

- failure paths
- compound risks
- shock scenarios
- contingency depletion paths
- operational collapse modes
- downside bounds

Typical extracted parameters:

```text
shock_cost
failure_probability
contingency_drawdown
demand_shortfall
capacity_failure
delay_cost
```

This section is especially useful when the simulation should challenge the plan rather than merely reproduce its optimistic assumptions.

---

### Expert Criticism

Keep or compress.

This section often identifies hidden assumptions more directly than the plan itself.

Good source for:

- missing denominators
- unrealistic assumptions
- weak risk controls
- unmodelled cost drivers
- underestimated staffing burden
- regulatory/compliance uncertainty
- fragile revenue assumptions

Typical extracted parameters:

```text
missing_denominator
required_capacity
unmodelled_cost
failure_threshold
risk_multiplier
uncertain_rate
```

If the extractor has trouble finding the “real” model drivers, this section is often more useful than the pitch or governance sections.

---

### Data Collection

Keep by default.

This is especially useful for generating `missing_values_to_estimate`.

Good source for:

- what evidence is missing
- how to estimate missing values
- what external data is required
- which values need validation
- which assumptions need bounds

Typical extracted parameters:

```text
missing_conversion_rate
missing_cost_per_unit
missing_utilization_rate
missing_capacity_denominator
missing_baseline_risk
suggested_estimation_method
```

This section helps the pipeline produce better bounds and avoids pretending that unknowns are known.

---

## Conditional sections

### Team

Use when staffing matters.

Keep this section when the plan depends on:

- staffing capacity
- FTE assumptions
- shift coverage
- redundancy
- instructor/operator availability
- role-specific throughput
- personnel cost
- accountability structure

Omit or compress when staffing is not central to viability.

Typical extracted parameters:

```text
fte_count
hours_per_week
coverage_ratio
staffing_capacity
required_staffing
labor_cost
```

---

### Scenarios

Use when scenario framing is needed.

This section can help identify low/base/high cases, but it is often narrative-heavy.

Keep if:

- the scenarios contain explicit numbers
- the plan uses scenarios as decision gates
- the simulation needs scenario axes
- the scenario descriptions reveal important failure modes

Omit if it only restates the plan in optimistic/base/pessimistic prose.

---

### SWOT Analysis

Usually low numeric value.

Keep only when the pipeline needs qualitative risk discovery or when other risk sections are missing.

SWOT is useful for identifying:

- broad risk categories
- opportunities
- external constraints
- qualitative weaknesses

But it rarely contains the clean inputs needed for Monte Carlo.

---

### Initial Prompt Vetted

Use as source-of-truth context when needed.

This section can help detect whether the generated plan drifted from the original user request.

Keep if:

- the report may have invented assumptions
- the original prompt contains hard constraints
- the generated plan has conflicting goals
- you need to preserve user intent

Otherwise it often duplicates the Executive Summary and Project Plan.

---

### Governance

Usually omit.

Keep only when governance/compliance is a central source of cost, delay, risk, or failure.

For most financial or operational simulations, governance sections are long and low-density. Important compliance parameters are usually repeated more cleanly in:

- Project Plan
- Review Plan
- Premortem
- Expert Criticism

---

### Work Breakdown Structure

Usually omit.

This section is often very noisy for parameter extraction.

It may contain:

- task IDs
- hierarchy levels
- task names
- sequencing details
- repeated dates
- implementation prose

Keep only when the model is specifically about:

- schedule simulation
- resource allocation
- critical path
- task-level cost estimation
- delivery risk

For first-pass viability Monte Carlo, omit.

---

### Questions & Answers

Usually omit.

Keep only if it contains unique clarifications that are not present elsewhere.

Otherwise it tends to repeat the plan in conversational form and adds token cost without many new parameters.

---

### Self Audit

Usually omit.

This can be useful as an extra critique pass, but it often duplicates:

- Review Plan
- Premortem
- Expert Criticism

Keep only if those sections are absent or weak.

---

## Sections to omit by default

### Pitch

Omit.

The pitch is persuasive narrative. It often repeats values from the Executive Summary and Project Plan, but with stronger rhetorical framing.

Risk of including it:

- duplicates numbers
- reinforces overconfident claims
- wastes tokens
- increases narrative bias

If the pitch contains a unique number, it should usually be captured elsewhere too.

---

### Documents to Create and Find

Omit.

This section describes supporting artifacts, not plan viability.

It is useful for project execution but weak for Monte Carlo parameter extraction.

Keep only if the model explicitly includes documentation workload, compliance-document production, or research effort.

---

### Related Resources

Omit from first-pass extraction.

This section may be useful later for bounds research or external validation, but it usually does not contain plan-native parameters.

Do not include it in the main extraction prompt unless the report itself lacks enough context.

---

### Prompt Adherence

Omit.

This is meta-evaluation of whether the generated plan followed the prompt. It is rarely useful for quantitative modelling.

---

### Gantt Interactive

Omit.

This section is mostly UI, script, styles, and visualization scaffolding.

It is not a good source of modelling parameters.

If schedule modelling is needed, use a clean task table or extracted schedule data instead of the interactive HTML block.

---

### Execute Plan

Omit.

This section normally contains execution buttons, placeholders, or action acknowledgements. It is not useful for parameter extraction.

---

## Recommended extraction profiles

### General viability Monte Carlo

Use:

```text
Executive Summary
Project Plan
Strategic Decisions, compressed
Assumptions
Review Plan
Premortem
Expert Criticism
Data Collection
Team, if staffing/capacity matters
```

Omit:

```text
Pitch
Gantt Interactive
Execute Plan
Prompt Adherence
Documents to Create and Find
Related Resources
Work Breakdown Structure
Questions & Answers
Governance, unless compliance is central
Self Audit, unless critique sections are weak
```

---

### Commercial / small-business plan

Prioritize:

```text
Executive Summary
Project Plan
Assumptions
Strategic Decisions
Review Plan
Premortem
Expert Criticism
Data Collection
Team, if labor capacity matters
```

Look for:

```text
budget
fixed_cost
variable_cost
unit_revenue
conversion_rate
capacity
utilization
gross_margin
break_even_volume
contingency
funding_gate
demand_shortfall
shock_cost
```

Usually omit:

```text
Pitch
Governance
Documents to Create and Find
Related Resources
Gantt Interactive
Prompt Adherence
Execute Plan
```

---

### Public-health / resilience / nonprofit plan

Prioritize:

```text
Executive Summary
Project Plan
Assumptions
Data Collection
Review Plan
Premortem
Expert Criticism
Team, if response capacity matters
Scenarios, if response levels matter
```

Look for:

```text
target_population
people_reached
people_protected
coverage_rate
baseline_risk
intervention_effectiveness
capacity
cost_per_person
avoided_harm
funding_gate
surge_cost
runway
```

Usually omit:

```text
Pitch
Documents to Create and Find
Related Resources
Prompt Adherence
Execute Plan
Gantt Interactive
```

---

### Schedule / delivery-risk simulation

Prioritize:

```text
Project Plan
Dependencies
Work Breakdown Structure
Gantt / task data, if available in clean structured form
Team
Risk Assessment
Review Plan
Premortem
```

Look for:

```text
task_duration
dependency
critical_path
resource_constraint
staffing_capacity
deadline
delay_cost
approval_gate
procurement_lead_time
```

Unlike financial viability modelling, this profile may need Work Breakdown Structure or Gantt-derived data.

---

## Practical preprocessing recommendation

Instead of sending raw HTML, convert the report into a compact modelling digest.

Suggested digest structure:

```text
# Modelling Digest

## Goal and constraints
- ...

## Explicit numeric values
- ...

## Assumptions and ranges
- ...

## Critical decisions and trade-offs
- ...

## Risks and shocks
- ...

## Missing data and evidence needed
- ...

## Capacity and staffing, if relevant
- ...

## Schedule and gate constraints, if relevant
- ...
```

This gives the parameter extractor cleaner signal and fewer distractors.

---

## Token-saving rules

Use these rules before sending content to the parameter extractor:

1. Remove HTML, CSS, JavaScript, UI controls, and Gantt rendering code.
2. Remove persuasive sections unless they contain unique numeric values.
3. Remove duplicate restatements of the same budget, date, or KPI.
4. Compress Strategic Decisions to decision title, core decision, why it matters, choices, and trade-off.
5. Keep critique and premortem sections because they expose failure modes.
6. Keep assumptions and data-collection sections because they expose inputs and missing values.
7. Omit sections that describe documents, resources, governance mechanics, or prompt adherence unless directly relevant to the model.
8. Prefer sections that contain formulas, thresholds, denominators, bounds, rates, quantities, capacities, or shock costs.
9. Prefer sections that explain why a number matters over sections that merely repeat the number.
10. For first-pass modelling, prioritize viability gates over implementation detail.

---

## Summary recommendation

For most PlanExe reports, the default extraction bundle should be:

```text
Executive Summary
Project Plan
Strategic Decisions, compressed
Assumptions
Review Plan
Premortem
Expert Criticism
Data Collection
```

Add conditionally:

```text
Team
Scenarios
Initial Prompt Vetted
SWOT Analysis
Work Breakdown Structure, only for schedule simulation
Governance, only for compliance-heavy models
```

Omit by default:

```text
Pitch
Gantt Interactive
Execute Plan
Prompt Adherence
Documents to Create and Find
Related Resources
Questions & Answers
Self Audit
```

The main principle:

> Feed the extractor sections that contain assumptions, gates, risks, denominators, and missing evidence. Drop sections that mainly contain persuasion, UI, documentation planning, or duplicate narrative.

---

## Reference implementation

A first reference implementation of this section-filtering recommendation lives in `experiments/napkin_math/prepare_extract_input.py`. It assembles `extract_parameters_input.md` in 137's order, with the Strategic Decisions slot replaced by **Selected Scenario** per [proposal 139](139-compress-for-monte-carlo.md) to keep rejected alternatives out of the parameter extractor.

The bundle is mixed-format:

- The four sections 137 marks "Keep or compress" (Selected Scenario, Review Plan, Premortem, Expert Criticism) are compressed via `compress_report_section`. Each bullet carries an inline epistemic tag of the form `[<source_status> | e=N r=N | quote: verified|unverified]`.
- The four sections marked plain "Keep" (Executive Summary, Project Plan, Assumptions, Data Collection) are passed through raw from the PlanExe sample. They are already short and primarily numeric; further compression risks dropping modelling primitives.

The companion skill `experiments/napkin_math/.claude/skills/extract-parameters-from-digest/` consumes the assembled file and produces a JSON parameter set with the same schema as the `extract-parameters` skill that reads the full PlanExe HTML. The two skills are head-to-head comparable on the same source plan.

---

## Lessons from the first reference implementation

A handful of failure modes recurred during head-to-head testing against the full-HTML pipeline. Recording them so the next implementation does not re-discover them.

### Budget and revenue are not the same denominator

When the report says "25% from rentals" or "40% Courses, 35% Memberships, 25% Drop-ins", that is a share of **revenue**, not of budget. An extractor that builds `rental_revenue = budget * rental_share` silently conflates spend capacity with sales target, and every downstream coverage and utilization ratio derived from that formula is distorted. The remedy is to surface `year1_revenue_target_dkk` (or the period equivalent) as a missing input whenever a revenue-mix share is captured without an explicit revenue target in the source. The same trap exists for cost-share, margin-share, contribution-share, and channel-share percentages.

### Cross-section duplication is the consumer's job to resolve

The four compressed sections routinely surface the same primitive ("minimum viable rental rate", "off-peak hourly price", "speculative high hourly rate") under different phrasings, because each compress call sees a different multi-file Luigi blob and is asked to be locally complete. Resist the urge to deduplicate inside the compressor — losing redundancy loses per-section provenance. The downstream extractor is where canonicalisation belongs: pick one stable snake_case id, merge near-duplicates, prefer the framing closest to a modelling primitive (rate, count, fraction, amount-per-period).

### Denominator-pairing is cheap and load-bearing

Every rate, share, conversion rate, hourly price, FTE count, and failure-duration magnitude in the digest needs a paired denominator or scaling input to be turned into an executable Monte Carlo formula. The compressor surfaces those denominators as `[missing]` items in the `missing_data_to_estimate` bucket — revenue target for a revenue-mix share, billable hours for an hourly rate, attendee count for a conversion rate, per-head cost for a headcount, per-period revenue exposure for a downtime duration. Without this rule the extractor invents the denominator, which makes the resulting distribution arbitrary.

### Strategic-Decisions content still arrives, just not as a standalone section

Substituting Selected Scenario for Strategic Decisions (per 139) does not lose the rejected-alternative content the planner considered. That content still flows into the compressor through the multi-file Luigi blobs that feed Review Plan, Premortem, and Expert Criticism — the compressor sees it as context but does not promote rejected alternatives into the numeric_values or gates of any section. The substitution is about provenance discipline, not information loss.

### Raw "Keep" sections are not free

The four raw sections inflate the digest by ~30 KB on the Nuuk sample (the compressed digest alone is ~21 KB; the full bundle is ~56 KB). That is the cost of preserving Executive Summary, Project Plan, Assumptions, and Data Collection at full fidelity. The savings claim ("instead of a 100 KB+ HTML report") still holds, but the extractor's prompt needs to make clear that raw sections carry no inline tags and require general triage — the format split is real, not cosmetic.
