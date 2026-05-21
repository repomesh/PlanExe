#!/usr/bin/env python3
"""Advisory audit: classify every prior-baseline signal by what happened
to it in the current parameters.json.

Implements Fork B of proposal 141 (source-preservation audit). Reads a
prior ``parameters.json`` and a current ``parameters.json``, builds the
prior signal set, and classifies each prior id as one of:

    preserved_by_id                — same id is in current
    preserved_by_output_name       — prior id appears as an output_name
    preserved_as_formula_dependency — prior id is on a current formula RHS
                                      or in a current depends_on list
    likely_renamed                 — prior id has high snake_case token
                                      overlap with one or more current ids
    absent_unexplained             — no preservation evidence found

Advisory only. Exit 0 unless the input is malformed (exit 2). No strict
mode, no CI gating, no schema changes to extract prompts — those land in
later proposal 141 PRs after this audit's findings (false-positive rate,
useful catches) are measured on the corpus.

Out of scope for this PR (deferred to later proposal 141 PRs):
  - Fork A (source-digest regex scan against the current artifact).
  - The optional ``dropped_signals`` schema in extract prompts.
  - LLM rationale parsing of ``dropped_signals`` entries.
  - Strict-mode exit-non-zero policy.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SECTIONS_WITH_IDS: tuple[str, ...] = (
    "key_values",
    "missing_values_to_estimate",
    "derived_questions",
    "recommended_first_calculations",
    "unmodelled_gates",
)

# Sections whose entries can declare an ``output_name`` distinct from
# their ``id``. The audit treats matching output_names as a preservation
# signal because downstream consumers (calculations.py, monte-carlo) bind
# by output_name, not by id.
SECTIONS_WITH_OUTPUT_NAMES: tuple[str, ...] = (
    "key_values",
    "derived_questions",
    "recommended_first_calculations",
)

# Builtins stripped from formula_hint RHS token extraction. Matches the
# set in validate_parameters.py for consistency.
FORMULA_BUILTINS: frozenset[str] = frozenset(
    {"min", "max", "abs", "sum", "round", "int", "float"}
)

# Jaccard-overlap threshold for the "likely_renamed" classification.
# A snake_case prior id and a candidate current id are considered a
# plausible rename when |intersection|/|union| >= this value.
# Calibrated empirically: ``actual_X_rate`` vs ``X_realised_rate``
# overlaps at 0.5; ``unrelated_thing`` vs ``different_id`` overlaps at 0.
# Lower values produce more candidates (advisory); 0.4 is permissive
# enough to surface most renames without flooding the report.
RENAME_JACCARD_THRESHOLD: float = 0.4

# Maximum candidate suggestions per likely_renamed prior id. The audit
# is advisory — the reviewer wants the top few, not an exhaustive list.
MAX_RENAME_CANDIDATES: int = 3


def parse_rhs_tokens(formula: str) -> set[str]:
    """Extract snake_case identifier tokens from the RHS of a
    ``lhs = rhs`` formula (or the whole expression when no ``=``).
    Function-name builtins are filtered out so they cannot collide with
    prior ids. Numeric literals fall out naturally because they are not
    snake_case identifiers.
    """
    if not isinstance(formula, str) or not formula:
        return set()
    rhs = formula.split("=", 1)[1] if "=" in formula else formula
    return set(re.findall(r"[a-z_][a-z0-9_]*", rhs)) - FORMULA_BUILTINS


def build_signal_index(params: dict) -> dict[str, Any]:
    """Build a single index over a parameters.json artifact.

    Both ``id`` values and ``output_name`` values are treated as
    first-class signals — downstream consumers (calculations.py,
    monte-carlo runner, summarize-assessment) bind by ``output_name``,
    not by entry ``id``. A calc entry whose ``id`` survives but whose
    ``output_name`` changes is a genuine signal regression even though
    the entry id matches; tracking both names catches that case.

    Returns a dict with:
      - ``signals``: ordered dict from name → ``{"kind": "id" |
        "output_name", "section": str}``. First occurrence wins when a
        name appears as both an id and an output_name (the id reading
        is the more authoritative one).
      - ``ids``: set of every entry's ``id`` across SECTIONS_WITH_IDS
      - ``output_names``: set of every entry's ``output_name`` (when
        declared) across SECTIONS_WITH_OUTPUT_NAMES
      - ``formula_tokens``: set of every snake_case token that appears
        on a ``formula_hint`` RHS or in a ``depends_on`` list in
        derived_questions / recommended_first_calculations
    """
    signals: dict[str, dict[str, str]] = {}
    ids: set[str] = set()
    output_names: set[str] = set()
    formula_tokens: set[str] = set()
    for section in SECTIONS_WITH_IDS:
        for entry in params.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            eid = entry.get("id")
            if isinstance(eid, str) and eid:
                ids.add(eid)
                signals.setdefault(eid, {"kind": "id", "section": section})
    for section in SECTIONS_WITH_OUTPUT_NAMES:
        for entry in params.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("output_name")
            if isinstance(name, str) and name:
                output_names.add(name)
                signals.setdefault(name, {"kind": "output_name", "section": section})
    for section in ("derived_questions", "recommended_first_calculations"):
        for entry in params.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            formula = entry.get("formula_hint")
            if isinstance(formula, str):
                formula_tokens |= parse_rhs_tokens(formula)
            for dep in entry.get("depends_on", []) or []:
                if isinstance(dep, str) and dep:
                    formula_tokens.add(dep)
    return {
        "signals": signals,
        "ids": ids,
        "output_names": output_names,
        "formula_tokens": formula_tokens,
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_rename_candidates(
    prior_name: str, current_candidate_pool: set[str]
) -> list[tuple[str, float]]:
    """Return up to MAX_RENAME_CANDIDATES candidate current names whose
    snake_case token Jaccard overlap with ``prior_name`` meets the
    rename threshold. Sorted descending by overlap.

    The candidate pool should be the union of current ids and current
    output_names — a prior id can rename to either a current id (entry
    rename) or a current output_name (signal-role move).
    """
    prior_tokens = set(prior_name.split("_"))
    if not prior_tokens:
        return []
    scored: list[tuple[str, float]] = []
    for cid in current_candidate_pool:
        if cid == prior_name:
            continue
        score = jaccard(prior_tokens, set(cid.split("_")))
        if score >= RENAME_JACCARD_THRESHOLD:
            scored.append((cid, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:MAX_RENAME_CANDIDATES]


def classify_prior_signal(
    prior_name: str, current_index: dict[str, Any]
) -> dict[str, Any]:
    """Classify one prior signal name by what evidence the current
    artifact provides for it.
    """
    if prior_name in current_index["ids"]:
        return {"status": "preserved_by_id"}
    if prior_name in current_index["output_names"]:
        return {"status": "preserved_by_output_name"}
    if prior_name in current_index["formula_tokens"]:
        return {"status": "preserved_as_formula_dependency"}
    candidate_pool = current_index["ids"] | current_index["output_names"]
    candidates = find_rename_candidates(prior_name, candidate_pool)
    if candidates:
        return {
            "status": "likely_renamed",
            "candidates": [
                {"id": cid, "jaccard": round(score, 3)}
                for cid, score in candidates
            ],
        }
    return {"status": "absent_unexplained"}


def audit(prior_params: dict, current_params: dict) -> dict[str, Any]:
    """Run the Fork-B audit. Returns a structured report:

    {
      "summary": {
        "prior_total": int,
        "preserved_by_id": int,
        "preserved_by_output_name": int,
        "preserved_as_formula_dependency": int,
        "likely_renamed": int,
        "absent_unexplained": int,
      },
      "details": [
        {"prior_name": str, "prior_kind": "id" | "output_name",
         "prior_section": str, "status": str, ...},
        ...
      ],
    }

    Every prior name — both entry ``id`` values and entry ``output_name``
    values — is treated as a first-class signal. A calc whose ``id``
    survives but whose ``output_name`` changes is a genuine signal
    regression because downstream binders bind by output_name.
    """
    prior_index = build_signal_index(prior_params)
    current_index = build_signal_index(current_params)
    summary = {
        "prior_total": len(prior_index["signals"]),
        "preserved_by_id": 0,
        "preserved_by_output_name": 0,
        "preserved_as_formula_dependency": 0,
        "likely_renamed": 0,
        "absent_unexplained": 0,
    }
    details: list[dict[str, Any]] = []
    for prior_name in sorted(prior_index["signals"]):
        meta = prior_index["signals"][prior_name]
        cls = classify_prior_signal(prior_name, current_index)
        summary[cls["status"]] = summary[cls["status"]] + 1
        details.append({
            "prior_name": prior_name,
            "prior_kind": meta["kind"],
            "prior_section": meta["section"],
            **cls,
        })
    return {"summary": summary, "details": details}


def _format_signal_label(detail: dict[str, Any]) -> str:
    kind = detail["prior_kind"]
    section = detail["prior_section"]
    kind_tag = "output_name" if kind == "output_name" else "id"
    return f"{detail['prior_name']} [{section}/{kind_tag}]"


def render_text_report(report: dict[str, Any]) -> str:
    """Human-readable rendering of an audit report. Lists summary
    counts, then enumerates every non-preserved-by-id signal so reviewers
    can see what was lost or renamed without scrolling past noise. Each
    entry is tagged with ``[section/id]`` or ``[section/output_name]``
    so reviewers can distinguish entry-id drift from output-name drift.
    """
    s = report["summary"]
    lines = [
        "Source-preservation audit (Fork B): prior vs current parameters.json",
        "",
        f"  Prior signals total              : {s['prior_total']}",
        f"  preserved_by_id                  : {s['preserved_by_id']}",
        f"  preserved_by_output_name         : {s['preserved_by_output_name']}",
        f"  preserved_as_formula_dependency  : {s['preserved_as_formula_dependency']}",
        f"  likely_renamed                   : {s['likely_renamed']}",
        f"  absent_unexplained               : {s['absent_unexplained']}",
        "",
    ]
    renamed = [d for d in report["details"] if d["status"] == "likely_renamed"]
    if renamed:
        lines.append("LIKELY RENAMED:")
        for d in renamed:
            cand_str = ", ".join(
                f"{c['id']} (j={c['jaccard']})" for c in d["candidates"]
            )
            lines.append(f"  {_format_signal_label(d)} → {cand_str}")
        lines.append("")
    absent = [d for d in report["details"] if d["status"] == "absent_unexplained"]
    if absent:
        lines.append("ABSENT UNEXPLAINED:")
        for d in absent:
            lines.append(f"  {_format_signal_label(d)}")
        lines.append("")
    by_output = [
        d for d in report["details"] if d["status"] == "preserved_by_output_name"
    ]
    if by_output:
        lines.append("PRESERVED BY OUTPUT_NAME (signal survives via formula LHS):")
        for d in by_output:
            lines.append(f"  {_format_signal_label(d)}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prior", type=Path, required=True)
    p.add_argument("--current", type=Path, required=True)
    p.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="If set, write the machine-readable JSON report to this path.",
    )
    args = p.parse_args()
    try:
        prior_params = json.loads(args.prior.read_text())
        current_params = json.loads(args.current.read_text())
    except json.JSONDecodeError as exc:
        print(f"audit_source_preservation: JSON parse error: {exc}", file=sys.stderr)
        return 2
    report = audit(prior_params, current_params)
    print(render_text_report(report))
    if args.report_json is not None:
        args.report_json.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
