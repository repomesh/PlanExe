"""Focused unit tests for audit_source_preservation.py (Fork B advisory).

Synthetic fixtures only — no corpus literals. Each test passes minimal
in-memory parameters dicts to ``audit()`` and inspects the structured
report.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


NAPKIN_DIR = Path(__file__).resolve().parent.parent
AUDIT_PATH = NAPKIN_DIR / "audit_source_preservation.py"

spec = importlib.util.spec_from_file_location("audit_source_preservation", AUDIT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _kv(eid: str, **extra: object) -> dict[str, object]:
    """Build a synthetic key_values entry with just the fields the audit
    looks at."""
    return {
        "id": eid,
        "label": extra.get("label", eid),
        "category": extra.get("category", "test"),
        "value_type": extra.get("value_type", "explicit"),
        "unit": extra.get("unit", "test_unit"),
        "value": extra.get("value", 1.0),
        "comment": extra.get("comment", ""),
        "formula_hint": extra.get("formula_hint"),
        "output_name": extra.get("output_name"),
        "output_unit": extra.get("output_unit"),
        "depends_on": extra.get("depends_on", []),
        "modelling_priority": extra.get("modelling_priority", "medium"),
        "uncertainty": extra.get("uncertainty", "low"),
        "source_text": extra.get("source_text", ""),
    }


def _mv(eid: str) -> dict[str, object]:
    return {
        "id": eid,
        "label": eid,
        "unit": "test_unit",
        "why_needed": "test",
        "suggested_estimation_method": "test",
    }


def _calc(eid: str, *, output_name: str, formula: str,
          depends_on: list[str] | None = None) -> dict[str, object]:
    return {
        "id": eid,
        "label": eid,
        "formula_hint": formula,
        "output_name": output_name,
        "output_unit": "test_unit",
        "depends_on": depends_on or [],
        "why_first": "test",
    }


PLAN_SUMMARY = {
    "plan_name": "synthetic",
    "plan_type": "synthetic",
    "primary_goal": "test",
    "modelling_frame": "test",
}


def _build(**sections: object) -> dict[str, object]:
    base: dict[str, object] = {
        "plan_summary": PLAN_SUMMARY,
        "key_values": [],
        "derived_questions": [],
        "missing_values_to_estimate": [],
        "recommended_first_calculations": [],
    }
    base.update(sections)
    return base


# ─── preserved_by_id ──────────────────────────────────────────────────────

def test_preserved_by_id_when_same_id_present_in_current() -> None:
    prior = _build(key_values=[_kv("alpha"), _kv("beta")])
    current = _build(key_values=[_kv("alpha"), _kv("beta"), _kv("gamma")])
    report = mod.audit(prior, current)
    assert report["summary"]["preserved_by_id"] == 2
    assert report["summary"]["absent_unexplained"] == 0
    statuses = {d["prior_name"]: d["status"] for d in report["details"]}
    assert statuses == {"alpha": "preserved_by_id", "beta": "preserved_by_id"}


# ─── preserved_by_output_name ─────────────────────────────────────────────

def test_preserved_by_output_name_when_primitive_became_a_calculation() -> None:
    """Rename pattern: a prior key_value (primitive) is removed and a
    current calculation now produces the same name as its output_name.
    Downstream binders look at output_name, so the signal IS preserved
    — but now it is a computed quantity rather than a sampled input."""
    prior = _build(key_values=[_kv("burn_rate_per_month")])
    current = _build(
        recommended_first_calculations=[
            _calc(
                "c_burn",
                output_name="burn_rate_per_month",
                formula="burn_rate_per_month = annual_burn / 12",
                depends_on=["annual_burn"],
            ),
        ],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["preserved_by_output_name"] == 1
    assert report["summary"]["preserved_by_id"] == 0
    assert report["summary"]["absent_unexplained"] == 0


# ─── preserved_as_formula_dependency ──────────────────────────────────────

def test_preserved_as_formula_dependency_when_used_on_rhs() -> None:
    """The prior key_value is no longer declared directly in the current
    artifact, but a current formula RHS still references the same token.
    The signal is alive as an input to a calculation."""
    prior = _build(key_values=[_kv("burn_rate_per_month")])
    current = _build(
        recommended_first_calculations=[
            _calc("c_holding", output_name="holding_cost",
                  formula="holding_cost = burn_rate_per_month * months_delay",
                  depends_on=["months_delay"]),
        ],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["preserved_as_formula_dependency"] == 1


def test_preserved_as_formula_dependency_when_in_depends_on() -> None:
    prior = _build(key_values=[_kv("vendor_quote_eur")])
    current = _build(
        recommended_first_calculations=[
            _calc("c_total", output_name="total_eur",
                  formula="total_eur = some_other_var",
                  depends_on=["vendor_quote_eur", "some_other_var"]),
        ],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["preserved_as_formula_dependency"] == 1


# ─── likely_renamed ───────────────────────────────────────────────────────

def test_likely_renamed_when_token_overlap_above_threshold() -> None:
    """``actual_outreach_contact_rate`` → ``outreach_contact_rate_target``:
    3 of 5 tokens overlap (outreach, contact, rate). Jaccard = 3/5 = 0.6,
    above the 0.4 threshold."""
    prior = _build(key_values=[_kv("actual_outreach_contact_rate")])
    current = _build(key_values=[_kv("outreach_contact_rate_target")])
    report = mod.audit(prior, current)
    assert report["summary"]["likely_renamed"] == 1
    detail = next(d for d in report["details"] if d["status"] == "likely_renamed")
    assert detail["prior_name"] == "actual_outreach_contact_rate"
    cand_ids = [c["id"] for c in detail["candidates"]]
    assert "outreach_contact_rate_target" in cand_ids


def test_likely_renamed_ranks_multiple_candidates_descending() -> None:
    """When multiple current ids overlap with the prior, the audit
    returns up to MAX_RENAME_CANDIDATES candidates sorted by overlap."""
    prior = _build(key_values=[_kv("alpha_beta_gamma")])
    current = _build(
        key_values=[
            _kv("alpha_beta_gamma_delta"),  # 3/4 overlap
            _kv("alpha_beta_epsilon"),       # 2/4 overlap = 0.5
            _kv("unrelated"),                # 0 overlap
        ],
    )
    report = mod.audit(prior, current)
    detail = next(d for d in report["details"] if d["status"] == "likely_renamed")
    cand_ids = [c["id"] for c in detail["candidates"]]
    assert cand_ids[0] == "alpha_beta_gamma_delta"
    assert cand_ids[1] == "alpha_beta_epsilon"
    # The unrelated id falls below threshold and is excluded.
    assert "unrelated" not in cand_ids


# ─── absent_unexplained ───────────────────────────────────────────────────

def test_absent_unexplained_when_no_overlap() -> None:
    prior = _build(key_values=[_kv("orphan_alpha_token")])
    current = _build(key_values=[_kv("completely_different_id")])
    report = mod.audit(prior, current)
    assert report["summary"]["absent_unexplained"] == 1
    detail = next(d for d in report["details"]
                  if d["status"] == "absent_unexplained")
    assert detail["prior_name"] == "orphan_alpha_token"


def test_absent_unexplained_when_current_is_empty() -> None:
    prior = _build(
        key_values=[_kv("alpha")],
        missing_values_to_estimate=[_mv("beta")],
    )
    current = _build()
    report = mod.audit(prior, current)
    assert report["summary"]["prior_total"] == 2
    assert report["summary"]["absent_unexplained"] == 2


# ─── empty inputs ─────────────────────────────────────────────────────────

def test_empty_prior_yields_zero_signals() -> None:
    report = mod.audit(_build(), _build())
    assert report["summary"]["prior_total"] == 0
    assert report["details"] == []


# ─── cross-section preservation ───────────────────────────────────────────

def test_preserved_by_id_across_sections() -> None:
    """A signal moved from key_values to unmodelled_gates is still
    preserved_by_id — the audit looks across all five sections."""
    prior = _build(key_values=[_kv("regulatory_floor_id")])
    current = _build(
        unmodelled_gates=[{
            "id": "regulatory_floor_id",
            "label": "Regulatory floor",
            "why_it_matters": "test",
            "source_anchor": "assumptions",
            "consequence_if_false": "test",
        }],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["preserved_by_id"] == 1


# ─── render_text_report smoke ─────────────────────────────────────────────

def test_text_report_renders_summary_and_sections() -> None:
    prior = _build(
        key_values=[
            _kv("alpha"),                     # preserved_by_id
            _kv("orphan_x"),                  # absent_unexplained
            _kv("renamed_alpha_beta"),        # likely_renamed
        ],
    )
    current = _build(
        key_values=[
            _kv("alpha"),
            _kv("renamed_alpha_beta_delta"),  # likely_renamed target
        ],
    )
    report = mod.audit(prior, current)
    text = mod.render_text_report(report)
    assert "Source-preservation audit" in text
    assert "preserved_by_id" in text
    assert "LIKELY RENAMED:" in text
    assert "ABSENT UNEXPLAINED:" in text
    assert "orphan_x" in text
    assert "renamed_alpha_beta" in text


# ─── output_name as first-class signal ────────────────────────────────────

def test_output_name_drift_on_preserved_id_is_reported() -> None:
    """Review feedback on PR #751 (first round): a calc whose entry id
    survives but whose output_name changes is a genuine signal
    regression — downstream binders bind by output_name, not by entry
    id. The audit must report the lost prior output_name as a separate
    signal, even though the id is preserved."""
    prior = _build(
        derived_questions=[{
            "id": "q_margin",
            "question": "What is the margin?",
            "why_it_matters": "test",
            "formula_hint": "old_margin = actual - threshold",
            "output_name": "old_margin",
            "output_unit": "test_unit",
            "depends_on": ["actual", "threshold"],
        }],
    )
    current = _build(
        derived_questions=[{
            "id": "q_margin",
            "question": "What is the margin?",
            "why_it_matters": "test",
            "formula_hint": "new_margin = actual - threshold",
            "output_name": "new_margin",
            "output_unit": "test_unit",
            "depends_on": ["actual", "threshold"],
        }],
    )
    report = mod.audit(prior, current)
    # Two prior signals: the entry id ``q_margin`` and the output_name
    # ``old_margin``. The id survives; the output_name does not.
    assert report["summary"]["prior_total"] == 2
    statuses = {d["prior_name"]: d["status"] for d in report["details"]}
    assert statuses["q_margin"] == "preserved_by_id"
    assert statuses["old_margin"] == "absent_unexplained"
    old_margin_detail = next(
        d for d in report["details"] if d["prior_name"] == "old_margin"
    )
    assert old_margin_detail["prior_kind"] == "output_name"


def test_rename_candidates_drawn_from_output_names_too() -> None:
    """Mars-style restructures often rename a prior id to a new
    output_name. Rename candidates must be searchable across both
    current ids and current output_names so the audit can suggest the
    output_name as a plausible target."""
    prior = _build(key_values=[_kv("year1_revenue_surplus_usd")])
    current = _build(
        recommended_first_calculations=[
            _calc(
                "c_surplus",
                output_name="year1_viability_surplus_usd",
                formula="year1_viability_surplus_usd = revenue - cost",
                depends_on=["revenue", "cost"],
            ),
        ],
    )
    report = mod.audit(prior, current)
    detail = next(
        d for d in report["details"]
        if d["prior_name"] == "year1_revenue_surplus_usd"
    )
    assert detail["status"] == "likely_renamed"
    cand_ids = [c["id"] for c in detail["candidates"]]
    assert "year1_viability_surplus_usd" in cand_ids


# ─── jaccard primitive ────────────────────────────────────────────────────

def test_jaccard_token_overlap_primitive() -> None:
    assert mod.jaccard(set(), set()) == 0.0
    assert mod.jaccard({"a"}, set()) == 0.0
    assert mod.jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert mod.jaccard({"a", "b"}, {"a", "c"}) == 1 / 3


def test_parse_rhs_tokens_handles_assignment_and_builtins() -> None:
    tokens = mod.parse_rhs_tokens("lhs = max(a, b) + c * 2")
    # Builtins ``max`` filtered out; numeric literals are not snake_case
    # identifiers and fall out naturally.
    assert tokens == {"a", "b", "c"}


def test_parse_rhs_tokens_handles_expression_without_assignment() -> None:
    tokens = mod.parse_rhs_tokens("a + b - c")
    assert tokens == {"a", "b", "c"}


def test_parse_rhs_tokens_returns_empty_for_non_string() -> None:
    assert mod.parse_rhs_tokens(None) == set()
    assert mod.parse_rhs_tokens("") == set()


# ─── explained_drop (dropped_signals consumption) ─────────────────────────

def _dropped(eid: str, **overrides) -> dict:
    base = {
        "id": eid,
        "origin": "prior_baseline",
        "source_anchor": "prior_baseline",
        "expected_section": "key_values",
        "dropped_from": "key_values",
        "reason": "replaced_by",
        "replacement_id": "alpha",
        "redundant_with_id": None,
        "cap_kind": None,
        "rationale": "replaced by an equivalent computed quantity",
    }
    base.update(overrides)
    return base


def test_explained_drop_reclassifies_absent_signal_with_replaced_by() -> None:
    """When the current artifact's dropped_signals names a prior id and
    points at an existing replacement, the audit reclassifies the prior
    signal from absent_unexplained to explained_drop."""
    prior = _build(key_values=[_kv("orphan_token_alpha")])
    current = _build(
        key_values=[_kv("alpha")],
        dropped_signals=[_dropped("orphan_token_alpha", replacement_id="alpha")],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["explained_drop"] == 1
    assert report["summary"]["absent_unexplained"] == 0
    detail = next(d for d in report["details"]
                  if d["status"] == "explained_drop")
    assert detail["reason"] == "replaced_by"
    assert detail["replacement_id"] == "alpha"


def test_explained_drop_outranks_likely_renamed() -> None:
    """When a prior id has BOTH a high-token-overlap rename candidate
    AND a dropped_signals entry, the explained_drop classification wins
    because the LLM named a specific structural reason."""
    prior = _build(key_values=[_kv("alpha_beta_gamma")])
    current = _build(
        key_values=[_kv("alpha_beta_gamma_delta")],
        dropped_signals=[
            _dropped("alpha_beta_gamma", replacement_id="alpha_beta_gamma_delta"),
        ],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["explained_drop"] == 1
    assert report["summary"]["likely_renamed"] == 0


def test_explained_drop_ignored_when_id_is_actually_preserved() -> None:
    """If the LLM over-records (drops_signals names a prior id that IS
    in current), the audit prefers the preservation evidence — the
    explained_drop entry is silently ignored. Avoids double-counting."""
    prior = _build(key_values=[_kv("alpha")])
    current = _build(
        key_values=[_kv("alpha")],
        dropped_signals=[_dropped("alpha", replacement_id="alpha")],
    )
    report = mod.audit(prior, current)
    assert report["summary"]["preserved_by_id"] == 1
    assert report["summary"]["explained_drop"] == 0


def test_explained_drop_silently_skips_malformed_entry() -> None:
    """Malformed dropped_signals entries (unknown reason, missing id,
    etc.) are silently skipped by the audit — validate_parameters is
    the right place to surface them. The audit should not crash or
    promote a malformed entry into a false explained_drop."""
    prior = _build(key_values=[_kv("orphan_token_alpha")])
    current = _build(
        key_values=[_kv("alpha")],
        dropped_signals=[{
            "id": "orphan_token_alpha",
            "origin": "prior_baseline",
            "reason": "garbage_reason",  # not in closed enum
            "rationale": "garbage",
        }],
    )
    report = mod.audit(prior, current)
    # Malformed entry ignored → prior signal falls through to
    # absent_unexplained (no rename candidate available).
    assert report["summary"]["explained_drop"] == 0
    assert report["summary"]["absent_unexplained"] == 1


def test_explained_drop_handles_cap_pressure_reason() -> None:
    """A cap_pressure drop is a legitimate explained_drop — the LLM did
    consider the signal but couldn't fit it under the cap."""
    prior = _build(key_values=[_kv("orphan_cap_pressured_token")])
    current = _build(
        key_values=[],
        dropped_signals=[
            _dropped(
                "orphan_cap_pressured_token",
                reason="cap_pressure",
                cap_kind="key_values",
                replacement_id=None,
                rationale="dropped under key_values cap pressure",
            ),
        ],
    )
    report = mod.audit(prior, current)
    detail = next(d for d in report["details"]
                  if d["status"] == "explained_drop")
    assert detail["reason"] == "cap_pressure"
    assert detail["cap_kind"] == "key_values"


def test_explained_drop_handles_moved_to_unmodelled_gate() -> None:
    prior = _build(key_values=[_kv("orphan_token_promoted_to_gate")])
    current = _build(
        unmodelled_gates=[{
            "id": "orphan_gate_id",
            "label": "Promoted gate",
            "why_it_matters": "test",
            "source_anchor": "assumptions",
            "consequence_if_false": "test",
        }],
        dropped_signals=[
            _dropped(
                "orphan_token_promoted_to_gate",
                reason="moved_to_unmodelled_gate",
                replacement_id="orphan_gate_id",
                rationale="re-categorised as binary regulatory gate",
            ),
        ],
    )
    report = mod.audit(prior, current)
    detail = next(d for d in report["details"]
                  if d["status"] == "explained_drop")
    assert detail["reason"] == "moved_to_unmodelled_gate"
    assert detail["replacement_id"] == "orphan_gate_id"
