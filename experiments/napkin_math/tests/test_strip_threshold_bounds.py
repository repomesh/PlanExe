"""CI tests for strip_threshold_bounds in run_monte_carlo.py.

These cover the deterministic post-processor that removes threshold/target
variables from a bounds dict before the Monte Carlo simulation consumes it.
Background and motivation are in the function's own docstring and in PR #732
/ PR #733 / the v46-v48 case study.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

NAPKIN_DIR = Path(__file__).resolve().parent.parent
RUNNER_PATH = NAPKIN_DIR / "run_monte_carlo.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("napkin_monte_carlo", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("napkin_monte_carlo", module)
    spec.loader.exec_module(module)
    return module


rmc = _load_runner()


def _bound(**overrides):
    base = {
        "unit": "fraction",
        "low": 0.1,
        "base": 0.2,
        "high": 0.3,
        "rationale": "test fixture",
        "source": "data",
        "sampling_discipline": "fraction",
        "non_negative": True,
        "default_pass_probability": None,
    }
    base.update(overrides)
    return base


class StripBySuffixTests(unittest.TestCase):
    def test_strips_threshold_suffix(self):
        bounds = {
            "public_compliance_threshold": _bound(),
            "actual_public_compliance_share": _bound(),
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, {})
        self.assertEqual(set(cleaned), {"actual_public_compliance_share"})
        self.assertEqual(
            stripped, [{"id": "public_compliance_threshold", "reason": "suffix"}]
        )

    def test_strips_all_suffix_variants(self):
        bounds = {
            "x_threshold": _bound(),
            "x_target": _bound(),
            "x_ceiling": _bound(),
            "x_floor": _bound(),
            "x_limit": _bound(),
            "x_cap": _bound(),
            "x_max": _bound(),
            "x_min": _bound(),
            "x_share": _bound(),  # not in suffix list → kept
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, {})
        self.assertEqual(list(cleaned), ["x_share"])
        self.assertEqual(len(stripped), 8)
        self.assertTrue(all(s["reason"] == "suffix" for s in stripped))

    def test_actual_prefix_overrides_suffix(self):
        """An `actual_*` id is never stripped, even with a threshold-like suffix."""
        bounds = {"actual_some_limit": _bound()}
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, {})
        self.assertEqual(set(cleaned), {"actual_some_limit"})
        self.assertEqual(stripped, [])


class StripByFormulaSideTests(unittest.TestCase):
    def test_strips_subtraction_subtrahend(self):
        """Standard pattern: `actual_X - X_target` → X_target is threshold."""
        params = {
            "recommended_first_calculations": [{
                "formula_hint":
                    "n95_staging_margin = actual_n95_staging_share "
                    "- n95_staging_target_share",
            }],
        }
        bounds = {
            "actual_n95_staging_share": _bound(),
            "n95_staging_target_share": _bound(),
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        self.assertEqual(set(cleaned), {"actual_n95_staging_share"})
        self.assertEqual(
            stripped,
            [{"id": "n95_staging_target_share", "reason": "formula-side"}],
        )

    def test_strips_subtraction_minuend(self):
        """Reversed pattern: `X_max - actual_X` → X_max is threshold."""
        params = {
            "recommended_first_calculations": [{
                "formula_hint":
                    "budget_surplus_usd = budget_max_usd "
                    "- actual_total_project_cost_usd",
            }],
        }
        bounds = {
            "actual_total_project_cost_usd": _bound(),
            "budget_max_usd": _bound(),
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        # budget_max_usd ends in `_usd`, not in any suffix in THRESHOLD_SUFFIXES,
        # so the suffix check doesn't fire. The formula-side check catches it
        # because it appears on the threshold side of `X_max - actual_Y`.
        self.assertEqual(set(cleaned), {"actual_total_project_cost_usd"})
        self.assertEqual(
            stripped, [{"id": "budget_max_usd", "reason": "formula-side"}]
        )

    def test_does_not_strip_coefficients_in_multiplicative_formula(self):
        """Coefficients in a product are not thresholds."""
        params = {
            "recommended_first_calculations": [{
                "formula_hint":
                    "people_protected = vulnerable_population_share "
                    "* leipzig_total_population * protection_conversion_rate",
            }],
        }
        bounds = {
            "vulnerable_population_share": _bound(),
            "leipzig_total_population": _bound(),
            "protection_conversion_rate": _bound(),
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(stripped, [])

    def test_does_not_strip_min_aggregate_operands(self):
        """`min()` aggregates aren't binary subtractions."""
        params = {
            "recommended_first_calculations": [{
                "formula_hint": "overall_margin = min(margin_a, margin_b)",
            }],
        }
        bounds = {
            "margin_a": _bound(),
            "margin_b": _bound(),
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(stripped, [])

    def test_does_not_strip_when_both_sides_actual(self):
        """`actual_A - actual_B` is ambiguous — leave both alone."""
        params = {
            "recommended_first_calculations": [{
                "formula_hint": "diff = actual_a - actual_b",
            }],
        }
        bounds = {"actual_a": _bound(), "actual_b": _bound()}
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(stripped, [])

    def test_scans_derived_questions(self):
        """Margin formulas declared in derived_questions are also scanned."""
        params = {
            "derived_questions": [{
                "formula_hint": "m = actual_v - v_target_share",
            }],
        }
        bounds = {"actual_v": _bound(), "v_target_share": _bound()}
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        self.assertEqual(set(cleaned), {"actual_v"})
        self.assertEqual(
            stripped, [{"id": "v_target_share", "reason": "formula-side"}]
        )


class CombinedTests(unittest.TestCase):
    def test_does_not_mutate_input(self):
        bounds = {"x_threshold": _bound(), "actual_x": _bound()}
        before = {k: dict(v) for k, v in bounds.items()}
        rmc.strip_threshold_bounds(bounds, {})
        self.assertEqual(bounds, before)

    def test_empty_inputs(self):
        cleaned, stripped = rmc.strip_threshold_bounds({}, {})
        self.assertEqual(cleaned, {})
        self.assertEqual(stripped, [])

    def test_yellowstone_v48_regression(self):
        """Both stubborn variables from Yellowstone v48 are removed.

        Suffix    → public_compliance_threshold
        Formula   → n95_staging_target_share (ends in _share, no suffix
                    match; caught by appearing on the threshold side of a
                    declared margin formula)
        """
        params = {
            "recommended_first_calculations": [
                {
                    "formula_hint":
                        "public_compliance_margin = "
                        "actual_public_compliance_share "
                        "- public_compliance_threshold",
                },
                {
                    "formula_hint":
                        "n95_staging_margin = actual_n95_staging_share "
                        "- n95_staging_target_share",
                },
            ],
        }
        bounds = {
            "actual_public_compliance_share": _bound(),
            "actual_n95_staging_share": _bound(),
            "public_compliance_threshold": _bound(),
            "n95_staging_target_share": _bound(),
        }
        cleaned, stripped = rmc.strip_threshold_bounds(bounds, params)
        self.assertEqual(
            set(cleaned),
            {"actual_public_compliance_share", "actual_n95_staging_share"},
        )
        stripped_ids = {s["id"]: s["reason"] for s in stripped}
        self.assertEqual(stripped_ids, {
            "public_compliance_threshold": "suffix",
            "n95_staging_target_share": "formula-side",
        })


if __name__ == "__main__":
    unittest.main()
