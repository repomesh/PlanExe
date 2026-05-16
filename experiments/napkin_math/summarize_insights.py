#!/usr/bin/env python3
"""Summarize napkin_math pipeline outputs into a human-readable insights.md.

Takes the four pipeline artifacts (any subset present — the script degrades
gracefully) and emits a markdown file next to the parameters that calls out:

- Threshold verdicts (DOOM / FRAGILE / MARGINAL / ROBUST) based on the
  user-declared threshold pass probabilities.
- Deterministic low/base/high outputs.
- Pearson-correlation sensitivity drivers per output.
- Model-collapse warnings (non-finite run rates).
- Missing-data entries that did not receive bounds.

Doom verdicts are driven entirely by the user's own threshold definitions
(operator + value). The script never inspects identifier strings, output
names, or units to decide whether a number is good or bad — that would be
domain-bias. It only knows: "the user said this should pass; here is how
often it does in 10k Monte Carlo runs."
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


VERDICT_BANDS = [
    (0.80, "ROBUST",   "passes in the strong majority of runs"),
    (0.50, "MARGINAL", "passes more often than not but uncomfortably close"),
    (0.20, "FRAGILE",  "fails in the majority of runs"),
    (0.00, "DOOM",     "almost certainly fails"),
]


def load_json(path: Path) -> dict | None:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"warning: cannot parse {path}: {exc}", file=sys.stderr)
        return None


def fmt_number(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        abs_v = abs(value)
        if abs_v >= 1_000_000:
            return f"{value:,.0f}"
        if abs_v >= 1_000:
            return f"{value:,.0f}"
        if abs_v >= 1:
            return f"{value:,.2f}"
        return f"{value:.4f}"
    return str(value)


def verdict_for(probability: float | None) -> tuple[str, str]:
    if probability is None:
        return "UNKNOWN", "no valid runs"
    for cutoff, label, note in VERDICT_BANDS:
        if probability >= cutoff:
            return label, note
    return "DOOM", "almost certainly fails"


def render_plan_summary(params: dict | None) -> list[str]:
    if not params:
        return ["# Plan summary", "", "_(parameters.json not available)_", ""]
    summary = params.get("plan_summary", {})
    lines = [
        f"# Plan: {summary.get('plan_name', 'unnamed')}",
        "",
        f"**Type:** {summary.get('plan_type', 'unknown')}  ",
        f"**Primary goal:** {summary.get('primary_goal', '—')}  ",
        f"**Modelling frame:** {summary.get('modelling_frame', '—')}",
        "",
    ]
    return lines


def render_threshold_verdicts(mc: dict | None) -> list[str]:
    if not mc or not mc.get("thresholds"):
        return []
    n_runs = mc.get("settings", {}).get("n_runs")
    runs_phrase = f"{n_runs:,} simulated runs" if isinstance(n_runs, int) else "the simulated runs"
    rows = [
        "## Headline verdicts",
        "",
        f"For each success condition the plan needs to meet, this is how often it actually meets it across {runs_phrase} that vary every uncertain input within its plausible range.",
        "",
        "Bands: at least 80% **ROBUST**, 50–80% **MARGINAL**, 20–50% **FRAGILE**, under 20% **DOOM**.",
        "",
        "| What we wanted | Condition | How often it holds | Verdict | What that means |",
        "|---|---|---:|---|---|",
    ]
    doom = []
    fragile = []
    for output_id, t in mc["thresholds"].items():
        op = t["operator"]
        val = t["value"]
        prob = t.get("probability")
        verdict, note = verdict_for(prob)
        prob_str = f"{prob * 100:.1f}%" if prob is not None else "n/a"
        rows.append(
            f"| `{output_id}` | {op} {fmt_number(val)} | {prob_str} | **{verdict}** | {note} |"
        )
        if verdict == "DOOM":
            doom.append(output_id)
        elif verdict == "FRAGILE":
            fragile.append(output_id)
    rows.append("")
    if doom:
        rows.append("### Bottom line — likely deal-breakers")
        rows.append("")
        for o in doom:
            t = mc["thresholds"][o]
            fail_pct = (1 - (t.get("probability") or 0)) * 100
            rows.append(
                f"- **`{o}`** misses its target ({t['operator']} {fmt_number(t['value'])}) "
                f"in {fail_pct:.1f}% of simulated futures. The plan depends on this holding; "
                f"the math says it almost never does."
            )
        rows.append("")
    if fragile:
        rows.append("### Caution — coin-flip territory")
        rows.append("")
        for o in fragile:
            t = mc["thresholds"][o]
            pass_pct = (t.get("probability") or 0) * 100
            rows.append(
                f"- **`{o}`** holds in only {pass_pct:.1f}% of simulated futures. That is "
                f"below half — the assumptions behind it deserve a hard review before the "
                f"plan moves forward."
            )
        rows.append("")
    return rows


def render_distributions(mc: dict | None) -> list[str]:
    if not mc or not mc.get("outputs"):
        return []
    rows = [
        "## Range of outcomes",
        "",
        "Each row is one of the numbers the plan needs to track. Reading across, you get a sense of the "
        "**worst-case** (5th percentile — only 5% of futures are this bad or worse), the **typical case** "
        "(median), the **best-case** (95th percentile — only 5% of futures are this good or better), and "
        "the **average** across all simulated futures.",
        "",
        "The **uncertainty** column is the standard deviation — bigger numbers mean the outcome swings more "
        "widely between futures. The **blank runs** column counts simulated futures where the number could "
        "not be calculated at all (typically an input the plan never specified, or a formula trying to "
        "divide by a value that landed at zero).",
        "",
        "| Number | Unit | Worst (5%) | Typical | Best (95%) | Average | Uncertainty | Blank runs |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    collapses = []
    for name, o in mc["outputs"].items():
        rows.append(
            f"| `{name}` | {o['unit']} | {fmt_number(o['p05'])} | {fmt_number(o['p50'])} "
            f"| {fmt_number(o['p95'])} | {fmt_number(o['mean'])} | {fmt_number(o['std'])} "
            f"| {o['missing_count']:,} |"
        )
        if o["missing_count"] > 0 and o["count"] > 0:
            rate = o["missing_count"] / (o["missing_count"] + o["count"])
            if rate >= 0.05:
                collapses.append((name, rate))
        elif o["missing_count"] > 0:
            collapses.append((name, 1.0))
    rows.append("")
    if collapses:
        rows.append("### Numbers the model could not compute")
        rows.append("")
        for name, rate in collapses:
            severity = "**most of the time**" if rate >= 0.5 else "noticeably often"
            rows.append(
                f"- `{name}` was blank in {rate * 100:.1f}% of simulated futures ({severity}). "
                f"The plan is probably missing an input the formula needs, or one of the inputs "
                f"can legitimately land at zero, which breaks the division. Fix the inputs and "
                f"re-run."
            )
        rows.append("")
    return rows


def render_sensitivity(mc: dict | None) -> list[str]:
    if not mc or not mc.get("sensitivity"):
        return []
    rows = [
        "## Which inputs move the outcome the most",
        "",
        "For each number above, this is the short list of inputs that most strongly move it. "
        "The score next to each driver runs from 0 (no relationship) to ±1 (lock-step). "
        "**↑** means the output goes up when this input goes up; **↓** means the opposite. "
        "Treat this as \"these are the levers worth getting right\" — it ranks how closely outputs "
        "track inputs in the simulation, not strict cause-and-effect.",
        "",
    ]
    for output_id, s in mc["sensitivity"].items():
        if not s.get("top_inputs"):
            continue
        rows.append(f"**`{output_id}`** — strongest drivers:")
        rows.append("")
        for t in s["top_inputs"][:3]:
            sign = "↑" if t["correlation"] >= 0 else "↓"
            rows.append(f"- `{t['id']}` ({sign} score {t['correlation']:+.2f})")
        rows.append("")
    return rows


def render_scenarios(scenarios: dict | None) -> list[str]:
    if not scenarios or not scenarios.get("comparison"):
        return []
    rows = [
        "## Three hand-picked scenarios",
        "",
        "Instead of simulating thousands of futures, this section picks exactly three: every uncertain "
        "input set to the **low** end of its range, every input set to its **middle** value, and every "
        "input set to the **high** end. It is a sanity check, not a full picture.",
        "",
        "The labels refer to **inputs**, not to whether the outcome is good or bad. A high-cost input "
        "is bad news; a high-effectiveness input is good news. The honest read is: if a number that the "
        "plan needs to stay positive is already negative in the middle column, the plan is in trouble at "
        "its own central assumptions — never mind the worst case.",
        "",
        "| Number | Unit | Low inputs | Middle inputs | High inputs | Range |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, o in scenarios["comparison"]["outputs"].items():
        spread = o.get("spread_absolute")
        rows.append(
            f"| `{name}` | {o.get('unit', '—')} | "
            f"{fmt_number(o['low'])} | {fmt_number(o['base'])} | {fmt_number(o['high'])} | "
            f"{fmt_number(spread)} |"
        )
    rows.append("")
    warns = scenarios.get("warnings", [])
    if warns:
        rows.append("### Things flagged in the three-scenario check")
        rows.append("")
        for w in warns:
            scope = w.get("scenario") or "all"
            calc = w.get("calculation") or "—"
            rows.append(f"- **{scope}** scenario, `{calc}`: {w['message']}")
        rows.append("")
    return rows


def render_missing_data(params: dict | None, bounds: dict | None) -> list[str]:
    if not params:
        return []
    declared = params.get("missing_values_to_estimate", [])
    if not declared:
        return []
    rows = [
        "## Inputs the plan did not supply",
        "",
        "Things the plan needs to be modelled but does not state directly. Entries marked "
        "**estimated** have been given a plausible low/middle/high range; entries marked "
        "**still missing** have no value at all, so any number that depends on them will "
        "show up as a blank run in the section above.",
        "",
    ]
    bound_ids = set(bounds or {})
    for mv in declared:
        vid = mv["id"]
        status = "estimated" if vid in bound_ids else "**still missing**"
        rows.append(f"- `{vid}` ({status}) — {mv.get('why_needed', '')}")
    rows.append("")
    return rows


def render_inputs_footer(params_path: Path | None, bounds_path: Path | None,
                        scenarios_path: Path | None, mc_path: Path | None) -> list[str]:
    rows = ["## Source files", "",
            "This summary was generated from the following machine-readable files. "
            "Open them if you want to see every number, not just the headlines.",
            ""]
    labels = {
        "parameters": "extracted plan parameters",
        "bounds": "plausible low/middle/high ranges for each input",
        "scenarios": "three hand-picked scenarios",
        "montecarlo": "thousands of simulated futures",
    }
    for key, p in [
        ("parameters", params_path),
        ("bounds", bounds_path),
        ("scenarios", scenarios_path),
        ("montecarlo", mc_path),
    ]:
        if p and p.exists():
            rows.append(f"- `{p.name}` — {labels[key]}")
    rows.append("")
    return rows


def build_insights(params: dict | None, bounds: dict | None,
                   scenarios: dict | None, mc: dict | None,
                   params_path: Path | None, bounds_path: Path | None,
                   scenarios_path: Path | None, mc_path: Path | None) -> str:
    sections: list[list[str]] = [
        render_plan_summary(params),
        render_threshold_verdicts(mc),
        render_distributions(mc),
        render_sensitivity(mc),
        render_scenarios(scenarios),
        render_missing_data(params, bounds),
        render_inputs_footer(params_path, bounds_path, scenarios_path, mc_path),
    ]
    out: list[str] = []
    for section in sections:
        if section:
            out.extend(section)
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--parameters", type=Path, required=True)
    p.add_argument("--bounds", type=Path)
    p.add_argument("--scenarios", type=Path)
    p.add_argument("--montecarlo", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    output = args.output or (args.parameters.parent / "insights.md")
    md = build_insights(
        load_json(args.parameters),
        load_json(args.bounds) if args.bounds else None,
        load_json(args.scenarios) if args.scenarios else None,
        load_json(args.montecarlo) if args.montecarlo else None,
        args.parameters, args.bounds, args.scenarios, args.montecarlo,
    )
    output.write_text(md)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
