"""Focused unit tests for the structural rules added in Phase 3.

End-to-end behaviour of the validator is covered by the smoke test
(``check_validate_parameters_end_to_end`` in ``run_smoke.py``); these
tests target the two new rules in isolation by passing minimal in-memory
parameters dicts to ``validate``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


NAPKIN_DIR = Path(__file__).resolve().parent.parent
VALIDATOR_PATH = NAPKIN_DIR / "validate_parameters.py"

spec = importlib.util.spec_from_file_location("validate_parameters", VALIDATOR_PATH)
validate_parameters = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validate_parameters)

validate = validate_parameters.validate
is_pure_sum_formula = validate_parameters.is_pure_sum_formula


PLAN_SUMMARY = {
    "plan_name": "test",
    "plan_type": "test",
    "primary_goal": "test",
    "modelling_frame": "test",
}


def _violations_for(report: dict, rule_id: str) -> list[dict]:
    return [v for v in report["violations"] if v["rule_id"] == rule_id]


# ─── is_pure_sum_formula ──────────────────────────────────────────────────

def test_is_pure_sum_formula_accepts_two_term_sum() -> None:
    assert is_pure_sum_formula("total = a + b") is True


def test_is_pure_sum_formula_accepts_three_term_sum() -> None:
    assert is_pure_sum_formula("total = a + b + c") is True


def test_is_pure_sum_formula_accepts_when_no_lhs() -> None:
    assert is_pure_sum_formula("a + b + c") is True


def test_is_pure_sum_formula_rejects_product() -> None:
    assert is_pure_sum_formula("derived = rate * duration") is False


def test_is_pure_sum_formula_rejects_mixed_operators() -> None:
    # Mixed-operator expressions are out of scope; the unambiguous
    # "aggregate of named parts" pattern only fires on pure sums.
    assert is_pure_sum_formula("net = a + b - c") is False
    assert is_pure_sum_formula("scaled = a * b + c") is False


def test_is_pure_sum_formula_rejects_single_term() -> None:
    assert is_pure_sum_formula("just_a = alpha") is False


def test_is_pure_sum_formula_rejects_constants_in_terms() -> None:
    # 30 is not a snake_case identifier; the rule only fires when every
    # operand is a named variable the rest of the schema can reference.
    assert is_pure_sum_formula("total = a + 30") is False


def test_is_pure_sum_formula_handles_non_string() -> None:
    assert is_pure_sum_formula(None) is False
    assert is_pure_sum_formula(123) is False
    assert is_pure_sum_formula("") is False


# ─── aggregate_not_bounded ─────────────────────────────────────────────────

def test_aggregate_not_bounded_fires_when_sum_lhs_is_also_missing() -> None:
    """The disconnected-aggregates failure: a total computed as a sum of
    named constituents AND also listed in missing_values_to_estimate."""
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [],
        "derived_questions": [],
        "missing_values_to_estimate": [
            {
                "id": "total_cost",
                "label": "Total cost",
                "unit": "USD",
                "why_needed": "Headline total",
                "suggested_estimation_method": "sum of constituents",
            },
        ],
        "recommended_first_calculations": [
            {
                "id": "calc_total_cost",
                "label": "Total cost from constituents",
                "formula_hint": "total_cost = civil_works + remediation + hardware",
                "output_name": "total_cost",
                "output_unit": "USD",
                "depends_on": ["civil_works", "remediation", "hardware"],
                "why_first": "headline gate",
            },
        ],
    }
    report = validate(params)
    fired = _violations_for(report, "aggregate_not_bounded")
    assert len(fired) == 1
    assert fired[0]["severity"] == "ERROR"
    assert "total_cost" in fired[0]["message"]


def test_aggregate_not_bounded_silent_when_no_missing_collision() -> None:
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [],
        "derived_questions": [],
        "missing_values_to_estimate": [
            {
                "id": "civil_works",
                "label": "Civil works",
                "unit": "USD",
                "why_needed": "Constituent of total",
                "suggested_estimation_method": "vendor quote",
            },
        ],
        "recommended_first_calculations": [
            {
                "id": "calc_total_cost",
                "label": "Total cost from constituents",
                "formula_hint": "total_cost = civil_works + remediation + hardware",
                "output_name": "total_cost",
                "output_unit": "USD",
                "depends_on": ["civil_works", "remediation", "hardware"],
                "why_first": "headline gate",
            },
        ],
    }
    report = validate(params)
    assert _violations_for(report, "aggregate_not_bounded") == []


def test_aggregate_not_bounded_silent_when_formula_is_not_pure_sum() -> None:
    """A burn-rate × duration product whose LHS is also a missing value
    is a different (and rarer) failure mode; this check intentionally
    fires only on pure sums to avoid false positives on multiplicative
    decompositions."""
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [],
        "derived_questions": [],
        "missing_values_to_estimate": [
            {
                "id": "holding_cost",
                "label": "Holding cost",
                "unit": "EUR",
                "why_needed": "operational",
                "suggested_estimation_method": "burn × delay",
            },
        ],
        "recommended_first_calculations": [
            {
                "id": "calc_holding_cost",
                "label": "Holding cost",
                "formula_hint": "holding_cost = annual_burn_rate * delay_years",
                "output_name": "holding_cost",
                "output_unit": "EUR",
                "depends_on": ["annual_burn_rate", "delay_years"],
                "why_first": "operational",
            },
        ],
    }
    report = validate(params)
    assert _violations_for(report, "aggregate_not_bounded") == []


# ─── requirement_has_margin ───────────────────────────────────────────────

def test_requirement_has_margin_fires_when_required_kv_has_no_referencing_calc() -> None:
    """A `_required` key value with no calculation consuming it leaves
    the realised-vs-required margin variable undeclared."""
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [
            {
                "id": "buildable_area_required",
                "label": "Buildable area required",
                "category": "capacity",
                "value_type": "explicit",
                "unit": "km2",
                "value": 32.2,
                "comment": "Stated requirement",
                "formula_hint": None,
                "output_name": None,
                "output_unit": None,
                "depends_on": [],
                "modelling_priority": "critical",
                "uncertainty": "low",
                "source_text": "Requires 32.2 km2 to support 9 GW.",
            },
        ],
        "derived_questions": [],
        "missing_values_to_estimate": [],
        "recommended_first_calculations": [],
    }
    report = validate(params)
    fired = _violations_for(report, "requirement_has_margin")
    assert len(fired) == 1
    assert "buildable_area_required" in fired[0]["message"]


def test_requirement_has_margin_silent_when_referenced_in_depends_on() -> None:
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [
            {
                "id": "buildable_area_required",
                "label": "Buildable area required",
                "category": "capacity",
                "value_type": "explicit",
                "unit": "km2",
                "value": 32.2,
                "comment": "Stated requirement",
                "formula_hint": None,
                "output_name": None,
                "output_unit": None,
                "depends_on": [],
                "modelling_priority": "critical",
                "uncertainty": "low",
                "source_text": "Requires 32.2 km2 to support 9 GW.",
            },
        ],
        "derived_questions": [],
        "missing_values_to_estimate": [
            {
                "id": "buildable_area_actual",
                "label": "Realised buildable area",
                "unit": "km2",
                "why_needed": "test against requirement",
                "suggested_estimation_method": "site survey",
            },
        ],
        "recommended_first_calculations": [
            {
                "id": "calc_buildable_surplus",
                "label": "Buildable area surplus",
                "formula_hint": "buildable_area_surplus = buildable_area_actual - buildable_area_required",
                "output_name": "buildable_area_surplus",
                "output_unit": "km2",
                "depends_on": ["buildable_area_actual", "buildable_area_required"],
                "why_first": "primary capacity gate",
            },
        ],
    }
    report = validate(params)
    assert _violations_for(report, "requirement_has_margin") == []


def test_requirement_has_margin_silent_when_referenced_in_formula_rhs_only() -> None:
    """If the requirement is consumed by a formula but not listed in
    depends_on, the validator's depends_on_declared rule will catch the
    omission separately; for requirement_has_margin, formula-RHS
    membership is enough to satisfy 'is referenced by a calculation'."""
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [
            {
                "id": "throughput_per_week_required",
                "label": "Throughput required",
                "category": "operational",
                "value_type": "explicit",
                "unit": "units_per_week",
                "value": 100,
                "comment": "Stated floor",
                "formula_hint": None,
                "output_name": None,
                "output_unit": None,
                "depends_on": [],
                "modelling_priority": "high",
                "uncertainty": "low",
                "source_text": "At least 100 units per week.",
            },
        ],
        "derived_questions": [
            {
                "id": "q_margin",
                "question": "What is the throughput surplus?",
                "why_it_matters": "tests the floor",
                "formula_hint": "throughput_surplus = throughput_actual - throughput_per_week_required",
                "output_name": "throughput_surplus",
                "output_unit": "units_per_week",
                "depends_on": ["throughput_actual"],
            },
        ],
        "missing_values_to_estimate": [
            {
                "id": "throughput_actual",
                "label": "Realised throughput",
                "unit": "units_per_week",
                "why_needed": "tests the floor",
                "suggested_estimation_method": "logged runs",
            },
        ],
        "recommended_first_calculations": [],
    }
    report = validate(params)
    assert _violations_for(report, "requirement_has_margin") == []


def test_requirement_has_margin_silent_when_no_required_key_value() -> None:
    """No `_required` key_value at all → rule is silent. Avoids false
    positives on plans that don't state hard requirements."""
    params = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [
            {
                "id": "throughput_target",
                "label": "Throughput target",
                "category": "operational",
                "value_type": "explicit",
                "unit": "units_per_week",
                "value": 100,
                "comment": "Aspirational target, not a hard floor",
                "formula_hint": None,
                "output_name": None,
                "output_unit": None,
                "depends_on": [],
                "modelling_priority": "high",
                "uncertainty": "medium",
                "source_text": "Aim for 100 units per week.",
            },
        ],
        "derived_questions": [],
        "missing_values_to_estimate": [],
        "recommended_first_calculations": [],
    }
    report = validate(params)
    assert _violations_for(report, "requirement_has_margin") == []


# ─── checks_performed enumeration ─────────────────────────────────────────

def test_validate_lists_all_18_checks() -> None:
    """The validator must report all 18 checks_performed, including the
    two new structural rules. Downstream consumers (summarize_assessment)
    use this list to render the validation card."""
    report = validate({
        "plan_summary": PLAN_SUMMARY,
        "key_values": [],
        "derived_questions": [],
        "missing_values_to_estimate": [],
        "recommended_first_calculations": [],
    })
    checks = report["summary"]["checks_performed"]
    assert len(checks) == 18
    assert "aggregate_not_bounded" in checks
    assert "requirement_has_margin" in checks
