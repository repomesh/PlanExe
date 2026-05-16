---
name: summarize-insights
description: Use after the napkin_math pipeline has produced parameters/bounds/scenarios/montecarlo JSON to generate a human-readable insights.md that highlights threshold verdicts (DOOM / FRAGILE / MARGINAL / ROBUST), sensitivity drivers, scenario warnings, and model-collapse risk. Bad news first, no sugar-coating, no hedging — the artifact tells project managers what the math actually says.
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

## Writing rules — apply to the script's output AND to anything you say back to the user about the insights

These are not stylistic preferences. They are how this skill is meant to communicate.

1. **Bad news first.** The first section after the plan summary is `Bad news first`, which consolidates every signal that the plan does not survive its own assumptions: DOOM and FRAGILE thresholds, scenario warnings, numbers the model could not compute, and inputs the plan does not supply at all. If any of those exist, they lead. Detail tables come after. If nothing qualifies, the section is omitted entirely — silence is the only acceptable form of good news.

2. **No sugar-coating.** A 5% pass probability is "almost certainly fails", not "shows some challenges". A negative base-scenario number is "the plan is in trouble at its own central assumptions", not "may warrant further attention". Use the strongest accurate language; if the script's wording softens a result, fix the script.

3. **No sycophancy.** Never start a paragraph with "Great plan, but..." or "The team has done strong work; one concern is...". The reader has the plan in front of them. They do not need praise from the report.

4. **No hedging phrases.** Banned in both the script's emitted text and in conversational reporting:
   - `the honest read is`, `frankly`, `to be fair`, `in fairness`, `candidly`, `let's be real`, `look, the truth is`
   - rhetorical "I'll be honest with you" / "to put it bluntly" / "if I may"

   These imply the default mode is dishonest or evasive. State the claim directly.

5. **Hedges about data vs hedges about the speaker.** Hedges that point at the underlying simulation are fine: "the simulation shows", "based on the bounds we have", "within the assumed ranges". Hedges that point at the writer's posture are not.

6. **Quote the verdicts; don't paraphrase.** When the script emits `**DOOM** — almost certainly fails`, report it as `DOOM — almost certainly fails`. Don't summarise it as "this one is concerning". The verdict bands are precise and load-bearing.

## Sections in the generated insights.md

Order is deliberate: plan summary, then bad news, then the detail tables. The output is written for project managers and non-developers — section names and language avoid statistics/engineering jargon (no "NaN", "Infinity", "Pearson", "non-finite", "model collapse", "p05/p50/p95" in the body text):

- **Plan summary** — name, type, primary goal, modelling frame.
- **Bad news first** — the consolidated top-of-report block, only present when there is bad news. Sub-sections in this order: Likely deal-breakers (DOOM thresholds), Coin-flip territory (FRAGILE thresholds), Already broken in the three-scenario sanity check (scenario warnings), Numbers the model could not compute (≥5% blank runs), Inputs the plan does not supply at all (still-missing entries).
- **Verdict table (all thresholds, worst first)** — every threshold including ROBUST/MARGINAL ones, sorted by severity (DOOM → FRAGILE → MARGINAL → ROBUST).
- **Range of outcomes** — worst-case / typical / best-case / average / uncertainty / blank-runs columns. No standalone alerts here; alerts live in "Bad news first" above.
- **Which inputs move the outcome the most** — top-3 drivers per output with ↑/↓ direction and a 0-to-±1 score.
- **Three hand-picked scenarios** — the low/middle/high deterministic table. No standalone alerts; warnings have already been surfaced in "Bad news first".
- **Inputs the plan did not supply** — `extract-parameters` missing-data entries, marked **estimated** when bounded or **still missing** when not. Still-missing entries have already been flagged in "Bad news first"; this section is the full list including the estimated ones.
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
