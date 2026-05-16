---
name: run-scenarios
description: Use when the user wants to compute deterministic low/base/high scenario outputs for a PlanExe model — given an extract-parameters-from-full JSON, a generate-bounds JSON, and a generate-calculations Python module — producing a scenario result JSON with inputs, outputs, comparison spread, and warnings
---

# Run Low/Base/High Scenarios

## Overview

Wraps the scenario-runner system prompt at `system-prompt.txt` (next to this file) and applies it to the **three** artifacts produced by earlier pipeline stages: a validated parameter JSON, a bounds JSON, and a generated Python calculations module. Output is a strict JSON document with one input pool and one output set per scenario (`low`, `base`, `high`), plus a comparison block summarising spread per computed output.

This stage is **deterministic** — it does not sample distributions. Monte Carlo is a separate later stage.

Stage 6 of the pipeline described in `planexe_simulator/README.md`.

## When to Use

- User asks to "run scenarios", "compute low/base/high outputs", "produce a scenario table", or "see how outputs move with the bounds"
- Pipeline step between `generate-bounds` / `generate-calculations` (both clean) and `monte-carlo`
- User wants a first sanity check that the deterministic model behaves sensibly before sampling

Not for: regenerating any prior artifact (use the corresponding earlier skill), Monte Carlo or distribution sampling (later stage), or critiquing the plan as a whole.

## Workflow

1. **Get the three input paths.** If any are missing, ask. Do not guess. Conventional layout (matches `output/<version>/`):
   - parameters JSON (e.g. `output/v12/parameters.json`)
   - bounds JSON (e.g. `output/v12/bounds.json`)
   - calculations Python module (e.g. `output/v12/calculations.py`)
2. **Read `system-prompt.txt`** (sibling of this SKILL.md). Its scenario semantics, input-pool construction, function-execution order, and output shape are authoritative.
3. **Read all three input artifacts.**
4. **Build the three input pools** (`low`, `base`, `high`) per the system prompt's selection rules.
5. **Run the calculation functions** in input order: `recommended_first_calculations` first, then `derived_questions`. Skip-and-warn on missing dependencies, `NotImplementedError` (for `P(...)` stubs), `inf`, or `NaN`. Do not abort the whole run.
6. **Emit the scenario JSON** per the system prompt's output shape.
7. **Output destination.** Default: write to `<dir-of-parameters>/scenarios.json` next to the input. Print the file path back, plus a one-line summary (output count, warning count).

## What gets supplied vs computed (re-stated for emphasis)

| Variable type | Source for `low/base/high` |
|---|---|
| `key_value` with bounds entry | bounds value for that scenario |
| `key_value` with non-null value, no bounds | the same `value` for all three scenarios |
| `key_value` with null value, no bounds | unresolved → may trigger missing-dependency warning |
| `missing_value_to_estimate` with bounds entry | bounds value for that scenario |
| Output of a generated function | computed from current scenario input pool |

The scenario names refer to the **input bounds**, not "good vs bad" outcomes. High cost is bad; high effectiveness is good. Don't rename to optimistic/pessimistic.

## Output Shape (re-stated for emphasis — see system prompt for full detail)

```json
{
  "valid": true,
  "plan_summary": { "plan_name": "...", "plan_type": "..." },
  "scenarios": {
    "low":  { "inputs": {...}, "outputs": {...} },
    "base": { "inputs": {...}, "outputs": {...} },
    "high": { "inputs": {...}, "outputs": {...} }
  },
  "comparison": {
    "outputs": {
      "<output_id>": {
        "low": ..., "base": ..., "high": ...,
        "unit": "...",
        "spread_ratio": <high/low or null>,
        "spread_absolute": <high-low or null>
      }
    }
  },
  "warnings": [
    { "stage": "run_scenarios", "scenario": "low", "calculation": "people_protected",
      "message": "Missing dependency 'voucher_install_success_rate'.", "severity": "WARN" }
  ]
}
```

Numeric JSON rules: no `NaN`, no `Infinity` — write `null` and add a warning. No currency symbols, no thousands separators. Don't round unless needed for valid JSON.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Wrapping output in ```` ```json ```` fences | Raw JSON only |
| Renaming scenarios to "optimistic / realistic / pessimistic" | Keep `low / base / high` — those refer to bounds, not outcomes |
| Aborting on first missing dependency or `inf` result | Skip the affected function for that scenario; emit a WARN; keep the run going |
| Inventing values for `null` key_values that have no bounds | Don't. Mark the dependent calculation as missing |
| Computing percentage change in `comparison` | Spec is `spread_ratio = high/low` and `spread_absolute = high-low` only |
| Running Monte Carlo or sampling | This stage is deterministic; sampling lives in `monte-carlo` |
| Ignoring `NotImplementedError` from `P(...)` stubs | Skip, emit a WARN noting the formula needs `monte-carlo` |
| Writing `Infinity` or `NaN` into JSON | JSON forbids both — use `null` and warn |
| Producing a markdown table or prose explanation | JSON only; the spec forbids prose |

## Reference

- System prompt (authoritative): `system-prompt.txt`
- Pipeline overview and "scenario purpose" list: `../../README.md`, Stage 6
- Companion skills: `../extract-parameters-from-full/SKILL.md`, `../validate-parameters/SKILL.md`, `../generate-bounds/SKILL.md`, `../generate-calculations/SKILL.md`
- Example input set for testing (all from the same run):
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v12/parameters.json`
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v12/bounds.json`
  - `/Users/neoneye/git/neoneye_lab/planexe_simulator/output/v12/calculations.py`
