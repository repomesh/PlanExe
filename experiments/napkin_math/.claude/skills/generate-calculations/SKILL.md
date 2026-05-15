---
name: generate-calculations
description: Use when the user wants to turn a validated extract-parameters JSON into a Python module of deterministic functions implementing the formula_hint expressions for downstream scenario runs and Monte Carlo
---

# Generate Deterministic Calculations from Extracted Parameters

## Overview

Wraps the calculation-generator system prompt at `system-prompt.txt` (next to this file) and applies it to a parameter JSON produced by `extract-parameters` (validated by `validate-parameters`). Output is a single Python module of small, pure functions — one per `formula_hint` declared in `recommended_first_calculations` and `derived_questions`.

Stage 5 of the pipeline described in `planexe_simulator/README.md`.

## When to Use

- User asks to "generate calculations", "emit Python", "materialise the formulas", or "build the deterministic functions" given a validated parameter JSON
- Pipeline step between `validate-parameters` (passes clean) / `generate-bounds` and `run-scenarios`
- User wants importable Python functions ready for scenario tables

Not for: regenerating the parameter JSON (use `extract-parameters`), validating it (use `validate-parameters`), producing low/base/high ranges (use `generate-bounds`), or running scenarios (use `run-scenarios`).

## Workflow

1. **Get the input JSON path.** If the user did not provide one, ask. Do not guess.
2. **Read `system-prompt.txt`** (sibling of this SKILL.md). Its function-shape, division-guard, and module-structure rules are authoritative.
3. **Read the parameter JSON.** Assume it has already passed `validate-parameters`; if it visibly hasn't, tell the user and offer to validate first.
4. **Produce the Python module** per the system prompt.
5. **Output destination.** Default: write to a file. Suggested default path: `<input-basename>.calculations.py` next to the input. Print the file path back, plus a one-line summary (function count, any `# skipped` lines, any TODO stubs for `P(...)` notation).

## What gets a function

| Input list | Action |
|---|---|
| `recommended_first_calculations` | one function each |
| `derived_questions` | one function each |
| `key_values` | not converted — these are caller-supplied inputs |
| `missing_values_to_estimate` | not converted — supplied via bounds at scenario time |

Skip an entry whose `formula_hint` is null, empty, or unparseable. Replace with a `# skipped: <id> -- <reason>` comment.

## Function shape (re-stated for emphasis — see system prompt for full detail)

```python
def x(a: float, b: float) -> float:
    return a * b
```

- Function name = LHS of `formula_hint` if present, else the entry's `id`
- Args = each `depends_on` id in declared order, all typed `float`
- Return type `float`
- Body: at most three lines (optional guard `if`, optional intermediate, return)

Division guards: every variable denominator must short-circuit to `float("inf")` when ≤ 0. Numeric-literal denominators (e.g. `value / 100`) need no guard.

## Function-style notation translations

| Source | Translation |
|---|---|
| `max(...)`, `min(...)`, `abs(...)`, `sum(...)` | Python builtins |
| `exp(...)`, `log(...)`, `sqrt(...)`, `ln(...)` | `math.exp`, `math.log`, `math.sqrt` (add `import math`) |
| `mean(...)`, `avg(...)` | `_mean(*args)` helper at top of module |
| `P(...)`, `p(...)` | `raise NotImplementedError(...)` stub with TODO comment carrying the original formula |

## Module structure

```python
"""
Generated PlanExe deterministic calculations.

Plan: <plan_name>
Plan type: <plan_type>

One function per formula_hint entry...
"""

from __future__ import annotations
import math   # only if needed

# _mean helper, only if needed

# functions, in order: recommended_first_calculations, then derived_questions
```

No top-level executable code, no `__main__` block, no file I/O, no classes, no decorators, no per-function docstrings, no in-body comments (except the `P(...)` TODO).

## Common Mistakes

| Mistake | Fix |
|---|---|
| Wrapping the Python output in ```` ```python ```` fences | Raw Python only |
| Adding a `if __name__ == "__main__":` demo block | This stage emits a library, not a runnable script |
| Generating a class hierarchy | One function per formula; no classes unless required by the formulas themselves (they aren't) |
| Inventing or omitting arguments to "make the formula work" | Args must match `depends_on` exactly, in order |
| Forgetting the divide-by-zero guard | Every variable denominator gets a guard; numeric literals don't |
| Emitting `def people_contacted(...) -> float: """People contacted"""` | No per-function docstrings — the signature is self-documenting |
| Translating `P(x >= y)` as a literal Python comparison | `P(...)` is probability notation; emit a `NotImplementedError` stub instead |
| Including functions for `key_values` or `missing_values_to_estimate` ids | Those are inputs, not calculations |

## Reference

- System prompt (authoritative): `system-prompt.txt`
- Pipeline overview and code-generation rules: `../../README.md`, Stage 5
- Companion skills: `../extract-parameters/SKILL.md`, `../validate-parameters/SKILL.md`, `../generate-bounds/SKILL.md`
- Example input for testing: `/tmp/extract-params-heatwave-v10.json` (passes validate-parameters with `valid: true`)
