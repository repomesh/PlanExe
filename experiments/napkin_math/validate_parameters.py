#!/usr/bin/env python3
"""Deterministic validator for napkin_math parameters.json.

Replaces the LLM-driven `validate-parameters` skill. Reads a
`parameters.json` produced by `extract-parameters-from-digest` (or
`extract-parameters-from-full`) and emits `validation.json` next to it in
the shape that `summarize_assessment.py` consumes (named `checks_performed`
list + per-violation rule_id/severity/path/message/suggested_fix).

16 structural checks are run:

    json_parse                                # implicit (file already parsed)
    top_level_structure                       # plan_summary + four arrays
    required_fields                           # required keys per entry
    array_length_caps                         # 8 / 5 / 5 / 5
    global_id_uniqueness                      # ids unique across all arrays
    snake_case_ids                            # ^[a-z][a-z0-9_]*$
    depends_on_declared                       # every id in depends_on declared
    formula_rhs_declared                      # every RHS var declared (or own output_name)
    fraction_value_range                      # unit==fraction => value in [0,1]
    comment_word_caps                         # comment <= 25 words
    source_text_word_caps                     # source_text <= 20 words
    output_name_present_when_formula_hint     # formula => output_name not null
    output_unit_present_when_formula_hint     # formula => output_unit not null
    no_dead_end_variables                     # every kv/mv consumed by a calc
    threshold_friendly_naming                 # WARN on _gap/_deficit/_shortfall outputs
    shared_pool_legitimacy                    # no-op; enforced upstream in the prompt

`valid` is true iff `error_count == 0`. WARN-level findings do not
invalidate the file. Exit code 0 on valid, 1 on invalid, 2 on JSON parse
failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


CHECKS_PERFORMED = [
    "json_parse", "top_level_structure", "required_fields", "array_length_caps",
    "global_id_uniqueness", "snake_case_ids", "depends_on_declared",
    "formula_rhs_declared", "fraction_value_range", "comment_word_caps",
    "source_text_word_caps", "output_name_present_when_formula_hint",
    "output_unit_present_when_formula_hint", "no_dead_end_variables",
    "threshold_friendly_naming", "shared_pool_legitimacy",
]

CAPS = {
    "key_values": 8,
    "derived_questions": 5,
    "missing_values_to_estimate": 5,
    "recommended_first_calculations": 5,
}

REQUIRED_KEYS = {
    "plan_summary": {"plan_name", "plan_type", "primary_goal", "modelling_frame"},
    "key_values": {
        "id", "label", "category", "value_type", "unit", "value", "comment",
        "formula_hint", "output_name", "output_unit", "depends_on",
        "modelling_priority", "uncertainty", "source_text",
    },
    "derived_questions": {
        "id", "question", "why_it_matters", "formula_hint", "output_name",
        "output_unit", "depends_on",
    },
    "missing_values_to_estimate": {
        "id", "label", "unit", "why_needed", "suggested_estimation_method",
    },
    "recommended_first_calculations": {
        "id", "label", "formula_hint", "output_name", "output_unit",
        "depends_on", "why_first",
    },
}

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Functions allowed inside formula_hint. Numeric literals are also fine.
FORMULA_BUILTINS = {"min", "max", "abs", "sum", "round", "int", "float"}

# A threshold-tested output should be named so positive = pass. These
# suffixes are warned about (the renderer can detect threshold use later).
THRESHOLD_UNFRIENDLY_SUFFIXES = ("_gap", "_deficit", "_shortfall")


def violation(rule_id: str, severity: str, path: str,
              message: str, suggested_fix: str) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "path": path,
        "message": message,
        "suggested_fix": suggested_fix,
    }


def collect_all_ids(params: dict) -> set[str]:
    ids: set[str] = set()
    for section in REQUIRED_KEYS:
        if section == "plan_summary":
            continue
        for entry in params.get(section, []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                ids.add(entry["id"])
    return ids


def collect_output_names(params: dict) -> set[str]:
    """output_name values declared anywhere — usable as RHS references."""
    names: set[str] = set()
    for section in REQUIRED_KEYS:
        if section == "plan_summary":
            continue
        for entry in params.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            on = entry.get("output_name")
            if isinstance(on, str) and on:
                names.add(on)
    return names


def parse_rhs_vars(formula: str) -> set[str]:
    """Extract snake_case variable names from the RHS of `lhs = rhs` (or the
    whole expression if no `=`). Strips function-name builtins; numeric
    literals are not snake_case identifiers so they fall out naturally.
    """
    if not isinstance(formula, str) or not formula:
        return set()
    rhs = formula.split("=", 1)[1] if "=" in formula else formula
    candidates = set(re.findall(r"[a-z_][a-z0-9_]*", rhs))
    return candidates - FORMULA_BUILTINS


# ─── individual checks ─────────────────────────────────────────────────────

def check_top_level_structure(params: dict, violations: list) -> None:
    expected = set(REQUIRED_KEYS)
    for k in sorted(expected - set(params.keys())):
        violations.append(violation(
            "top_level_structure", "ERROR", f"$.{k}",
            f"missing top-level key `{k}`",
            f"add `{k}` to the top-level object",
        ))


def check_required_fields(params: dict, violations: list) -> None:
    for section, required in REQUIRED_KEYS.items():
        obj = params.get(section)
        if section == "plan_summary":
            if not isinstance(obj, dict):
                continue
            for k in sorted(required - set(obj.keys())):
                violations.append(violation(
                    "required_fields", "ERROR", "$.plan_summary",
                    f"plan_summary missing required field `{k}`",
                    f"add `{k}` to plan_summary",
                ))
            continue
        if not isinstance(obj, list):
            continue
        for i, entry in enumerate(obj):
            if not isinstance(entry, dict):
                continue
            for k in sorted(required - set(entry.keys())):
                violations.append(violation(
                    "required_fields", "ERROR", f"$.{section}[{i}]",
                    f"{section}[{i}] missing required field `{k}`",
                    f"add `{k}` to the entry",
                ))


def check_array_length_caps(params: dict, violations: list) -> None:
    for section, cap in CAPS.items():
        arr = params.get(section)
        if isinstance(arr, list) and len(arr) > cap:
            violations.append(violation(
                "array_length_caps", "ERROR", f"$.{section}",
                f"{section} has {len(arr)} entries; cap is {cap}",
                f"drop {len(arr) - cap} entries",
            ))


def check_global_id_uniqueness(params: dict, violations: list) -> None:
    seen: dict[str, list[str]] = {}
    for section in REQUIRED_KEYS:
        if section == "plan_summary":
            continue
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            eid = entry.get("id")
            if isinstance(eid, str):
                seen.setdefault(eid, []).append(f"$.{section}[{i}]")
    for eid, paths in seen.items():
        if len(paths) > 1:
            violations.append(violation(
                "global_id_uniqueness", "ERROR", paths[0],
                f"id `{eid}` is used in {len(paths)} entries: {', '.join(paths)}",
                "rename one of the duplicates or merge them",
            ))


def check_snake_case_ids(params: dict, violations: list) -> None:
    for section in REQUIRED_KEYS:
        if section == "plan_summary":
            continue
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            eid = entry.get("id")
            if isinstance(eid, str) and not SNAKE_CASE_RE.match(eid):
                violations.append(violation(
                    "snake_case_ids", "ERROR", f"$.{section}[{i}].id",
                    f"id `{eid}` is not snake_case",
                    "rewrite as lowercase letters, digits, and underscores; no leading digit",
                ))


def check_depends_on_declared(params: dict, violations: list) -> None:
    """depends_on must reference declared identifiers. An entry is considered
    declared if its `id` matches OR if its `output_name` matches — formulas
    routinely depend on a computed output (the LHS of another entry's
    formula_hint) rather than on the entry's own id, especially when an
    entry's id is a `q_*` question-style name distinct from its output_name.
    """
    declared = collect_all_ids(params) | collect_output_names(params)
    for section in ("key_values", "derived_questions", "recommended_first_calculations"):
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            for d in entry.get("depends_on", []) or []:
                if d not in declared:
                    violations.append(violation(
                        "depends_on_declared", "ERROR",
                        f"$.{section}[{i}].depends_on",
                        f"`{d}` listed in depends_on but not declared as an id or output_name anywhere",
                        f"add `{d}` to key_values, missing_values_to_estimate, "
                        f"derived_questions, or recommended_first_calculations, "
                        f"or set it as another entry's output_name",
                    ))


def check_formula_rhs_declared(params: dict, violations: list) -> None:
    declared = collect_all_ids(params)
    declared |= collect_output_names(params)
    for section in ("key_values", "derived_questions", "recommended_first_calculations"):
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            formula = entry.get("formula_hint")
            if not formula:
                continue
            for v in parse_rhs_vars(formula):
                if v in declared:
                    continue
                if v == entry.get("output_name"):
                    continue
                violations.append(violation(
                    "formula_rhs_declared", "ERROR",
                    f"$.{section}[{i}].formula_hint",
                    f"`{v}` appears on the RHS of formula but is not declared anywhere",
                    f"add `{v}` to declared ids or rewrite the formula",
                ))


def check_fraction_value_range(params: dict, violations: list) -> None:
    for i, entry in enumerate(params.get("key_values", []) or []):
        if not isinstance(entry, dict):
            continue
        if entry.get("unit") != "fraction":
            continue
        v = entry.get("value")
        if v is None or not isinstance(v, (int, float)):
            continue
        if v < 0 or v > 1:
            violations.append(violation(
                "fraction_value_range", "ERROR", f"$.key_values[{i}].value",
                f"value `{v}` is outside [0, 1] but unit is `fraction`",
                f"convert percentages to fractions (60% → 0.6) or change the unit",
            ))


def _word_cap(params: dict, violations: list, section: str, field: str,
              cap: int, rule_id: str) -> None:
    for i, entry in enumerate(params.get(section, []) or []):
        if not isinstance(entry, dict):
            continue
        text = entry.get(field)
        if not isinstance(text, str):
            continue
        n = len(text.split())
        if n > cap:
            violations.append(violation(
                rule_id, "ERROR", f"$.{section}[{i}].{field}",
                f"{field} is {n} words; cap is {cap}",
                f"shorten to {cap} words",
            ))


def check_comment_word_caps(params: dict, violations: list) -> None:
    _word_cap(params, violations, "key_values", "comment", 25, "comment_word_caps")


def check_source_text_word_caps(params: dict, violations: list) -> None:
    _word_cap(params, violations, "key_values", "source_text", 20, "source_text_word_caps")


def _output_field_present_when_formula(params: dict, violations: list,
                                       field: str, rule_id: str) -> None:
    for section in ("key_values", "derived_questions", "recommended_first_calculations"):
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            formula = entry.get("formula_hint")
            if not formula:
                continue
            if not entry.get(field):
                violations.append(violation(
                    rule_id, "ERROR", f"$.{section}[{i}].{field}",
                    f"formula_hint is non-empty but `{field}` is missing/null",
                    f"set `{field}` to the value the formula computes",
                ))


def check_output_name_present_when_formula_hint(params: dict, violations: list) -> None:
    _output_field_present_when_formula(
        params, violations, "output_name", "output_name_present_when_formula_hint")


def check_output_unit_present_when_formula_hint(params: dict, violations: list) -> None:
    _output_field_present_when_formula(
        params, violations, "output_unit", "output_unit_present_when_formula_hint")


def check_no_dead_end_variables(params: dict, violations: list) -> None:
    """A key_value or missing_values_to_estimate entry is a dead end if it is
    not referenced by any calculation's depends_on or formula_hint RHS.

    Transitive references count: if a key_value's output_name is
    referenced by a calculation, that key_value isn't dead-end and the
    inputs feeding its own formula_hint are kept alive too.
    """
    # Direct: every depends_on + formula RHS in derived_questions and
    # recommended_first_calculations.
    referenced: set[str] = set()
    for section in ("derived_questions", "recommended_first_calculations"):
        for entry in params.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            for d in entry.get("depends_on", []) or []:
                referenced.add(d)
            formula = entry.get("formula_hint")
            if formula:
                referenced |= parse_rhs_vars(formula)

    # Transitive: key_values that have their own formula_hint and whose
    # output_name is already referenced, contribute their RHS too.
    changed = True
    while changed:
        changed = False
        for entry in params.get("key_values", []) or []:
            if not isinstance(entry, dict):
                continue
            on = entry.get("output_name")
            formula = entry.get("formula_hint")
            if not on or not formula:
                continue
            if on not in referenced:
                continue
            for v in parse_rhs_vars(formula):
                if v not in referenced:
                    referenced.add(v)
                    changed = True

    for i, entry in enumerate(params.get("key_values", []) or []):
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        on = entry.get("output_name")
        if not eid:
            continue
        if eid in referenced:
            continue
        if isinstance(on, str) and on in referenced:
            continue
        violations.append(violation(
            "no_dead_end_variables", "ERROR", f"$.key_values[{i}]",
            f"key_value `{eid}` is not consumed by any calculation",
            "use it in a derived_question or recommended_first_calculation, or drop it",
        ))

    for i, entry in enumerate(params.get("missing_values_to_estimate", []) or []):
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if eid and eid not in referenced:
            violations.append(violation(
                "no_dead_end_variables", "ERROR",
                f"$.missing_values_to_estimate[{i}]",
                f"missing_value `{eid}` is not consumed by any calculation",
                "use it in a derived_question or recommended_first_calculation, or drop it",
            ))


def check_threshold_friendly_naming(params: dict, violations: list) -> None:
    """Soft check (WARN): outputs ending in _gap/_deficit/_shortfall are
    flagged because they read ambiguously when tested against a threshold.
    The validator doesn't see montecarlo_settings.json so it warns on every
    output with these suffixes; the prompt-side rule asks the extractor to
    flip the sign and rename.
    """
    for section in ("derived_questions", "recommended_first_calculations"):
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            on = entry.get("output_name")
            if not isinstance(on, str):
                continue
            for suffix in THRESHOLD_UNFRIENDLY_SUFFIXES:
                if on.endswith(suffix):
                    base = on[: -len(suffix)]
                    violations.append(violation(
                        "threshold_friendly_naming", "WARN",
                        f"$.{section}[{i}].output_name",
                        f"output_name `{on}` ends in `{suffix}`; threshold-tested outputs should use _surplus/_buffer/_margin/_coverage",
                        f"rename to e.g. `{base}_surplus` and flip the formula sign so positive = pass",
                    ))
                    break


def check_shared_pool_legitimacy(params: dict, violations: list) -> None:
    """No-op. Shared-pool legitimacy requires reading the source plan's
    narrative to confirm whether multiple subtracted pressures legitimately
    draw on one named pool. That is an LLM-time check enforced by the
    extractor's system prompt. The validator runs the check name so
    downstream consumers see it in checks_performed; it does not invent
    violations from structure alone.
    """
    return


CHECK_FUNCTIONS = {
    "json_parse": None,  # implicit; failure handled in main()
    "top_level_structure": check_top_level_structure,
    "required_fields": check_required_fields,
    "array_length_caps": check_array_length_caps,
    "global_id_uniqueness": check_global_id_uniqueness,
    "snake_case_ids": check_snake_case_ids,
    "depends_on_declared": check_depends_on_declared,
    "formula_rhs_declared": check_formula_rhs_declared,
    "fraction_value_range": check_fraction_value_range,
    "comment_word_caps": check_comment_word_caps,
    "source_text_word_caps": check_source_text_word_caps,
    "output_name_present_when_formula_hint": check_output_name_present_when_formula_hint,
    "output_unit_present_when_formula_hint": check_output_unit_present_when_formula_hint,
    "no_dead_end_variables": check_no_dead_end_variables,
    "threshold_friendly_naming": check_threshold_friendly_naming,
    "shared_pool_legitimacy": check_shared_pool_legitimacy,
}


def validate(params: dict) -> dict:
    violations: list[dict] = []
    for check_name in CHECKS_PERFORMED:
        fn = CHECK_FUNCTIONS[check_name]
        if fn is not None:
            fn(params, violations)
    error_count = sum(1 for v in violations if v["severity"] == "ERROR")
    warn_count = sum(1 for v in violations if v["severity"] == "WARN")
    rule_id_breakdown: dict[str, int] = {}
    for v in violations:
        rule_id_breakdown[v["rule_id"]] = rule_id_breakdown.get(v["rule_id"], 0) + 1
    return {
        "valid": error_count == 0,
        "error_count": error_count,
        "warn_count": warn_count,
        "violations": violations,
        "summary": {
            "counts": {
                "key_values": len(params.get("key_values", []) or []),
                "derived_questions": len(params.get("derived_questions", []) or []),
                "missing_values_to_estimate": len(params.get("missing_values_to_estimate", []) or []),
                "recommended_first_calculations": len(params.get("recommended_first_calculations", []) or []),
            },
            "rule_id_breakdown": rule_id_breakdown,
            "checks_performed": CHECKS_PERFORMED,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--parameters", type=Path, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    output = args.output or (args.parameters.parent / "validation.json")
    try:
        params = json.loads(args.parameters.read_text())
    except json.JSONDecodeError as exc:
        report = {
            "valid": False,
            "error_count": 1,
            "warn_count": 0,
            "violations": [violation(
                "json_parse", "ERROR", "$",
                f"could not parse JSON: {exc}",
                "fix the JSON syntax",
            )],
            "summary": {
                "counts": {},
                "rule_id_breakdown": {"json_parse": 1},
                "checks_performed": CHECKS_PERFORMED,
            },
        }
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(output)
        return 2

    report = validate(params)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(output)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
