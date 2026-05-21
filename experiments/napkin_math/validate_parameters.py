#!/usr/bin/env python3
"""Deterministic validator for napkin_math parameters.json.

Replaces the LLM-driven `validate-parameters` skill. Reads a
`parameters.json` produced by `extract-parameters-from-digest` (or
`extract-parameters-from-full`) and emits `validation.json` next to it in
the shape that `summarize_assessment.py` consumes (named `checks_performed`
list + per-violation rule_id/severity/path/message/suggested_fix).

19 structural checks are run:

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
    aggregate_not_bounded                     # sum-formula LHS not in missing_values
    requirement_has_margin                    # *_required key_value referenced by a calc
    dropped_signals_schema                    # optional dropped_signals shape + refs

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
    "aggregate_not_bounded", "requirement_has_margin",
    "dropped_signals_schema",
]

CAPS = {
    "key_values": 8,
    "derived_questions": 5,
    "missing_values_to_estimate": 5,
    "recommended_first_calculations": 5,
    "unmodelled_gates": 5,
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
    "unmodelled_gates": {
        "id", "label", "why_it_matters", "source_anchor", "consequence_if_false",
    },
}

# Top-level keys the validator REQUIRES (vs optional). unmodelled_gates is
# optional — older parameters.json files won't have it. dropped_signals
# is optional and only present when the LLM records prior-iteration or
# source-stated absences (proposal 141 PR 2).
OPTIONAL_TOP_LEVEL_KEYS = {"unmodelled_gates", "dropped_signals"}

DROPPED_SIGNAL_REASONS: frozenset[str] = frozenset({
    "replaced_by", "cap_pressure", "out_of_scope",
    "moved_to_unmodelled_gate", "redundant_with",
})

# Hard limit on dropped_signals entries. Above this the extraction
# itself is too lossy and should be redone rather than confessed.
MAX_DROPPED_SIGNALS: int = 8

# Max words in a dropped_signal.rationale.
DROPPED_SIGNAL_RATIONALE_WORD_CAP: int = 25

# Origin values for a dropped_signal entry.
DROPPED_SIGNAL_ORIGINS: frozenset[str] = frozenset({
    "source_digest", "prior_baseline",
})

# Reasons whose semantics require a populated replacement_id.
DROPPED_SIGNAL_REASONS_NEEDING_REPLACEMENT: frozenset[str] = frozenset({
    "replaced_by", "moved_to_unmodelled_gate",
})

# Sections whose entries carry an `id` field. Used by uniqueness, snake_case,
# and reference checks.
SECTIONS_WITH_IDS = (
    "key_values", "derived_questions", "missing_values_to_estimate",
    "recommended_first_calculations", "unmodelled_gates",
)

SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Functions allowed inside formula_hint. Numeric literals are also fine.
FORMULA_BUILTINS = {"min", "max", "abs", "sum", "round", "int", "float"}

# A threshold-tested output should be named so positive = pass. The suffix
# is flagged whether it appears at the very end of output_name or before a
# unit suffix (e.g. `revenue_shortfall_usd`, `funding_gap_eur`,
# `coverage_deficit_dkk`). Matching the bad word as a token — preceded by
# an underscore and followed by either end-of-string or another underscore
# — avoids false positives on names that happen to contain the substring
# elsewhere.
THRESHOLD_UNFRIENDLY_PATTERN = re.compile(r"_(gap|deficit|shortfall)(_[a-z0-9_]+)?$")

# Output-name suffixes recognised as a realised-vs-required margin shape.
# Matched as a token at the end or just before a unit/qualifier suffix.
MARGIN_SUFFIX_PATTERN = re.compile(r"_(margin|surplus|buffer|coverage)(_[a-z0-9_]+)?$")


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
    for section in SECTIONS_WITH_IDS:
        for entry in params.get(section, []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                ids.add(entry["id"])
    return ids


def collect_output_names(params: dict) -> set[str]:
    """output_name values declared anywhere — usable as RHS references."""
    names: set[str] = set()
    for section in SECTIONS_WITH_IDS:
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
    required_top = set(REQUIRED_KEYS) - OPTIONAL_TOP_LEVEL_KEYS
    for k in sorted(required_top - set(params.keys())):
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
        # Optional sections skip when absent; validate shape when present.
        if obj is None and section in OPTIONAL_TOP_LEVEL_KEYS:
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
    for section in SECTIONS_WITH_IDS:
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
    for section in SECTIONS_WITH_IDS:
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
    """Soft check (WARN): outputs containing _gap/_deficit/_shortfall as a
    token (at end, or before a unit suffix like _usd/_eur) are flagged.
    They read ambiguously when tested against a threshold. The validator
    doesn't see montecarlo_settings.json so it warns on every output with
    these suffixes; the prompt-side rule asks the extractor to flip the
    sign and rename.
    """
    for section in ("derived_questions", "recommended_first_calculations"):
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            on = entry.get("output_name")
            if not isinstance(on, str):
                continue
            m = THRESHOLD_UNFRIENDLY_PATTERN.search(on)
            if not m:
                continue
            bad = m.group(1)
            tail = m.group(2) or ""
            base = on[: m.start()]
            suggested = f"{base}_surplus{tail}"
            violations.append(violation(
                "threshold_friendly_naming", "WARN",
                f"$.{section}[{i}].output_name",
                f"output_name `{on}` contains `_{bad}`; threshold-tested outputs should use _surplus/_buffer/_margin/_coverage",
                f"rename to e.g. `{suggested}` and flip the formula sign so positive = pass",
            ))


def check_shared_pool_legitimacy(params: dict, violations: list) -> None:
    """No-op. Shared-pool legitimacy requires reading the source plan's
    narrative to confirm whether multiple subtracted pressures legitimately
    draw on one named pool. That is an LLM-time check enforced by the
    extractor's system prompt. The validator runs the check name so
    downstream consumers see it in checks_performed; it does not invent
    violations from structure alone.
    """
    return


def is_pure_sum_formula(formula: object) -> bool:
    """A formula is a pure sum aggregate when its RHS is a chain of
    snake_case identifiers joined by ``+`` and nothing else. Constants,
    multiplication, division, subtraction, function calls, and unary
    minus all disqualify it. The intent is to flag only the unambiguous
    ``total = A + B + C`` shape — a flat bounded variable for the LHS
    would conflict with the constituent decomposition. Mixed expressions
    like ``A*B + C`` are out of scope here because their semantics are
    not unambiguously "aggregate of the named parts".
    """
    if not isinstance(formula, str) or not formula:
        return False
    rhs = formula.split("=", 1)[1] if "=" in formula else formula
    rhs = rhs.strip()
    while rhs.startswith("(") and rhs.endswith(")"):
        rhs = rhs[1:-1].strip()
    if not rhs or "+" not in rhs:
        return False
    if any(op in rhs for op in ("*", "/", "-")):
        return False
    parts = [p.strip() for p in rhs.split("+")]
    if len(parts) < 2:
        return False
    return all(SNAKE_CASE_RE.match(p) for p in parts)


def check_aggregate_not_bounded(params: dict, violations: list) -> None:
    """A variable computed as a pure sum of named constituents MUST NOT
    also appear in ``missing_values_to_estimate``.

    When a total is sampled independently of its named sub-components, a
    single Monte Carlo trial can pair sub-component p95s with a total
    p05 (or vice versa). The total is a calculation over the
    constituents, not a primitive input that needs estimation.
    """
    missing_ids: set[str] = set()
    for entry in params.get("missing_values_to_estimate", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            missing_ids.add(entry["id"])
    if not missing_ids:
        return
    for section in ("key_values", "derived_questions", "recommended_first_calculations"):
        for i, entry in enumerate(params.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            if not is_pure_sum_formula(entry.get("formula_hint")):
                continue
            output_name = entry.get("output_name")
            if not isinstance(output_name, str):
                continue
            if output_name not in missing_ids:
                continue
            violations.append(violation(
                "aggregate_not_bounded", "ERROR",
                f"$.{section}[{i}].output_name",
                f"`{output_name}` is computed as a sum of named constituents AND also appears in "
                f"missing_values_to_estimate; bounding the aggregate flat lets a single Monte Carlo "
                f"trial pair sub-component p95s with a total p05",
                f"drop `{output_name}` from missing_values_to_estimate (the named constituents are the primitives)",
            ))


def check_requirement_has_margin(params: dict, violations: list) -> None:
    """A key_value whose id ends in ``_required`` names a stated
    requirement floor. At least one calculation must declare a real
    realised-vs-required margin against it. Three properties together
    constitute a margin:

    1. The requirement id appears on the formula RHS (the calculation
       actually consumes the required value).
    2. The formula contains a subtraction or ratio operator (the
       calculation compares the realised quantity to the requirement,
       rather than adding the requirement into an aggregate).
    3. The output_name carries a positive-pass margin suffix
       (``_margin``/``_surplus``/``_buffer``/``_coverage``), so a
       downstream ``>= 0`` threshold reads correctly.

    A bare reference inside a sum (e.g. ``combined = actual + required``)
    consumes the value but does not test whether the realised quantity
    meets the requirement. Without a real margin, the gate defaults to
    ``>= 0`` against an absolute quantity and passes for any non-negative
    realisation regardless of whether it meets the requirement.
    """
    required_kv: list[tuple[int, str]] = []
    for i, entry in enumerate(params.get("key_values", []) or []):
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if isinstance(eid, str) and eid.endswith("_required"):
            required_kv.append((i, eid))
    if not required_kv:
        return
    for i, rid in required_kv:
        satisfied = False
        for section in ("derived_questions", "recommended_first_calculations"):
            for entry in params.get(section, []) or []:
                if not isinstance(entry, dict):
                    continue
                formula = entry.get("formula_hint")
                if not isinstance(formula, str) or not formula:
                    continue
                if rid not in parse_rhs_vars(formula):
                    continue
                rhs = formula.split("=", 1)[1] if "=" in formula else formula
                if "-" not in rhs and "/" not in rhs:
                    continue
                output_name = entry.get("output_name")
                if not isinstance(output_name, str):
                    continue
                if not MARGIN_SUFFIX_PATTERN.search(output_name):
                    continue
                satisfied = True
                break
            if satisfied:
                break
        if satisfied:
            continue
        violations.append(violation(
            "requirement_has_margin", "ERROR",
            f"$.key_values[{i}].id",
            f"key_value `{rid}` names a requirement but no calculation declares a "
            f"realised-vs-required margin against it; expected a derived_question or "
            f"recommended_first_calculation whose formula references `{rid}` with a "
            f"subtraction or ratio operator AND whose output_name ends in "
            f"_margin/_surplus/_buffer/_coverage",
            f"add a calculation like `<base>_margin = <actual> - {rid}` (or "
            f"`<base>_coverage = <actual> / {rid}`) so a >= 0 / >= 1 threshold tests the "
            f"realised value against the requirement; or rename the key_value if it "
            f"isn't actually a requirement",
        ))


def check_dropped_signals_schema(params: dict, violations: list) -> None:
    """Validate the optional ``dropped_signals`` array's shape and
    cross-references. The field is absent on first-iteration extractions
    and on cleanly-preserved iterations; when present each entry must
    name a structural reason from the closed enum and resolve its
    replacement / cap-pressure / redundancy references against current
    ids or output_names. Malformed entries are not acceptable as
    explanations and fire ERROR-level violations.
    """
    obj = params.get("dropped_signals")
    if obj is None:
        return
    if not isinstance(obj, list):
        violations.append(violation(
            "dropped_signals_schema", "ERROR", "$.dropped_signals",
            "dropped_signals must be a list (or absent)",
            "use an array of objects, or omit the field entirely",
        ))
        return
    if len(obj) > MAX_DROPPED_SIGNALS:
        violations.append(violation(
            "dropped_signals_schema", "ERROR", "$.dropped_signals",
            f"dropped_signals has {len(obj)} entries; cap is {MAX_DROPPED_SIGNALS}",
            f"reduce to at most {MAX_DROPPED_SIGNALS} entries — if more drops would need "
            f"recording, the extraction itself is too lossy and should be redone",
        ))
    current_refs = collect_all_ids(params) | collect_output_names(params)
    unmodelled_ids: set[str] = set()
    for entry in params.get("unmodelled_gates", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            unmodelled_ids.add(entry["id"])
    for i, entry in enumerate(obj):
        path = f"$.dropped_signals[{i}]"
        if not isinstance(entry, dict):
            violations.append(violation(
                "dropped_signals_schema", "ERROR", path,
                "dropped_signals entry is not an object",
                "use an object with the documented fields",
            ))
            continue
        reason = entry.get("reason")
        if reason not in DROPPED_SIGNAL_REASONS:
            violations.append(violation(
                "dropped_signals_schema", "ERROR", f"{path}.reason",
                f"reason `{reason}` is not in the closed enum",
                f"use one of {sorted(DROPPED_SIGNAL_REASONS)}",
            ))
        origin = entry.get("origin")
        if origin not in DROPPED_SIGNAL_ORIGINS:
            violations.append(violation(
                "dropped_signals_schema", "ERROR", f"{path}.origin",
                f"origin `{origin}` is not in the closed enum",
                f"use one of {sorted(DROPPED_SIGNAL_ORIGINS)}",
            ))
        eid = entry.get("id")
        if not isinstance(eid, str) or not eid:
            violations.append(violation(
                "dropped_signals_schema", "ERROR", f"{path}.id",
                "id must be a non-empty string (prior signal id or source_claim_id)",
                "supply the prior signal's id",
            ))
        rationale = entry.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            violations.append(violation(
                "dropped_signals_schema", "ERROR", f"{path}.rationale",
                "rationale must be a non-empty structural sentence",
                "name the structural reason in one sentence",
            ))
        elif len(rationale.split()) > DROPPED_SIGNAL_RATIONALE_WORD_CAP:
            violations.append(violation(
                "dropped_signals_schema", "ERROR", f"{path}.rationale",
                f"rationale is {len(rationale.split())} words; cap is "
                f"{DROPPED_SIGNAL_RATIONALE_WORD_CAP}",
                f"shorten to {DROPPED_SIGNAL_RATIONALE_WORD_CAP} words",
            ))
        if reason in DROPPED_SIGNAL_REASONS_NEEDING_REPLACEMENT:
            rid = entry.get("replacement_id")
            if not isinstance(rid, str) or not rid:
                violations.append(violation(
                    "dropped_signals_schema", "ERROR", f"{path}.replacement_id",
                    f"reason `{reason}` requires a non-empty replacement_id",
                    "set replacement_id to the current id or output_name that replaces this signal",
                ))
            elif reason == "replaced_by" and rid not in current_refs:
                violations.append(violation(
                    "dropped_signals_schema", "ERROR", f"{path}.replacement_id",
                    f"replacement_id `{rid}` does not match any current id or output_name",
                    "rename to an existing current id/output_name, or drop the entry",
                ))
            elif reason == "moved_to_unmodelled_gate" and rid not in unmodelled_ids:
                violations.append(violation(
                    "dropped_signals_schema", "ERROR", f"{path}.replacement_id",
                    f"replacement_id `{rid}` does not match any unmodelled_gates id",
                    "set replacement_id to an existing unmodelled_gates entry id",
                ))
        if reason == "redundant_with":
            rid = entry.get("redundant_with_id")
            if not isinstance(rid, str) or not rid:
                violations.append(violation(
                    "dropped_signals_schema", "ERROR", f"{path}.redundant_with_id",
                    "reason `redundant_with` requires a non-empty redundant_with_id",
                    "set redundant_with_id to the current id or output_name that subsumes this signal",
                ))
            elif rid not in current_refs:
                violations.append(violation(
                    "dropped_signals_schema", "ERROR", f"{path}.redundant_with_id",
                    f"redundant_with_id `{rid}` does not match any current id or output_name",
                    "rename to an existing current id/output_name, or drop the entry",
                ))
        if reason == "cap_pressure":
            cap_kind = entry.get("cap_kind")
            if cap_kind not in CAPS:
                violations.append(violation(
                    "dropped_signals_schema", "ERROR", f"{path}.cap_kind",
                    f"cap_kind `{cap_kind}` is not a capped array name",
                    f"use one of {sorted(CAPS)}",
                ))
            else:
                cap_size = CAPS[cap_kind]
                actual_size = len(params.get(cap_kind, []) or [])
                if actual_size < cap_size:
                    violations.append(violation(
                        "dropped_signals_schema", "ERROR", f"{path}.cap_kind",
                        f"cap_pressure claim is not justified: `{cap_kind}` has "
                        f"{actual_size} entries, below cap {cap_size}",
                        f"drop this dropped_signals entry, or fill the `{cap_kind}` "
                        f"array to its cap with the dropped signal first",
                    ))


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
    "aggregate_not_bounded": check_aggregate_not_bounded,
    "requirement_has_margin": check_requirement_has_margin,
    "dropped_signals_schema": check_dropped_signals_schema,
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
                "unmodelled_gates": len(params.get("unmodelled_gates", []) or []),
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
