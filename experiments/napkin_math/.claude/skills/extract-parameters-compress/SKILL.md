---
name: extract-parameters-compress
description: Use when the user wants to extract parameters from a *compressed* PlanExe digest (the markdown produced by experiments/napkin_math/prepare_extract_input.py) instead of the full PlanExe HTML report
---

# Extract Parameters from a Compressed PlanExe Digest

## Overview

A drop-in alternative to `extract-parameters` that reads the small, tagged
markdown digest produced by `prepare_extract_input.py` (see
`experiments/napkin_math/prepare_extract_input.py`) rather than the full
PlanExe HTML report.

The compressed digest concatenates four per-section digests
(selected_scenario, review_plan, premortem, expert_criticism). Each bullet
already carries inline epistemic tags of the form
`[<source_status> | e=N r=N | quote: verified|unverified]`. The system prompt
at `system-prompt.txt` explains how to read them.

Output schema and hard limits are identical to `extract-parameters`, so the
two skills can be compared head-to-head on the same plan.

## When to Use

- The user has run `prepare_extract_input.py` against a PlanExe sample and
  wants parameters extracted from the resulting digest
- The user is comparing whether the compressed pipeline produces better
  parameters than feeding the full HTML report

For plain PlanExe HTML/text reports, use `extract-parameters` instead.

## Workflow

1. **Get the digest path.** Usually
   `experiments/napkin_math/output/<plan-name>/extract_parameters_input.md`.
   If the user did not provide one, ask. Do not guess.
2. **Read `system-prompt.txt`** (sibling of this SKILL.md). Treat it as the
   authoritative extraction instructions.
3. **Read the digest file.** It will be a few KB — much smaller than a raw
   PlanExe report.
4. **Produce the JSON** following the schema at the end of `system-prompt.txt`.
   Map the digest's inline `source_status` tags to the JSON `value_type`
   field: `[explicit]` → `explicit`, `[derived]` → `derived`,
   `[inferred]` → `inferred`, `[missing]` items belong in
   `missing_values_to_estimate`, `[stress_test]` items are
   scenario-stress inputs (not baseline `key_values`).
5. **Output destination.** Default: print JSON to the chat. If the user
   asks for a file, write to the path they specify. Default suggestion:
   `<digest-basename>.parameters.json` next to the digest.

## Hard Rules (re-stated for emphasis)

- **JSON only.** No markdown fences, no prose, no explanation.
- **Use the digest's tags.** Prefer `[explicit] + quote: verified` items for
  baseline `key_values`. Treat `quote: unverified` items with extra
  scepticism. `[missing]` items belong in `missing_values_to_estimate`.
  `[stress_test]` items are downside-scenario inputs, not plan facts.
- **Percentages as fractions** between 0 and 1 with `unit: "fraction"`.
- **No invented ids in `formula_hint`** — every variable must be declared
  in `key_values`, `missing_values_to_estimate`, or the object's own
  `depends_on`.

## Reference

- System prompt (authoritative): `system-prompt.txt`
- Producer of the input digest: `experiments/napkin_math/prepare_extract_input.py`
- Parallel skill for full HTML reports: `../extract-parameters/SKILL.md`
- Background: `docs/proposals/137-section_filtering_for_parameter_extraction.md`,
  `docs/proposals/139-compress-for-monte-carlo.md`
