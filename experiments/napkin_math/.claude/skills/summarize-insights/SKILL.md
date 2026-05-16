---
name: summarize-insights
description: Use after the napkin_math pipeline has produced parameters/bounds/scenarios/montecarlo JSON to generate a thin interpretation layer (insights.md) over the intermediary artifacts. Emits a JSON manifest, a provenance map, gate verdicts (DOOM / FRAGILE / MARGINAL / ROBUST), failure drivers, confidence and trust boundaries, scenario sanity check, and suggested next actions. The artifact is a navigation/judgment file, not a copy of the raw simulation data.
---

# Summarize napkin_math insights into a thin interpretation layer

## Overview

A thin wrapper around `experiments/napkin_math/summarize_insights.py`. The script reads the pipeline artifacts and emits `insights.md` next to them. The output is an **interpretation layer**: it tells the next reader of this directory what the simulation tested, which gates fail or pass, which inputs drive the result, which assumptions remain unvalidated, and what to inspect next. The raw distributions live in `montecarlo.json`; `insights.md` references them via the provenance map rather than reproducing them.

## When to Use

- The Monte Carlo stage has just produced `montecarlo.json` and the user wants a verdict
- The user asks "is this plan in trouble?" or "what does the simulation say?"
- After any iteration on bounds or calculations, to see how the doom signals moved

Not for: producing the simulation itself (`monte-carlo`), running scenarios (`run-scenarios`), or extracting parameters from a report.

## Workflow

1. **Locate the inputs.** Required: `parameters.json`. Optional but recommended: `bounds.json`, `scenarios.json`, `montecarlo.json`. `validation.json` and `montecarlo_settings.json` are picked up automatically from the same directory if present. The script degrades gracefully if any optional file is missing — it just omits that section. If `parameters.json` is missing, ask.

2. **Invoke the script.** Requires Python 3.11+ (no extra deps):

   ```
   /opt/homebrew/bin/python3.11 experiments/napkin_math/summarize_insights.py \
     --parameters   <path>/parameters.json \
     --bounds       <path>/bounds.json \
     --scenarios    <path>/scenarios.json \
     --montecarlo   <path>/montecarlo.json \
     [--output      <path>/insights.md]
   ```

   Default output: `<dir-of-parameters>/insights.md`. The script prints the output path on stdout.

3. **Report back.** Tell the user the output path. If the user asks for a verdict in-conversation, read `insights.md` and quote the gate-verdict rows and critical-findings bullets verbatim — don't paraphrase.

## How doom verdicts are decided

Verdicts come from the user's own threshold definitions in the Monte Carlo settings. No identifier-string or unit-string interpretation — domain-bias-free.

Each threshold has an operator (`>=`, `<=`, etc.) and a value. The user wrote the threshold because they want it to pass. The verdict is the pass probability in the simulation:

| Band | Pass probability | Verdict | Note |
|---|---|---|---|
| ≥ 80% | strong majority | **ROBUST** | passes in the strong majority of runs |
| 50–80% | uncomfortable | **MARGINAL** | passes more often than not but uncomfortably close |
| 20–50% | minority pass | **FRAGILE** | fails in the majority of runs |
| < 20% | rarely passes | **DOOM** | rarely passes under current bounds |

Any output classified DOOM or FRAGILE also gets a "bottom line" callout at the top of the report.

The script does **not** invent thresholds for outputs the user did not declare. To get a verdict on an output, declare a threshold on it in the Monte Carlo settings file.

## Audience and tone

`insights.md` is written to be consumed by the next program or process that touches this directory — a downstream pipeline stage, a planning loop, a follow-on extractor, a future invocation of this same workflow. A human can also read it, but the writing optimises for token-density of useful signal over engagement hooks. The output describes **what the file is** (an interpretation layer over the simulation artifacts); it does not label its audience.

What that means concretely:

- The file leads with a machine-readable JSON manifest. Every prose section after it is a structured form of those same signals.
- Stable retrievable section names (`## Critical findings`, `## Gate verdicts`, `## Failure drivers`, `## Suggested next actions`). No colorful or narrative-flavoured headings.
- No reader-engagement prefixes ("If you read nothing else, read this", "Stop and pay attention", "Important:"). The structural markers and verdict labels carry that weight.
- No filler sentences whose only job is to motivate the next sentence. Lead with the substantive claim.
- Keep substantive explanations (what a verdict label means, what a column shows, what makes an item belong in a section). Those are signal, not filler.
- Don't apologise for or hedge the bad news. State it.

## Writing rules — apply to the script's output AND to anything you say back to the user about the insights

These are not stylistic preferences. They are how this skill is meant to communicate.

1. **Critical findings first.** After the artifact contract, machine summary, provenance map, modelling frame, and simulation settings, the first interpretation section is `## Critical findings`. It consolidates every signal that the plan does not survive its own assumptions: DOOM and FRAGILE thresholds, scenario warnings, numbers the model could not compute, and inputs the plan does not supply at all. If nothing qualifies, the section is omitted entirely — silence is the only acceptable form of good news.

2. **No sugar-coating.** A 5% pass probability is "rarely passes under current bounds", not "shows some challenges". A base-scenario value on the wrong side of a declared threshold is "the gate fails at the plan's own central assumptions", not "may warrant further attention". Use the strongest accurate language without overclaiming epistemic certainty — never "the math says it certainly will" — but never soften the result either; if the script's wording softens a result, fix the script.

3. **No sycophancy.** Never start a paragraph with "Great plan, but..." or "The team has done strong work; one concern is...". The downstream consumer has the plan available. It does not need praise from the report.

4. **No hedging phrases.** Banned in both the script's emitted text and in conversational reporting:
   - `the honest read is`, `frankly`, `to be fair`, `in fairness`, `candidly`, `let's be real`, `look, the truth is`
   - rhetorical "I'll be honest with you" / "to put it bluntly" / "if I may"

   These imply the default mode is dishonest or evasive. State the claim directly.

5. **Hedges about data vs hedges about the speaker.** Hedges that point at the underlying simulation are fine: "the simulation shows", "based on the bounds we have", "within the assumed ranges". Hedges that point at the writer's posture are not.

6. **Quote the verdicts; don't paraphrase.** When the script emits `**DOOM** — rarely passes under current bounds`, report it as `DOOM — rarely passes under current bounds`. Don't summarise it as "this one is concerning". The verdict bands are precise and load-bearing.

## Sections in the generated insights.md

Order is deliberate. Stable section names — programmatic consumers retrieve by heading text, so the headings stay the same regardless of plan domain:

- **`# Insights: <plan name>`** — title plus a 2-line frontmatter (type, primary goal).
- **`## Artifact contract`** — declares what this file is (an interpretation layer over the simulation artifacts) and what it is not (a copy of the raw simulation data, an external feasibility proof, a probability calibration).
- **`## Machine summary`** — a JSON code block with the compact manifest: `insights_schema_version` (currently `3`), `artifact_type`, `plan_name`, `artifact_set` (`version` / `plan_slug` / `relative_dir` — the portable identifier), `source_plan_dir` (absolute path; local-only), `primary_model_result` (a structured object: `overall_risk_band` ∈ doom/fragile/marginal/viable/unknown, `basis` — a one-line disclaimer that the band reflects the worst declared gate's pass-rate band and is not a calibrated whole-plan probability, `reason`, `worst_gate`, `worst_gate_pass_rate`), `validation_status`, `simulation` (n_runs/seed/distribution_default), `primary_failed_gates`, `primary_uncertainty_drivers`, `do_not_treat_as`, `schema_notes` (allowed enums for `overall_risk_band`, `verdict`, `basis`, `threshold_basis`, plus the `primary_model_result_semantics` disclaimer). The `basis_enum` is intentionally wider than what the current pipeline emits (`report_derived`, `model_assumption`) — it reserves `report_explicit`, `report_inferred`, `external_reference`, `manual_override`, `unknown` for future provenance types. JSON, not YAML — that is intentional.
- **`## Provenance map`** — table listing every intermediary file with its role and "open when" guidance. The first row points at `extract_parameters_input.md`, then parameters/bounds/calculations/scenarios/scenario_outputs/montecarlo_settings/montecarlo/validation.
- **`## Modelling frame`** — the source plan's own statement of what the model is testing, lifted verbatim from `parameters.plan_summary.modelling_frame`.
- **`## Simulation settings`** — n_runs, seed, distribution_default, validation status.
- **`## Critical findings`** — bullets in severity order: DOOM gates, FRAGILE gates, scenario warnings, numbers the model could not compute (≥5% blank runs), still-missing inputs. Section omitted entirely when nothing qualifies.
- **`## Gate verdicts`** — every declared threshold, worst-first, with the `min` marker on aggregate gates. Columns: marker, output, condition, **threshold basis** (`report_explicit` / `report_inferred` / `model_defined` / `unknown` — derived from the corresponding key_value's `value_type`), pass rate, verdict, meaning. Includes an `### Aggregation warning` sub-section when the thresholds use incompatible units and the plan declares no `min()` aggregate.
- **`## Decision implications`** — one row per gate with verdict in DOOM/FRAGILE/MARGINAL. Five columns: Gate, Verdict, **Planning consequence** (templated by verdict), **Structural lever** (the top driver from `quartile_analysis` with the direction implied by its sign of Δ-pp), **Gate meaning** (the gate's own rationale lifted from `parameters.recommended_first_calculations[].why_first` or `derived_questions[].why_it_matters`, plus the threshold parameter the formula tests against). The Gate-meaning column surfaces plan-specific framing without inventing tactical advice; the actual plan revision (cut capacity, change a contract clause, relax a target) is for human or LLM interpretation against the source report.
- **`## Failure drivers`** — one row per failing gate (DOOM or FRAGILE): top driver from `quartile_analysis` (max abs Δ-pp) and the conditional input restriction from `required_input_thresholds` that would lift the gate to 80%. Binding-gate frequencies for aggregates appear as bullets below the table.
- **`## Missing inputs ranked by impact`** — the `missing_value_priority` table. The `Basis` column translates the bounds.json `source` label (`data` → `report_derived`, `assumption` → `model_assumption`) so it isn't mistaken for empirically observed real-world data.
- **`## Confidence and trust boundaries`** — Validated (a one-line list of `validation.json` checks_performed), Not validated (a canonical list: real-world accuracy of bounds, independence assumptions, external feasibility, factual truth of source claims), Per-output confidence (HIGH/MEDIUM/LOW grade table from `model_confidence`). The grade-table column is `Declared-source inputs` — the share of input bounds anchored in the source report's narrative; the rest are modelling assumptions. Neither is empirical real-world data.
- **`## Scenario sanity check`** — short low/base/high deterministic comparison table. Columns: `Low inputs` / `Base inputs` / `High inputs`, matching the keys in `scenarios.json`.
- **`## Suggested next actions`** — five imperatives for whatever consumes this file next. Phrased as "To answer X, lead with Y; to audit Z, open W".
- **`## Open questions for next analysis pass`** — five standing audit questions the simulation can't answer on its own (bound width/bias, gate independence, hard vs soft gates, missing-input remediation, unmodelled gates).

## Common Mistakes

| Mistake | Fix |
|---|---|
| Running before `montecarlo.json` exists | Gate verdicts, failure drivers, and the machine summary's `primary_model_result` all depend on simulation output. Run the Monte Carlo stage first. |
| Reading the markdown and paraphrasing the gate verdicts | Quote them. The cutoff bands and phrasing are deliberate. |
| Treating the machine summary as authoritative without reading the prose | The JSON manifest is a compact pointer, not a proof. The aggregation warning, trust boundaries, and failure-driver rows are load-bearing context. |
| Treating a MARGINAL verdict as good news | MARGINAL means "passes in 50–80% of runs" — that's the same as "fails up to 50% of the time". |
| Inventing a threshold to make a number look good | Thresholds reflect the user's success criteria. Don't fabricate them after the fact. |

## Reference

- Script (authoritative): `experiments/napkin_math/summarize_insights.py`
- Companion skills: `../monte-carlo/SKILL.md`, `../run-scenarios/SKILL.md`, `../generate-bounds/SKILL.md`, `../extract-parameters-from-full/SKILL.md`, `../extract-parameters-from-digest/SKILL.md`
- Example output: any `insights.md` under `experiments/napkin_math/output/<version>/<plan>/`
