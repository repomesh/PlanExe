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

- **Distributions per bounded variable:**
  - Default: triangular `(low, mode=base, high)`
  - `distribution_default: "uniform"` switches to uniform
  - **Fixed** (`low == base == high`): always returns that value
  - **Binary gate-dependent monetary** (currency unit, `low == 0`, `base == high`, rationale mentions `binary | gate | release | tranche | pass | fail | withheld | conditional`): Bernoulli — use `gate_probabilities[id]` if set, else 0.5 with a warning
  - **Integer counts** (unit token in `people | buyers | customers | households | units | kits | months | days | hours | events | …`, but NOT `_per_` / `per_` / `_rate`): sample continuously, then round, then re-clamp to bounds
  - **Fractions** (`unit == "fraction"`): clamp to `[0, 1]`
  - **Non-negative**: clamp to `≥ 0`
  - Never samples outside `[low, high]`

- **Calculation execution:** uses `inspect.signature` on each generated function to pull args from the run's input pool. Order: `recommended_first_calculations` first, then `derived_questions`. Output name is the LHS of `formula_hint`, falling back to entry `id`. Outputs are added to the pool so later functions can depend on them. Missing dependencies / non-finite results / exceptions skip the run for that output (one aggregated warning, not per-run noise).

- **Sensitivity:** Pearson correlation between each sampled input and each summarized output, top 5 by `|correlation|`. Only inputs that vary AND are used directly or indirectly by the output AND have ≥20 finite paired samples are considered. `NaN` correlations become `null` + warning.

- **Thresholds:** operators `>  >=  <  <=  ==  !=` only. Probability = success_count / valid_count. `valid_count == 0` → probability `null`.

- **By default variables are independent.** `correlation_groups` is currently parsed but not yet implemented in the runner; if the user passes them, the script will accept the setting and ignore correlation enforcement. Update the runner if correlation is actually needed.

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
- Example input set for testing:
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v23/20260215_nuuk_clay_workshop/parameters.json`
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v23/20260215_nuuk_clay_workshop/bounds.json`
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v23/20260215_nuuk_clay_workshop/calculations.py`
