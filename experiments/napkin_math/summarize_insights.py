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
    rows = [
        "## Threshold verdicts",
        "",
        "Probability that each user-declared threshold passes across the Monte Carlo runs.",
        "Verdict cutoffs: ≥80% ROBUST, ≥50% MARGINAL, ≥20% FRAGILE, <20% DOOM.",
        "",
        "| Output | Condition | Pass probability | Verdict | Note |",
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
        rows.append("### Bottom line: doom signals")
        rows.append("")
        for o in doom:
            t = mc["thresholds"][o]
            rows.append(
                f"- **`{o}`** fails ({t['operator']} {fmt_number(t['value'])}) in "
                f"{(1 - (t.get('probability') or 0)) * 100:.1f}% of runs. This is the "
                f"condition the plan needs to meet; it does not."
            )
        rows.append("")
    if fragile:
        rows.append("### Caution: fragile signals")
        rows.append("")
        for o in fragile:
            t = mc["thresholds"][o]
            rows.append(
                f"- **`{o}`** passes in only "
                f"{(t.get('probability') or 0) * 100:.1f}% of runs. Below half — review the "
                f"driving assumptions before proceeding."
            )
        rows.append("")
    return rows


def render_distributions(mc: dict | None) -> list[str]:
    if not mc or not mc.get("outputs"):
        return []
    rows = [
        "## Monte Carlo distributions",
        "",
        "Per-output summary across all runs. `missing_count` > 0 signals a calculation "
        "that produced NaN/Infinity in some runs — usually a divide-by-zero or an "
        "unresolved dependency.",
        "",
        "| Output | Unit | p05 | p50 | p95 | mean | std | missing |",
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
        rows.append("### Model instability")
        rows.append("")
        for name, rate in collapses:
            severity = "**SEVERE**" if rate >= 0.5 else "noteworthy"
            rows.append(
                f"- {severity}: `{name}` was non-finite in {rate * 100:.1f}% of runs. "
                f"A dependency is likely unresolved or a divisor goes to zero."
            )
        rows.append("")
    return rows


def render_sensitivity(mc: dict | None) -> list[str]:
    if not mc or not mc.get("sensitivity"):
        return []
    rows = [
        "## What drives the uncertainty",
        "",
        "Pearson correlation between each sampled input and each output. "
        "Positive r means moving the input up moves the output up; negative the opposite. "
        "Sensitivity is **not** causation — it only ranks how tightly outputs track inputs in the sample.",
        "",
    ]
    for output_id, s in mc["sensitivity"].items():
        if not s.get("top_inputs"):
            continue
        rows.append(f"**`{output_id}`** — top drivers:")
        rows.append("")
        for t in s["top_inputs"][:3]:
            sign = "↑" if t["correlation"] >= 0 else "↓"
            rows.append(f"- `{t['id']}` ({sign} r = {t['correlation']:+.3f})")
        rows.append("")
    return rows


def render_scenarios(scenarios: dict | None) -> list[str]:
    if not scenarios or not scenarios.get("comparison"):
        return []
    rows = [
        "## Deterministic scenarios (low / base / high)",
        "",
        "Single-point evaluation at each scenario's bounds. The `low / base / high` "
        "labels refer to **input bounds**, not outcomes — a `high` cost scenario is "
        "bad, a `high` effectiveness scenario is good. Watch for outputs that go "
        "negative at base.",
        "",
        "| Output | Unit | low | base | high | spread |",
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
        rows.append("### Scenario warnings")
        rows.append("")
        for w in warns:
            scope = w.get("scenario") or "all"
            calc = w.get("calculation") or "—"
            rows.append(f"- **{scope}** / `{calc}`: {w['message']}")
        rows.append("")
    return rows


def render_missing_data(params: dict | None, bounds: dict | None) -> list[str]:
    if not params:
        return []
    declared = params.get("missing_values_to_estimate", [])
    if not declared:
        return []
    rows = [
        "## Missing data flagged by extract-parameters",
        "",
        "The extractor identified inputs the plan does not supply. Bounded entries "
        "carry an assumed low/base/high; unbounded entries propagate as unresolved "
        "dependencies into Monte Carlo, where they will show up as model collapse.",
        "",
    ]
    bound_ids = set(bounds or {})
    for mv in declared:
        vid = mv["id"]
        status = "bounded" if vid in bound_ids else "**unbounded**"
        rows.append(f"- `{vid}` ({status}) — {mv.get('why_needed', '')}")
    rows.append("")
    return rows


def render_inputs_footer(params_path: Path | None, bounds_path: Path | None,
                        scenarios_path: Path | None, mc_path: Path | None) -> list[str]:
    rows = ["## Inputs", ""]
    for label, p in [
        ("parameters", params_path),
        ("bounds", bounds_path),
        ("scenarios", scenarios_path),
        ("montecarlo", mc_path),
    ]:
        if p and p.exists():
            rows.append(f"- `{p.name}`: {label}")
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
