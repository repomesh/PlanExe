---
name: summarize-insights
description: Use after the napkin_math pipeline has produced parameters/bounds/scenarios/montecarlo JSON to generate a human-readable insights.md that highlights threshold verdicts (DOOM / FRAGILE / MARGINAL / ROBUST), sensitivity drivers, scenario warnings, and model-collapse risk. The verdict text calls out numbers that likely spell doom for the project.
---

# Summarize napkin_math insights into a readable markdown digest

## Overview

A thin wrapper around `experiments/napkin_math/summarize_insights.py`. The script reads any subset of the four pipeline artifacts (`parameters.json`, `bounds.json`, `scenarios.json`, `montecarlo.json`) and emits `insights.md` next to them. The output is meant to be skimmable — a glance tells you whether the plan is in trouble.

## When to Use

- The Monte Carlo stage has just produced `montecarlo.json` and the user wants a verdict
- The user asks "is this plan in trouble?" or "what does the simulation say?"
- After any iteration on bounds or calculations, to see how the doom signals moved

Not for: producing the simulation itself (`monte-carlo`), running scenarios (`run-scenarios`), or extracting parameters from a report.

## Workflow

1. **Locate the inputs.** Required: `parameters.json`. Optional but recommended: `bounds.json`, `scenarios.json`, `montecarlo.json`. The script degrades gracefully if any optional file is missing — it just omits that section. If `parameters.json` is missing, ask.

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

3. **Report back.** Tell the user the output path. If the user asks for a verdict in-conversation, read `insights.md` and quote the doom / fragile bullets verbatim — don't paraphrase.

## How doom verdicts are decided

Verdicts come from the user's own threshold definitions in the Monte Carlo settings. No identifier-string or unit-string interpretation — domain-bias-free.

Each threshold has an operator (`>=`, `<=`, etc.) and a value. The user wrote the threshold because they want it to pass. The verdict is the pass probability in the simulation:

| Band | Pass probability | Verdict | Note |
|---|---|---|---|
| ≥ 80% | strong majority | **ROBUST** | passes in the strong majority of runs |
| 50–80% | uncomfortable | **MARGINAL** | passes more often than not but uncomfortably close |
| 20–50% | minority pass | **FRAGILE** | fails in the majority of runs |
| < 20% | rarely passes | **DOOM** | almost certainly fails |

Any output classified DOOM or FRAGILE also gets a "bottom line" callout at the top of the report.

The script does **not** invent thresholds for outputs the user did not declare. To get a verdict on an output, declare a threshold on it in the Monte Carlo settings file.

## Sections in the generated insights.md

The output is written for project managers and non-developers. Section names and language avoid statistics/engineering jargon (no "NaN", "Infinity", "Pearson", "non-finite", "model collapse", "p05/p50/p95" in the body text):

- **Plan summary** — name, type, primary goal, modelling frame.
- **Headline verdicts** — pass-probability table plus a "Bottom line — likely deal-breakers" callout for DOOM thresholds and "Caution — coin-flip territory" for FRAGILE.
- **Range of outcomes** — worst-case / typical / best-case / average / uncertainty / blank-runs columns. The "blank runs" plus a separate "Numbers the model could not compute" callout replace the previous NaN/Infinity wording.
- **Which inputs move the outcome the most** — top-3 drivers per output with ↑/↓ direction and a 0-to-±1 score.
- **Three hand-picked scenarios** — the low/middle/high deterministic table, with a "things flagged in the three-scenario check" sub-section for scenario warnings.
- **Inputs the plan did not supply** — `extract-parameters` missing-data entries, marked **estimated** when bounded or **still missing** when not.
- **Source files** — pointers to the underlying machine-readable JSON for anyone who wants every number.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Running before `montecarlo.json` exists | Threshold verdicts are the most actionable section. Run the Monte Carlo stage first. |
| Reading the markdown and paraphrasing doom callouts | Quote them. The cutoff bands and phrasing are deliberate. |
| Treating a MARGINAL verdict as good news | MARGINAL means "passes in 50–80% of runs" — that's the same as "fails up to 50% of the time". |
| Inventing a threshold to make a number look good | Thresholds reflect the user's success criteria. Don't fabricate them after the fact. |

## Reference

- Script (authoritative): `experiments/napkin_math/summarize_insights.py`
- Companion skills: `../monte-carlo/SKILL.md`, `../run-scenarios/SKILL.md`, `../generate-bounds/SKILL.md`, `../extract-parameters-from-full/SKILL.md`, `../extract-parameters-from-digest/SKILL.md`
- Example output: any `insights.md` under `experiments/napkin_math/output/<version>/<plan>/`
