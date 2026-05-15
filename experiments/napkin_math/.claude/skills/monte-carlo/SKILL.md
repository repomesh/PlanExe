---
name: monte-carlo
description: Use when the user wants Monte Carlo simulation of a PlanExe model — sampling from bounds to produce output distributions (mean/std/percentiles), threshold pass probabilities, and Pearson-correlation sensitivity rankings — given an extract-parameters JSON, a generate-bounds JSON, a generate-calculations Python module, and optional run settings
---

# Monte Carlo Simulation

## Overview

Wraps the Monte Carlo system prompt at `system-prompt.txt` (next to this file) and applies it to the same trio of artifacts that `run-scenarios` consumes, plus an optional settings object. Output is a strict JSON document with per-output summary statistics, threshold pass probabilities, and a sensitivity ranking of input drivers.

This stage is **stochastic** — it samples from bounds many times. Contrast with `run-scenarios`, which evaluates the model deterministically at three points only.

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

   If any required input is missing, ask. Defaults for settings are listed below.

2. **Read `system-prompt.txt`** (sibling of this SKILL.md). Sampling rules, distribution choices, threshold semantics, and sensitivity computation are authoritative.

3. **Read all three required artifacts** plus the settings if provided.

4. **Build sampled input pools** per the system prompt's selection rules. For each variable with bounds, choose a distribution (triangular default; uniform if requested; Bernoulli for binary gate-dependent monetary variables; clamp/round for fraction and integer-count units).

5. **Run the simulation** for `n_runs`. Execute calculation functions in the same order as `run-scenarios` (recommended_first then derived_questions). Record finite results; count and warn (in aggregate) on `NaN`/`Infinity`/exceptions/missing dependencies.

6. **Compute summary stats, threshold probabilities, sensitivity** — emit per the output shape.

7. **Output destination.** Default: write to `<dir-of-parameters>/montecarlo.json` next to the inputs. Print the file path back, plus a one-line summary (n_runs, output count, threshold count, warning count).

## Settings defaults (re-stated for emphasis)

| Setting | Default | Bounds |
|---|---|---|
| `n_runs` | 10000 | int in [100, 100000] |
| `seed` | 12345 | int |
| `distribution_default` | `"triangular"` | `triangular` or `uniform` |
| `outputs_of_interest` | `[]` (= summarize all computed outputs) | list of output ids |
| `thresholds` | `{}` | id → `{operator, value}` with operator in `> >= < <= == !=` |
| `gate_probabilities` | `{}` | id → pass-probability for binary gate-dependent monetary variables; default 0.5 if absent (with warning) |
| `correlation_groups` | `[]` | list of `{ids, direction: positive | negative}` |

## Distribution rules (the most important ones)

- **Default**: triangular `(low, mode=base, high)`
- **Fixed** (`low == base == high`): always return that value
- **Binary gate-dependent monetary** (unit is monetary, `low == 0`, `base == high`, rationale mentions binary/gate/release/etc.): Bernoulli with pass-probability from `gate_probabilities` (default 0.5 + warning)
- **Integer counts** (people, kits, centers, days, etc.): sample continuously then round
- **Fractions**: clamp to `[0, 1]`
- **Non-negative quantities** (people, money, counts, rates, events, capacities): clamp to `≥ 0`
- Never sample outside `[low, high]`

By default variables are **independent**. Don't invent correlations.

## Output Shape (re-stated for emphasis — see system prompt for full detail)

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

Sensitivity = Pearson correlation between each sampled input and each summarized output, top 5 by `|correlation|`. JSON forbids `NaN`/`Infinity` — write `null` and warn.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Wrapping output in ```` ```json ```` fences | Raw JSON only |
| Outputting per-run sampled rows | Spec forbids it; only summary stats are emitted |
| Producing low/base/high tables instead of distributions | Wrong stage — that's `run-scenarios`. This one samples |
| One warning per failed run instead of one aggregated | Aggregate by failure type; the spec explicitly forbids per-run noise |
| Sampling outside `[low, high]` | All distributions must respect the bounds |
| Defaulting binary gate variables to 0.5 silently | Use 0.5, but emit a warning naming the variable |
| Inventing correlation between variables not in `correlation_groups` | Independence is the default; never invent |
| Claiming causality from a high Pearson correlation | Sensitivity ≠ causation; spec forbids the claim |
| Computing sensitivity for inputs that don't vary (e.g. fixed values, constants) | Drop them from the ranking |
| Writing `Infinity` / `NaN` into JSON | Write `null` and warn — JSON forbids both |

## Reference

- System prompt (authoritative): `system-prompt.txt`
- Pipeline overview: `../../README.md`, Stage 7
- Companion skills: `../extract-parameters/SKILL.md`, `../validate-parameters/SKILL.md`, `../generate-bounds/SKILL.md`, `../generate-calculations/SKILL.md`, `../run-scenarios/SKILL.md`
- Example input set for testing (all from the same run):
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v12/parameters.json`
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v12/bounds.json`
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v12/calculations.py`
