---
name: monte-carlo
description: Use when the user wants Monte Carlo simulation of a PlanExe model — sampling from bounds to produce output distributions (mean/std/percentiles), threshold pass probabilities, and Pearson-correlation sensitivity rankings — given an extract-parameters JSON, a generate-bounds JSON, a generate-calculations Python module, and optional run settings
---

# Monte Carlo Simulation

## Overview

This stage is **stochastic** — it samples from bounds many times. Contrast with `run-scenarios`, which evaluates the model deterministically at three points only.

The simulation itself is performed by a Python script (`experiments/napkin_math/run_monte_carlo.py`), not by the LLM. The script imports `calculations.py`, draws samples with a seeded NumPy RNG, runs the loop, and writes `montecarlo.json`. The script is authoritative; this skill is a thin wrapper that locates inputs, builds an optional settings file, and invokes the runner.

Stage 7 of the pipeline described in `planexe_simulator/README.md`.

## When to Use

- User asks to "run Monte Carlo", "sample the bounds", "compute distributions", "estimate gate-pass probability", or "find which inputs drive uncertainty"
- User wants percentile bands (p05/p50/p95) or threshold pass rates (e.g. `P(avoided_events ≥ 10)`)
- Final stage in the pipeline; only run after `run-scenarios` already shows a sane deterministic model

Not for: regenerating any prior artifact, replacing the deterministic scenario table (use `run-scenarios`), or claiming causality from sensitivity correlations.

## Workflow

1. **Get the inputs.** Three required, one optional:
   - parameters JSON (e.g. `output/v12/parameters.json`)
   - bounds JSON (e.g. `output/v12/bounds.json`)
   - calculations Python module (e.g. `output/v12/calculations.py`)
   - **settings JSON** (optional — `n_runs`, `seed`, `distribution_default`, `outputs_of_interest`, `thresholds`, `gate_probabilities`, `correlation_groups`)

   If any required input is missing, ask. If the user wants thresholds or non-default settings, write them to a small JSON file and pass `--settings`.

2. **Invoke the runner.** Requires Python 3.11+ with NumPy:

   ```
   /opt/homebrew/bin/python3.11 experiments/napkin_math/run_monte_carlo.py \
     --parameters   <path>/parameters.json \
     --bounds       <path>/bounds.json \
     --calculations <path>/calculations.py \
     [--settings   <path>/settings.json] \
     [--output     <path>/montecarlo.json]
   ```

   Default output path is `<dir-of-parameters>/montecarlo.json`. The script prints a one-line summary (n_runs, output count, threshold count, warning count) on stdout.

3. **Report back.** Tell the user the output path and the one-line summary. If the user asks for interpretation, read the JSON, then explain — but never replace running the script with hand-computed numbers.

## What the runner does (so the LLM can describe results accurately)

The runner does **no** lexical pattern-matching on id strings, unit strings, or rationale text. Every semantic classification it needs is read verbatim from upstream-declared fields. If a required field is missing, the runner exits with `SCHEMA ERROR` and names which upstream stage to re-run.

- **Distributions per bounded variable** — driven by the bound's `sampling_discipline` field (required, declared by `generate-bounds`):
  - `"fixed"` — always returns the single pinned value
  - `"bernoulli_gate"` — Bernoulli draw with probability from `settings.gate_probabilities[id]` if set, else the bound's `default_pass_probability` (required, in `[0, 1]`). Returns `high` on pass, `low` on fail. Works for any unit — currency tranches, permit toggles, regulatory pass/fail.
  - `"integer"` — sample triangular/uniform, round to nearest integer, re-clamp to `[low, high]`
  - `"fraction"` — sample triangular/uniform, clamp to `[0, 1]`
  - `"continuous"` — sample triangular/uniform with no extra rounding or clamping beyond `[low, high]`
  - Default base distribution: triangular `(low, mode=base, high)`. `distribution_default: "uniform"` switches to uniform.
  - The bound's `non_negative: bool` (required) drives whether draws are clamped to `>= 0`.

- **Output names and units:** the runner uses `entry.output_name` and `entry.output_unit` from each `recommended_first_calculations` / `derived_questions` entry, declared by `extract-parameters`. The runner does **not** parse `formula_hint` to recover the name, and does **not** infer units from id tokens. The LLM is the single authority for both.

- **Calculation execution:** uses `inspect.signature` on each generated function to pull args from the run's input pool. Order: `recommended_first_calculations` first, then `derived_questions`. Outputs are added to the pool so later functions can depend on them. Missing dependencies / non-finite results / exceptions skip the run for that output (one aggregated warning, not per-run noise).

- **Sensitivity:** Pearson correlation between each sampled input and each summarized output, top 5 by `|correlation|`. Only inputs that vary AND are used directly or indirectly by the output AND have ≥20 finite paired samples are considered. `NaN` correlations become `null` + warning.

- **Thresholds:** operators `>  >=  <  <=  ==  !=` only. Probability = success_count / valid_count. `valid_count == 0` → probability `null`.

- **By default variables are independent.** `correlation_groups` is currently parsed but not yet implemented in the runner; if the user passes them, the script will accept the setting and ignore correlation enforcement. Update the runner if correlation is actually needed.

## Required upstream schema

For the runner to accept the artifacts, the upstream LLM stages must have emitted:

- **Each `bounds.json` entry** — `sampling_discipline` (string, one of `fixed | bernoulli_gate | integer | fraction | continuous`), `non_negative` (bool), `default_pass_probability` (number in `[0, 1]` when `sampling_discipline == "bernoulli_gate"`, otherwise `null`).
- **Each `recommended_first_calculations` and `derived_questions` entry with non-null `formula_hint`** — `output_name` (snake_case id of the computed value) and `output_unit` (unit string).

If any required field is missing, the runner exits with `SCHEMA ERROR: <message>. Re-run <stage>.` and exit code 2. Fix the upstream artifact and re-run; the runner has no fallback path that re-guesses any of these.

## Output Shape

```json
{
  "valid": true,
  "plan_summary": { "plan_name": "...", "plan_type": "..." },
  "settings": { "n_runs": 10000, "seed": 12345, "distribution_default": "triangular" },
  "outputs": {
    "<output_id>": {
      "unit": "...",
      "count": ..., "missing_count": ...,
      "mean": ..., "std": ...,
      "min": ..., "p05": ..., "p25": ..., "p50": ..., "p75": ..., "p95": ..., "max": ...
    }
  },
  "thresholds": {
    "<output_id>": { "operator": ">=", "value": ..., "success_count": ..., "valid_count": ..., "probability": ... }
  },
  "sensitivity": {
    "<output_id>": { "top_inputs": [ { "id": "...", "correlation": ... } ] }
  },
  "warnings": [
    { "stage": "monte_carlo", "run": null, "calculation": null, "message": "...", "severity": "WARN" }
  ]
}
```

JSON forbids `NaN`/`Infinity` — the runner writes `null` and adds a warning. Identical inputs + identical seed produce a byte-identical output file.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Hand-rolling stats inside the LLM response | Run the script. Never produce summary numbers without it. |
| Producing low/base/high tables instead of distributions | Wrong stage — that's `run-scenarios`. This one samples. |
| Claiming causality from a high Pearson correlation | Sensitivity ≠ causation; only describe directional strength. |
| Treating "0% probability" as impossible | It means 0 of `valid_count` samples passed; widen bounds or revisit the model. |
| Running with `python3` when only `python3.11` has NumPy | Use the explicit interpreter path. |

## Reference

- Runner (authoritative implementation): `experiments/napkin_math/run_monte_carlo.py`
- Pipeline overview: `../../README.md`, Stage 7
- Companion skills: `../extract-parameters/SKILL.md`, `../validate-parameters/SKILL.md`, `../generate-bounds/SKILL.md`, `../generate-calculations/SKILL.md`, `../run-scenarios/SKILL.md`
- Synthetic fixture exercising every `sampling_discipline` (used as the runner smoke test):
  - `experiments/napkin_math/tests/fixtures/smoke/parameters.json`
  - `experiments/napkin_math/tests/fixtures/smoke/bounds.json`
  - `experiments/napkin_math/tests/fixtures/smoke/calculations.py`
