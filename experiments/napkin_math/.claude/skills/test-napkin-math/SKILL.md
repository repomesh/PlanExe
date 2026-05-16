---
name: test-napkin-math
description: Use after any change under experiments/napkin_math/ or to the upstream skill prompts that feed into it (extract-parameters, extract-parameters-from-digest, generate-bounds, generate-calculations, run-scenarios, monte-carlo). Runs the smoke-test suite and reports pass/fail. Invoke before declaring napkin-math work done.
---

# Test the napkin_math experiment

## Overview

A single-shot smoke check for the napkin_math experiment. The test logic lives in `experiments/napkin_math/tests/run_smoke.py`; this skill is a thin wrapper that invokes the script, parses its output, and reports a one-line summary.

Covers the Monte Carlo runner (end-to-end, determinism, Bernoulli arithmetic, sensitivity ranking), the strict-schema fail-fast paths (each required field individually), `prepare_extract_input.py` import sanity, and the `compress_report_section` pytest suite.

## When to Use

- After any edit to:
  - `experiments/napkin_math/run_monte_carlo.py`
  - `experiments/napkin_math/prepare_extract_input.py`
  - `experiments/napkin_math/tests/fixtures/smoke/*`
  - `worker_plan/worker_plan_internal/parameter_extraction/compress_report_section.py`
  - any system-prompt.txt / SKILL.md under `experiments/napkin_math/.claude/skills/{extract-parameters,extract-parameters-from-digest,generate-bounds,generate-calculations,run-scenarios,monte-carlo}/` that touches the artifact schema
- Before declaring any napkin_math change "done" — even if the change looks self-contained, the schema is tightly coupled across stages
- When the user asks "did I break anything?" or "run the napkin_math tests"

Not for: end-to-end LLM-driven runs of the extract-parameters skills against real reports (those require an LLM in the loop and are out of scope here).

## Workflow

1. **Invoke the runner.** Requires Python 3.11+ with NumPy and pytest installed:

   ```
   /opt/homebrew/bin/python3.11 experiments/napkin_math/tests/run_smoke.py
   ```

   Override the interpreter with `NAPKIN_TEST_PYTHON=<path>` if the default isn't available.

2. **Read the script's stdout.** It prints one section per check with individual `ok` / `FAIL` lines, then a final summary:

   ```
   SUMMARY: 7/7 checks passed
   ALL GREEN
   ```

   Exit code is `0` on full pass, `1` on any failure.

3. **Report back to the user.** On success: one line ("All 7 napkin_math smoke checks passed."). On failure: list the failing checks with the detail printed by the runner, and point at the specific file or schema field implicated.

## What the seven checks cover

| Check | What it verifies |
|---|---|
| `end_to_end` | Runner consumes the synthetic fixture, emits both expected outputs, zero warnings |
| `determinism` | Two runs with the same seed produce byte-identical JSON |
| `bernoulli_arithmetic` | Mean of `total_budget_with_gate_inr` ≈ `1,000,000 + 0.6 * 250,000` within ±5,000 |
| `sensitivity_ranking` | Bernoulli gate is the sole driver of its dependent output (correlation == 1.0); two-input convert sensitivity has both inputs |
| `schema_errors` | Each required schema field (`sampling_discipline`, `non_negative`, `default_pass_probability` for bernoulli_gate, `output_name`, `output_unit`) triggers a `SCHEMA ERROR` exit code 2 with a message naming the upstream stage to re-run |
| `prepare_extract_input_imports` | `prepare_extract_input.py` imports cleanly and exposes `build_combined_digest` |
| `compress_pytest` | The pytest suite for `compress_report_section.py` passes (13 tests) |

## Common Mistakes

| Mistake | Fix |
|---|---|
| Skipping the check because "the diff is tiny" | The schema is tightly coupled across five skills + the runner. A tiny change in one prompt can break the runner's strict validation. Always run it. |
| Reporting "tests pass" without running the script | If you didn't see `ALL GREEN`, you didn't pass. |
| Running with `python3` instead of `python3.11` | NumPy and the worker_plan tests live in the 3.11 env. Use the explicit path or set `NAPKIN_TEST_PYTHON`. |
| Treating a `compress_pytest` failure as unrelated | The compressor is part of the napkin_math experiment; if its tests break, the digest produced by `prepare_extract_input.py` is suspect. |
| Editing fixtures to make tests pass | Fixtures encode the contract. If a fixture needs to change, the schema or the runner changed for a real reason — update both consciously and re-justify each touched check. |

## Reference

- Test runner: `experiments/napkin_math/tests/run_smoke.py`
- Synthetic fixture: `experiments/napkin_math/tests/fixtures/smoke/`
- Monte Carlo runner under test: `experiments/napkin_math/run_monte_carlo.py`
- Companion skills (consumers of the same schema): `../extract-parameters/SKILL.md`, `../extract-parameters-from-digest/SKILL.md`, `../generate-bounds/SKILL.md`, `../generate-calculations/SKILL.md`, `../run-scenarios/SKILL.md`, `../monte-carlo/SKILL.md`
