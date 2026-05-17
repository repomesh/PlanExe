---
name: validate-parameters
description: Use after the napkin_math pipeline has produced parameters.json (from extract-parameters-from-digest or extract-parameters-from-full) to validate it against the 16 structural checks the rest of the pipeline assumes. Writes validation.json next to parameters.json. Deterministic Python — no LLM call.
---

# Validate napkin_math parameters.json

## Overview

A thin wrapper around `experiments/napkin_math/validate_parameters.py`. The script reads `parameters.json` and emits `validation.json` next to it. Output shape is what `summarize_assessment.py` consumes (named `checks_performed` list + per-violation `rule_id`/`severity`/`path`/`message`/`suggested_fix`).

This replaces the older LLM-driven `validate-parameters` skill, which was written against an earlier schema and rejected the `output_name`/`output_unit` fields the digest extractor is required to emit. The Python validator runs in milliseconds, costs no tokens, and is deterministic.

## When to Use

- The extractor (digest or full) has just produced `parameters.json` and the pipeline needs `validation.json` before running scenarios or Monte Carlo
- The user asks to "validate", "check", or "lint" a parameters file
- After hand-editing `parameters.json`, to confirm the result is still structurally valid

Not for: regenerating the parameters (use `extract-parameters-from-digest` or `extract-parameters-from-full`), generating bounds, or running calculations.

## Workflow

1. **Get the parameters path.** If the user did not provide one, ask. Do not guess.

2. **Invoke the script.** Requires Python 3.11+ (no extra deps):

   ```
   /opt/homebrew/bin/python3.11 experiments/napkin_math/validate_parameters.py \
     --parameters <path>/parameters.json \
     [--output    <path>/validation.json]
   ```

   Default output: `<dir-of-parameters>/validation.json`. Exit code 0 on `valid: true`, 1 on validation errors, 2 on JSON parse failure. The script prints the output path on stdout.

3. **Report back.** Tell the user the output path, the verdict (`valid` / `INVALID`), and the error count. If there are violations, quote the first few `rule_id` + `message` pairs verbatim. Don't paraphrase the verdict — the rule ids are how downstream tooling routes the next step.

## The 16 checks

| Check | Severity bias | What it checks |
|---|---|---|
| `json_parse` | ERROR | the file parses as JSON (failure handled with a json_parse violation) |
| `top_level_structure` | ERROR | `plan_summary` + four arrays present |
| `required_fields` | ERROR | each entry carries its required keys |
| `array_length_caps` | ERROR | ≤8 key_values, ≤5 derived_questions / missing_values_to_estimate / recommended_first_calculations |
| `global_id_uniqueness` | ERROR | ids unique across all four arrays |
| `snake_case_ids` | ERROR | ids match `^[a-z][a-z0-9_]*$` |
| `depends_on_declared` | ERROR | every id in `depends_on` matches a declared `id` or `output_name` |
| `formula_rhs_declared` | ERROR | every snake_case identifier on the RHS of `formula_hint` is declared (or is the entry's own `output_name`); built-ins like `min`/`max` are exempt |
| `fraction_value_range` | ERROR | `unit == "fraction"` ⇒ value in `[0, 1]` or null |
| `comment_word_caps` | ERROR | key_value `comment` ≤25 words |
| `source_text_word_caps` | ERROR | key_value `source_text` ≤20 words |
| `output_name_present_when_formula_hint` | ERROR | non-empty `formula_hint` ⇒ `output_name` not null |
| `output_unit_present_when_formula_hint` | ERROR | non-empty `formula_hint` ⇒ `output_unit` not null |
| `no_dead_end_variables` | ERROR | every key_value and missing_value is consumed (transitively) by some calculation |
| `threshold_friendly_naming` | WARN | output_names ending in `_gap` / `_deficit` / `_shortfall` are flagged because they read ambiguously under a `>= 0` / `<= 0` threshold |
| `shared_pool_legitimacy` | (no-op) | listed in `checks_performed` for completeness; enforcement is upstream in the extractor's system prompt (requires reading source narrative to verify pool legitimacy, which is not a structural check) |

`valid` is `true` iff `error_count == 0`. WARN-level findings do not invalidate the file.

## Output shape

```json
{
  "valid": true,
  "error_count": 0,
  "warn_count": 0,
  "violations": [],
  "summary": {
    "counts": {"key_values": 8, "derived_questions": 3, "missing_values_to_estimate": 4, "recommended_first_calculations": 5},
    "rule_id_breakdown": {},
    "checks_performed": ["json_parse", "top_level_structure", ...]
  }
}
```

The `summary.checks_performed` list is what `summarize_assessment.py` surfaces as the "Validated" line under `## Confidence and trust boundaries`. Keep it as the authoritative list of what the validator actually ran.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running before `parameters.json` exists | Run the extractor first (`extract-parameters-from-digest` or `extract-parameters-from-full`). |
| Treating WARN findings as blocking | They are not. `valid` is set only by ERROR-level findings. |
| Editing `parameters.json` by hand to silence a `no_dead_end_variables` ERROR | The right fix is usually to add a calculation that consumes the variable, not to drop the variable. Re-validate after either change. |
| Editing `parameters.json` to silence a `threshold_friendly_naming` WARN | If the output is actually threshold-tested, rename and flip the formula sign. If it isn't, the WARN is just advisory. |

## Reference

- Script (authoritative): `experiments/napkin_math/validate_parameters.py`
- Companion skills: `../extract-parameters-from-digest/SKILL.md`, `../extract-parameters-from-full/SKILL.md`, `../generate-bounds/SKILL.md`, `../monte-carlo/SKILL.md`, `../summarize-assessment/SKILL.md`
- Example output: any `validation.json` under `experiments/napkin_math/output/<version>/<plan>/`
