---
name: generate-bounds
description: Use when the user wants to generate low/base/high assumption ranges (bounds) for missing or uncertain variables in a validated extract-parameters JSON, in preparation for deterministic scenarios or Monte Carlo
---

# Generate Bounds for Extracted Parameters

## Overview

Wraps the bounds-estimator system prompt at `system-prompt.txt` (next to this file) and applies it to a parameter JSON produced by `extract-parameters` (and ideally already passed `validate-parameters`). Output is a strict JSON object keyed by variable id, with `low / base / high / unit / rationale / source` for every variable that needs an assumption range.

Stage 4 of the pipeline described in `planexe_simulator/README.md`.

## When to Use

- User asks to "generate bounds", "estimate ranges", "add low/base/high", or "prepare for scenarios" given an extract-parameters JSON
- User wants to fill in assumptions for `missing_values_to_estimate` and uncertain `key_values` before running deterministic scenarios or Monte Carlo
- Pipeline step between `validate-parameters` (passes clean) and `generate-calculations` / `run-scenarios`

Not for: regenerating the parameter JSON (use `extract-parameters`), validating the JSON (use `validate-parameters`), or producing Python code (use `generate-calculations`).

## Workflow

1. **Get the input JSON path.** If the user did not provide one, ask. Do not guess.
2. **Read `system-prompt.txt`** (sibling of this SKILL.md). Its selection rules and spread heuristics are authoritative.
3. **Read the parameter JSON.** Assume it has already passed `validate-parameters`; if it visibly hasn't, tell the user and offer to validate first.
4. **Produce the bounds JSON** per the system prompt.
5. **Output destination.** Default: print the JSON to chat. If the user asks for a file, write to the path they specify. Suggested default file path: `<input-basename>.bounds.json` next to the input.

## Selection Rules (re-stated for emphasis — see system prompt for full detail)

Generate one bounds entry for every id that meets ANY of:

- it appears in `missing_values_to_estimate`
- it is a `key_value` with `value_type ∈ {inferred, missing_but_needed}`
- it is a `key_value` with `value == null`
- it is a `key_value` with `uncertainty == high`
- it is a `key_value` with `uncertainty == medium` AND `modelling_priority ∈ {critical, high}`

Skip: explicit/derived `key_values` with low uncertainty, `derived_questions`, `recommended_first_calculations`, and formula LHS-only outputs that are not declared as inputs.

## Spread by Uncertainty

| Uncertainty | Spread around base |
|---|---|
| low | ±10–20% |
| medium | ±25–50% |
| high | ≥±50%, up to a 2–5× factor when genuinely speculative |

Always `low ≤ base ≤ high`. Fractions stay in `[0, 1]`. Counts of discrete things (people, kits, centers, months) use integer bounds.

## Output Shape

```json
{
  "<variable_id>": {
    "unit": "fraction",
    "low": 0.10,
    "base": 0.20,
    "high": 0.30,
    "rationale": "Short, ≤30 words, one or two sentences.",
    "source": "data" | "assumption",
    "sampling_discipline": "fraction",
    "non_negative": true,
    "default_pass_probability": null
  }
}
```

Top-level is a single object keyed by variable id. Order keys roughly by importance (critical → high → medium → remaining missing values). Use `"source": "data"` only when the range is anchored in a citable real-world reference for similar programs; otherwise `"assumption"`.

### Sampling-discipline tag

Each entry MUST carry a `sampling_discipline` chosen by the LLM based on the variable's nature. Downstream consumers (run-scenarios, monte-carlo runner) read this tag directly and do not pattern-match on unit strings — so the LLM is the single authority for this classification.

| Value | Meaning | Downstream behavior |
|---|---|---|
| `"fixed"` | `low == base == high`; genuinely pinned | Always return that value |
| `"bernoulli_gate"` | Binary pass/fail (staged funding, permit toggle, regulatory pass, conditional release). Requires `default_pass_probability` ∈ [0, 1] | Bernoulli draw; low on fail, high on pass |
| `"integer"` | Countable units — people, households, sites, kits, days, … | Sample continuously, round, re-clamp to `[low, high]` |
| `"fraction"` | Bounded fraction in `[0, 1]` | Clamp draws to `[0, 1]` |
| `"continuous"` | Real-valued; no rounding, no extra clamping beyond `[low, high]` | Plain triangular/uniform draw |

`non_negative` is independent of discipline: set `true` when the variable cannot legitimately go below zero (continuous monetary amounts, counts, capacities); set `false` only when negative values are physically meaningful (a delta or net change variable).

`default_pass_probability` is required (a number in `[0, 1]`) when `sampling_discipline == "bernoulli_gate"` and MUST be `null` for every other discipline.

If no variable needs bounds, return `{}`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Bounding every variable, including known explicit facts | Skip explicit/derived key_values with low uncertainty — they are facts, not assumptions |
| Returning `low == base == high` for variables with real uncertainty | Give a real range; identical bounds are only for genuinely pinned KPI commitments |
| Wrapping output in ```` ```json ```` fences | Raw JSON only |
| Including `derived_questions` or `recommended_first_calculations` ids | Those are outputs/questions, not bounded inputs |
| Inventing ids that are not declared in the parameter JSON | Every key must correspond to a declared id in `key_values` or `missing_values_to_estimate` |
| Picking fractions outside `[0, 1]` (e.g. base 1.5 for a rate) | Clamp to the unit's natural range |
| Ignoring the parameter's `uncertainty` and giving everything the same ±20% spread | Anchor the spread on the parameter's stated uncertainty level |

## Reference

- System prompt (authoritative): `system-prompt.txt`
- Pipeline overview and "what needs bounds" list: `../../README.md`, Stage 4
- Companion skills: `../extract-parameters/SKILL.md`, `../validate-parameters/SKILL.md`
- Example input for testing: `/tmp/extract-params-heatwave-v8.json` (passes validate-parameters with `valid: true`)
