"""CI tests for experiments/napkin_math/run_monte_carlo.py.

Tests are unittest.TestCase subclasses so the repo's `python test.py`
discovery picks them up. They exercise the runner's small primitives
directly where possible (faster + more focused than spawning a subprocess
per case), and use a hermetic in-memory fixture written to a tmpdir for
end-to-end paths.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

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


def make_bound(**overrides):
    base = {
        "unit": "fraction",
        "low": 0.1,
        "base": 0.2,
        "high": 0.3,
        "rationale": "x",
        "source": "data",
        "sampling_discipline": "fraction",
        "non_negative": True,
        "default_pass_probability": None,
    }
    base.update(overrides)
    return base


def write_fixture(tmpdir: Path, *,
                  key_values: list[dict] | None = None,
                  missing_values: list[dict] | None = None,
                  recommended: list[dict] | None = None,
                  derived: list[dict] | None = None,
                  bounds: dict | None = None,
                  calc_source: str = "") -> dict[str, Path]:
    params = {
        "plan_summary": {"plan_name": "test", "plan_type": "test",
                         "primary_goal": "x", "modelling_frame": "x"},
        "key_values": key_values or [],
        "derived_questions": derived or [],
        "missing_values_to_estimate": missing_values or [],
        "recommended_first_calculations": recommended or [],
    }
    paths = {
        "parameters": tmpdir / "parameters.json",
        "bounds": tmpdir / "bounds.json",
        "calculations": tmpdir / "calculations.py",
        "output": tmpdir / "montecarlo.json",
    }
    paths["parameters"].write_text(json.dumps(params))
    paths["bounds"].write_text(json.dumps(bounds or {}))
    paths["calculations"].write_text(calc_source)
    return paths


def run_with_fixture(tmpdir: Path, **fixture_kwargs):
    settings = fixture_kwargs.pop("_settings", None)
    p = write_fixture(tmpdir, **fixture_kwargs)
    settings_path = None
    if settings is not None:
        settings_path = tmpdir / "settings.json"
        settings_path.write_text(json.dumps(settings))
    return rmc.run(p["parameters"], p["bounds"], p["calculations"], settings_path, p["output"])


class TestSettingsMerging(unittest.TestCase):
    def test_defaults_when_none(self):
        out, warns = rmc.merge_settings(None)
        self.assertEqual(out["n_runs"], 10000)
        self.assertEqual(out["seed"], 12345)
        self.assertEqual(out["distribution_default"], "triangular")
        self.assertEqual(warns, [])

    def test_n_runs_clamped_low(self):
        out, warns = rmc.merge_settings({"n_runs": 5})
        self.assertEqual(out["n_runs"], 10000)
        self.assertTrue(any("n_runs" in w for w in warns))

    def test_n_runs_clamped_high(self):
        out, warns = rmc.merge_settings({"n_runs": 999_999})
        self.assertEqual(out["n_runs"], 10000)
        self.assertTrue(any("n_runs" in w for w in warns))

    def test_n_runs_non_int(self):
        out, warns = rmc.merge_settings({"n_runs": "many"})
        self.assertEqual(out["n_runs"], 10000)
        self.assertTrue(any("n_runs" in w for w in warns))

    def test_seed_non_int(self):
        out, warns = rmc.merge_settings({"seed": "abc"})
        self.assertEqual(out["seed"], 12345)
        self.assertTrue(any("seed" in w for w in warns))

    def test_distribution_default_invalid(self):
        out, warns = rmc.merge_settings({"distribution_default": "gaussian"})
        self.assertEqual(out["distribution_default"], "triangular")
        self.assertTrue(any("distribution_default" in w for w in warns))

    def test_thresholds_pass_through(self):
        thresholds = {"x": {"operator": ">=", "value": 0}}
        out, _ = rmc.merge_settings({"thresholds": thresholds})
        self.assertEqual(out["thresholds"], thresholds)


class TestSamplingDiscipline(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(42)

    def test_fixed_returns_low_value(self):
        bound = make_bound(sampling_discipline="fixed", low=7, base=7, high=7,
                           unit="weeks")
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "v") for _ in range(50)]
        self.assertTrue(all(v == 7 for v in out))

    def test_bernoulli_p_zero_always_low(self):
        bound = make_bound(unit="EUR", low=0, base=1000, high=1000,
                           sampling_discipline="bernoulli_gate",
                           default_pass_probability=0.0)
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "g") for _ in range(200)]
        self.assertTrue(all(v == 0 for v in out))

    def test_bernoulli_p_one_always_high(self):
        bound = make_bound(unit="EUR", low=0, base=1000, high=1000,
                           sampling_discipline="bernoulli_gate",
                           default_pass_probability=1.0)
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "g") for _ in range(200)]
        self.assertTrue(all(v == 1000 for v in out))

    def test_bernoulli_override_takes_precedence(self):
        bound = make_bound(unit="EUR", low=0, base=1000, high=1000,
                           sampling_discipline="bernoulli_gate",
                           default_pass_probability=0.0)
        out = [rmc.sample_one(self.rng, bound, "triangular", {"g": 1.0}, "g")
               for _ in range(200)]
        self.assertTrue(all(v == 1000 for v in out))

    def test_integer_discipline_rounds_and_clamps(self):
        bound = make_bound(unit="people", low=10, base=15, high=20,
                           sampling_discipline="integer")
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "p") for _ in range(500)]
        self.assertTrue(all(v == int(v) for v in out))
        self.assertTrue(all(10 <= v <= 20 for v in out))

    def test_fraction_clamped_to_unit_interval(self):
        bound = make_bound(low=0.0, base=0.5, high=1.0,
                           sampling_discipline="fraction")
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "f") for _ in range(500)]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in out))

    def test_non_negative_clamps_negative_draws(self):
        bound = make_bound(unit="delta", low=-10, base=0, high=10,
                           sampling_discipline="continuous",
                           non_negative=True)
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "x") for _ in range(500)]
        self.assertTrue(all(v >= 0 for v in out))

    def test_continuous_with_negatives_allowed(self):
        bound = make_bound(unit="delta", low=-10, base=0, high=10,
                           sampling_discipline="continuous",
                           non_negative=False)
        out = [rmc.sample_one(self.rng, bound, "triangular", {}, "x") for _ in range(2000)]
        self.assertTrue(any(v < 0 for v in out))
        self.assertTrue(all(-10 <= v <= 10 for v in out))

    def test_lognormal_passes_schema_validation(self):
        """The schema accepts lognormal so that generate-bounds can begin
        emitting it (Phase 4 readiness for the megaproject CAPEX default
        that lands in the prompt-side follow-up)."""
        bound = make_bound(unit="EUR", low=1e6, base=5e6, high=2e7,
                           sampling_discipline="lognormal")
        rmc.validate_bound("capex", bound)

    def test_pert_passes_schema_validation(self):
        bound = make_bound(unit="EUR", low=1e6, base=5e6, high=2e7,
                           sampling_discipline="pert")
        rmc.validate_bound("opex", bound)

    def test_lognormal_sampler_raises_not_implemented(self):
        """Sampling raises loudly until Phase 8 lands the sampler. A silent
        fall-back to triangular would let the user see "100% Robust" on a
        megaproject whose CAPEX bounds are actually fat-tailed — exactly
        the megaproject illusion Phase 4 is laying groundwork to fix."""
        bound = make_bound(unit="EUR", low=1e6, base=5e6, high=2e7,
                           sampling_discipline="lognormal")
        with self.assertRaises(NotImplementedError) as ctx:
            rmc.sample_one(self.rng, bound, "triangular", {}, "capex")
        self.assertIn("lognormal", str(ctx.exception))
        self.assertIn("Phase 8", str(ctx.exception))

    def test_pert_sampler_raises_not_implemented(self):
        bound = make_bound(unit="EUR", low=1e6, base=5e6, high=2e7,
                           sampling_discipline="pert")
        with self.assertRaises(NotImplementedError) as ctx:
            rmc.sample_one(self.rng, bound, "triangular", {}, "opex")
        self.assertIn("pert", str(ctx.exception))


class TestSchemaValidation(unittest.TestCase):
    def test_missing_sampling_discipline(self):
        bound = make_bound()
        del bound["sampling_discipline"]
        with self.assertRaises(rmc.SchemaError) as ctx:
            rmc.validate_bound("v", bound)
        self.assertIn("sampling_discipline", str(ctx.exception))
        self.assertIn("generate-bounds", str(ctx.exception))

    def test_unknown_sampling_discipline(self):
        bound = make_bound(sampling_discipline="bayesian_magic")
        with self.assertRaises(rmc.SchemaError):
            rmc.validate_bound("v", bound)

    def test_missing_non_negative(self):
        bound = make_bound()
        del bound["non_negative"]
        with self.assertRaises(rmc.SchemaError) as ctx:
            rmc.validate_bound("v", bound)
        self.assertIn("non_negative", str(ctx.exception))

    def test_non_negative_must_be_bool(self):
        bound = make_bound(non_negative="yes")
        with self.assertRaises(rmc.SchemaError):
            rmc.validate_bound("v", bound)

    def test_bernoulli_requires_pass_probability(self):
        bound = make_bound(unit="EUR", low=0, base=1, high=1,
                           sampling_discipline="bernoulli_gate",
                           default_pass_probability=None)
        with self.assertRaises(rmc.SchemaError) as ctx:
            rmc.validate_bound("v", bound)
        self.assertIn("default_pass_probability", str(ctx.exception))

    def test_bernoulli_pass_probability_must_be_in_range(self):
        bound = make_bound(unit="EUR", low=0, base=1, high=1,
                           sampling_discipline="bernoulli_gate",
                           default_pass_probability=1.5)
        with self.assertRaises(rmc.SchemaError):
            rmc.validate_bound("v", bound)

    def test_non_bernoulli_must_have_null_pass_probability(self):
        bound = make_bound(default_pass_probability=0.3)
        with self.assertRaises(rmc.SchemaError):
            rmc.validate_bound("v", bound)

    def test_non_numeric_bound_value(self):
        bound = make_bound(low="zero")
        with self.assertRaises(rmc.SchemaError) as ctx:
            rmc.validate_bound("v", bound)
        self.assertIn("non-numeric", str(ctx.exception))

    def test_calculation_entry_missing_output_name(self):
        entry = {"id": "x", "formula_hint": "y = a + b",
                 "output_name": None, "output_unit": "EUR"}
        with self.assertRaises(rmc.SchemaError) as ctx:
            rmc.validate_calculation_entry(entry)
        self.assertIn("output_name", str(ctx.exception))
        self.assertIn("extract-parameters-from-full", str(ctx.exception))

    def test_calculation_entry_missing_output_unit(self):
        entry = {"id": "x", "formula_hint": "y = a + b",
                 "output_name": "y", "output_unit": None}
        with self.assertRaises(rmc.SchemaError) as ctx:
            rmc.validate_calculation_entry(entry)
        self.assertIn("output_unit", str(ctx.exception))


class TestCalculationsExecution(unittest.TestCase):
    def test_function_missing_from_module_warned_and_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            result = run_with_fixture(
                tmpdir,
                key_values=[{
                    "id": "a", "label": "a", "category": "x", "value_type": "explicit",
                    "unit": "EUR", "value": 5, "comment": "x",
                    "formula_hint": None, "output_name": None, "output_unit": None,
                    "depends_on": [], "modelling_priority": "low",
                    "uncertainty": "low", "source_text": "x",
                }],
                recommended=[{
                    "id": "calc1", "label": "calc",
                    "formula_hint": "missing_fn = a + 1",
                    "output_name": "missing_fn", "output_unit": "EUR",
                    "depends_on": ["a"], "why_first": "x",
                }],
                calc_source="",
            )
        self.assertEqual(result["outputs"], {})
        self.assertTrue(any("missing_fn" in w["message"] and "not found" in w["message"]
                            for w in result["warnings"]))

    def test_function_exception_aggregated(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def boomer(a: float) -> float:\n    raise ValueError('nope')\n"
            result = run_with_fixture(
                tmpdir,
                key_values=[{
                    "id": "a", "label": "a", "category": "x", "value_type": "explicit",
                    "unit": "EUR", "value": 5, "comment": "x",
                    "formula_hint": None, "output_name": None, "output_unit": None,
                    "depends_on": [], "modelling_priority": "low",
                    "uncertainty": "low", "source_text": "x",
                }],
                recommended=[{
                    "id": "calc1", "label": "calc",
                    "formula_hint": "boomer = a + 1",
                    "output_name": "boomer", "output_unit": "EUR",
                    "depends_on": ["a"], "why_first": "x",
                }],
                calc_source=calc,
                _settings={"n_runs": 200, "seed": 1},
            )
        # All runs raised; output marked missing
        self.assertEqual(result["outputs"]["boomer"]["count"], 0)
        self.assertEqual(result["outputs"]["boomer"]["missing_count"], 200)
        self.assertTrue(any("ValueError" in w["message"] for w in result["warnings"]))

    def test_function_returning_nan_marked_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "import math\ndef bad(a: float) -> float:\n    return math.nan\n"
            result = run_with_fixture(
                tmpdir,
                key_values=[{
                    "id": "a", "label": "a", "category": "x", "value_type": "explicit",
                    "unit": "EUR", "value": 5, "comment": "x",
                    "formula_hint": None, "output_name": None, "output_unit": None,
                    "depends_on": [], "modelling_priority": "low",
                    "uncertainty": "low", "source_text": "x",
                }],
                recommended=[{
                    "id": "calc1", "label": "calc",
                    "formula_hint": "bad = a",
                    "output_name": "bad", "output_unit": "EUR",
                    "depends_on": ["a"], "why_first": "x",
                }],
                calc_source=calc,
                _settings={"n_runs": 100, "seed": 1},
            )
        self.assertEqual(result["outputs"]["bad"]["count"], 0)

    def test_multi_stage_dependency(self):
        """One calculation feeds the next via the input pool."""
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = (
                "def doubled(a: float) -> float:\n    return a * 2\n"
                "def plus_one(doubled: float) -> float:\n    return doubled + 1\n"
            )
            result = run_with_fixture(
                tmpdir,
                key_values=[{
                    "id": "a", "label": "a", "category": "x", "value_type": "explicit",
                    "unit": "units", "value": 3, "comment": "x",
                    "formula_hint": None, "output_name": None, "output_unit": None,
                    "depends_on": [], "modelling_priority": "low",
                    "uncertainty": "low", "source_text": "x",
                }],
                recommended=[
                    {"id": "c1", "label": "c1",
                     "formula_hint": "doubled = a * 2",
                     "output_name": "doubled", "output_unit": "units",
                     "depends_on": ["a"], "why_first": "x"},
                    {"id": "c2", "label": "c2",
                     "formula_hint": "plus_one = doubled + 1",
                     "output_name": "plus_one", "output_unit": "units",
                     "depends_on": ["doubled"], "why_first": "x"},
                ],
                calc_source=calc,
                _settings={"n_runs": 100, "seed": 1},
            )
        self.assertEqual(result["outputs"]["doubled"]["mean"], 6.0)
        self.assertEqual(result["outputs"]["plus_one"]["mean"], 7.0)


class TestSensitivity(unittest.TestCase):
    def test_single_input_perfect_correlation(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(x: float) -> float:\n    return x * 2\n"
            result = run_with_fixture(
                tmpdir,
                missing_values=[{
                    "id": "x", "label": "x", "unit": "fraction",
                    "why_needed": "x", "suggested_estimation_method": "x",
                }],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = x * 2",
                    "output_name": "out", "output_unit": "fraction",
                    "depends_on": ["x"], "why_first": "x",
                }],
                bounds={"x": make_bound(low=0.1, base=0.5, high=0.9)},
                calc_source=calc,
                _settings={"n_runs": 500, "seed": 1},
            )
        top = result["sensitivity"]["out"]["top_inputs"]
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["id"], "x")
        self.assertAlmostEqual(top[0]["correlation"], 1.0, places=4)

    def test_all_fixed_inputs_yield_empty_sensitivity(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(a: float, b: float) -> float:\n    return a + b\n"
            result = run_with_fixture(
                tmpdir,
                key_values=[
                    {"id": "a", "label": "a", "category": "x", "value_type": "explicit",
                     "unit": "EUR", "value": 3, "comment": "x",
                     "formula_hint": None, "output_name": None, "output_unit": None,
                     "depends_on": [], "modelling_priority": "low",
                     "uncertainty": "low", "source_text": "x"},
                    {"id": "b", "label": "b", "category": "x", "value_type": "explicit",
                     "unit": "EUR", "value": 4, "comment": "x",
                     "formula_hint": None, "output_name": None, "output_unit": None,
                     "depends_on": [], "modelling_priority": "low",
                     "uncertainty": "low", "source_text": "x"},
                ],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = a + b",
                    "output_name": "out", "output_unit": "EUR",
                    "depends_on": ["a", "b"], "why_first": "x",
                }],
                calc_source=calc,
                _settings={"n_runs": 100, "seed": 1},
            )
        self.assertEqual(result["sensitivity"]["out"]["top_inputs"], [])

    def test_fixed_input_with_fp_artifact_value_excluded_from_sensitivity(self):
        """A fixed input whose numeric value triggers np.std floating-point
        artifacts (e.g. 0.15 yields std ~2.8e-17 even when the array is
        constant) must still be filtered. Use np.ptp, not np.std, for the
        constant-array check.
        """
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(constant_fp_artifact: float, x: float) -> float:\n    return constant_fp_artifact + x\n"
            result = run_with_fixture(
                tmpdir,
                key_values=[{
                    "id": "constant_fp_artifact", "label": "k", "category": "x",
                    "value_type": "explicit", "unit": "fraction", "value": 0.15,
                    "comment": "x", "formula_hint": None,
                    "output_name": None, "output_unit": None,
                    "depends_on": [], "modelling_priority": "low",
                    "uncertainty": "low", "source_text": "x",
                }],
                missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                 "why_needed": "x", "suggested_estimation_method": "x"}],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = constant_fp_artifact + x",
                    "output_name": "out", "output_unit": "fraction",
                    "depends_on": ["constant_fp_artifact", "x"], "why_first": "x",
                }],
                bounds={"x": make_bound(low=0.0, base=0.5, high=1.0)},
                calc_source=calc,
                _settings={"n_runs": 500, "seed": 1},
            )
        ids = [t["id"] for t in result["sensitivity"]["out"]["top_inputs"]]
        self.assertNotIn("constant_fp_artifact", ids,
                         "fixed input whose value triggers FP artifact in np.std "
                         "was not filtered; use np.ptp instead")

    def test_unrelated_input_excluded_from_sensitivity(self):
        """An input that varies but doesn't feed the output should not appear."""
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(x: float) -> float:\n    return x * 2\n"
            result = run_with_fixture(
                tmpdir,
                missing_values=[
                    {"id": "x", "label": "x", "unit": "fraction",
                     "why_needed": "x", "suggested_estimation_method": "x"},
                    {"id": "unrelated", "label": "u", "unit": "fraction",
                     "why_needed": "x", "suggested_estimation_method": "x"},
                ],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = x * 2",
                    "output_name": "out", "output_unit": "fraction",
                    "depends_on": ["x"], "why_first": "x",
                }],
                bounds={
                    "x": make_bound(low=0.1, base=0.5, high=0.9),
                    "unrelated": make_bound(low=0.0, base=0.5, high=1.0),
                },
                calc_source=calc,
                _settings={"n_runs": 500, "seed": 1},
            )
        ids = [t["id"] for t in result["sensitivity"]["out"]["top_inputs"]]
        self.assertEqual(ids, ["x"])
        self.assertNotIn("unrelated", ids)


class TestThresholds(unittest.TestCase):
    def _base_fixture(self):
        return dict(
            missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                             "why_needed": "x", "suggested_estimation_method": "x"}],
            recommended=[{
                "id": "c", "label": "c",
                "formula_hint": "out = x",
                "output_name": "out", "output_unit": "fraction",
                "depends_on": ["x"], "why_first": "x",
            }],
            bounds={"x": make_bound(low=0.0, base=0.5, high=1.0)},
            calc_source="def out(x: float) -> float:\n    return x\n",
        )

    def test_ge_operator(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_with_fixture(
                Path(td), **self._base_fixture(),
                _settings={"n_runs": 10000, "seed": 1,
                           "thresholds": {"out": {"operator": ">=", "value": 0.5}}},
            )
        t = result["thresholds"]["out"]
        self.assertEqual(t["valid_count"], 10000)
        self.assertGreater(t["probability"], 0.4)
        self.assertLess(t["probability"], 0.6)

    def test_unsupported_operator_warns_and_skips(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_with_fixture(
                Path(td), **self._base_fixture(),
                _settings={"n_runs": 200, "seed": 1,
                           "thresholds": {"out": {"operator": "~=", "value": 0.5}}},
            )
        self.assertEqual(result["thresholds"], {})
        self.assertTrue(any("unsupported operator" in w["message"] for w in result["warnings"]))

    def test_threshold_on_unknown_output_warns(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_with_fixture(
                Path(td), **self._base_fixture(),
                _settings={"n_runs": 200, "seed": 1,
                           "thresholds": {"ghost": {"operator": ">=", "value": 0}}},
            )
        self.assertEqual(result["thresholds"], {})
        self.assertTrue(any("unknown output" in w["message"] for w in result["warnings"]))

    def test_all_operators_work(self):
        for op in (">", ">=", "<", "<=", "==", "!="):
            with self.subTest(op=op):
                with tempfile.TemporaryDirectory() as td:
                    result = run_with_fixture(
                        Path(td), **self._base_fixture(),
                        _settings={"n_runs": 200, "seed": 1,
                                   "thresholds": {"out": {"operator": op, "value": 0.5}}},
                    )
                self.assertIn("out", result["thresholds"])
                self.assertEqual(result["thresholds"]["out"]["operator"], op)


class TestDeterminism(unittest.TestCase):
    def test_same_seed_byte_identical(self):
        cases = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as td:
                tmpdir = Path(td)
                run_with_fixture(
                    tmpdir,
                    missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                     "why_needed": "x", "suggested_estimation_method": "x"}],
                    recommended=[{
                        "id": "c", "label": "c",
                        "formula_hint": "out = x",
                        "output_name": "out", "output_unit": "fraction",
                        "depends_on": ["x"], "why_first": "x",
                    }],
                    bounds={"x": make_bound(low=0.0, base=0.5, high=1.0)},
                    calc_source="def out(x: float) -> float:\n    return x\n",
                    _settings={"n_runs": 1000, "seed": 42},
                )
                cases.append((tmpdir / "montecarlo.json").read_bytes())
        self.assertEqual(cases[0], cases[1])

    def test_different_seeds_produce_different_output(self):
        cases = []
        for seed in (1, 2):
            with tempfile.TemporaryDirectory() as td:
                tmpdir = Path(td)
                run_with_fixture(
                    tmpdir,
                    missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                     "why_needed": "x", "suggested_estimation_method": "x"}],
                    recommended=[{
                        "id": "c", "label": "c",
                        "formula_hint": "out = x",
                        "output_name": "out", "output_unit": "fraction",
                        "depends_on": ["x"], "why_first": "x",
                    }],
                    bounds={"x": make_bound(low=0.0, base=0.5, high=1.0)},
                    calc_source="def out(x: float) -> float:\n    return x\n",
                    _settings={"n_runs": 1000, "seed": seed},
                )
                cases.append((tmpdir / "montecarlo.json").read_text())
        self.assertNotEqual(cases[0], cases[1])


class TestUnitPropagation(unittest.TestCase):
    def test_output_unit_copied_verbatim(self):
        """A bespoke currency code declared in output_unit must propagate without inference."""
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(x: float) -> float:\n    return x\n"
            result = run_with_fixture(
                tmpdir,
                missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                 "why_needed": "x", "suggested_estimation_method": "x"}],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = x",
                    "output_name": "out", "output_unit": "ZambianKwacha",
                    "depends_on": ["x"], "why_first": "x",
                }],
                bounds={"x": make_bound()},
                calc_source=calc,
                _settings={"n_runs": 200, "seed": 1},
            )
        self.assertEqual(result["outputs"]["out"]["unit"], "ZambianKwacha")

    def test_outputs_of_interest_filters(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = (
                "def out_a(x: float) -> float:\n    return x\n"
                "def out_b(x: float) -> float:\n    return x * 2\n"
            )
            result = run_with_fixture(
                tmpdir,
                missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                 "why_needed": "x", "suggested_estimation_method": "x"}],
                recommended=[
                    {"id": "a", "label": "a",
                     "formula_hint": "out_a = x",
                     "output_name": "out_a", "output_unit": "fraction",
                     "depends_on": ["x"], "why_first": "x"},
                    {"id": "b", "label": "b",
                     "formula_hint": "out_b = x * 2",
                     "output_name": "out_b", "output_unit": "fraction",
                     "depends_on": ["x"], "why_first": "x"},
                ],
                bounds={"x": make_bound()},
                calc_source=calc,
                _settings={"n_runs": 200, "seed": 1, "outputs_of_interest": ["out_a"]},
            )
        self.assertEqual(set(result["outputs"]), {"out_a"})

    def test_outputs_of_interest_unknown_warns(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(x: float) -> float:\n    return x\n"
            result = run_with_fixture(
                tmpdir,
                missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                 "why_needed": "x", "suggested_estimation_method": "x"}],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = x",
                    "output_name": "out", "output_unit": "fraction",
                    "depends_on": ["x"], "why_first": "x",
                }],
                bounds={"x": make_bound()},
                calc_source=calc,
                _settings={"n_runs": 200, "seed": 1,
                           "outputs_of_interest": ["ghost"]},
            )
        self.assertNotIn("ghost", result["outputs"])
        self.assertTrue(any("requested output 'ghost'" in w["message"]
                            for w in result["warnings"]))


class TestEmptyAndDegenerateInputs(unittest.TestCase):
    def test_no_calculations_yields_empty_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            result = run_with_fixture(tmpdir, _settings={"n_runs": 100, "seed": 1})
        self.assertEqual(result["outputs"], {})
        self.assertEqual(result["thresholds"], {})
        self.assertEqual(result["sensitivity"], {})

    def test_low_equals_high_degenerate_continuous(self):
        """A continuous bound with low == base == high should still produce that value."""
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            calc = "def out(x: float) -> float:\n    return x\n"
            bound = make_bound(low=5, base=5, high=5,
                               sampling_discipline="continuous", unit="EUR")
            result = run_with_fixture(
                tmpdir,
                missing_values=[{"id": "x", "label": "x", "unit": "EUR",
                                 "why_needed": "x", "suggested_estimation_method": "x"}],
                recommended=[{
                    "id": "c", "label": "c",
                    "formula_hint": "out = x",
                    "output_name": "out", "output_unit": "EUR",
                    "depends_on": ["x"], "why_first": "x",
                }],
                bounds={"x": bound},
                calc_source=calc,
                _settings={"n_runs": 200, "seed": 1},
            )
        self.assertEqual(result["outputs"]["out"]["mean"], 5.0)
        self.assertEqual(result["outputs"]["out"]["std"], 0.0)


class TestDistributionDefault(unittest.TestCase):
    def test_uniform_setting_produces_different_distribution(self):
        """Uniform draws should have higher variance than triangular for the same bounds."""
        def variance_for(distribution_default: str) -> float:
            with tempfile.TemporaryDirectory() as td:
                tmpdir = Path(td)
                calc = "def out(x: float) -> float:\n    return x\n"
                result = run_with_fixture(
                    tmpdir,
                    missing_values=[{"id": "x", "label": "x", "unit": "fraction",
                                     "why_needed": "x", "suggested_estimation_method": "x"}],
                    recommended=[{
                        "id": "c", "label": "c",
                        "formula_hint": "out = x",
                        "output_name": "out", "output_unit": "fraction",
                        "depends_on": ["x"], "why_first": "x",
                    }],
                    bounds={"x": make_bound(
                        sampling_discipline="continuous",
                        low=0.0, base=0.5, high=1.0,
                    )},
                    calc_source=calc,
                    _settings={"n_runs": 5000, "seed": 1,
                               "distribution_default": distribution_default},
                )
            return result["outputs"]["out"]["std"] ** 2
        # Uniform variance over [0,1] is 1/12 ≈ 0.083; triangular(0,0.5,1) variance is 1/24 ≈ 0.042.
        tri_var = variance_for("triangular")
        uni_var = variance_for("uniform")
        self.assertGreater(uni_var, tri_var)


class TestNewAnalysisBlocks(unittest.TestCase):
    """Smoke tests for the v34 quick-win analyses: binding gates, quartile pass
    rates, required-input thresholds, missing-value priority, model confidence."""

    def _faraday_like_fixture(self, tmpdir: Path) -> dict:
        """Tiny min()-aggregate fixture with three EUR surplus gates."""
        calc = (
            "def gate_a(a: float, b: float) -> float:\n    return a - b\n"
            "def gate_b(c: float, d: float) -> float:\n    return c - d\n"
            "def gate_c(e: float, f: float) -> float:\n    return e - f\n"
            "def weakest_gate(gate_a: float, gate_b: float, gate_c: float) -> float:\n"
            "    return min(gate_a, gate_b, gate_c)\n"
        )
        recommended = [
            {"id": "gate_a", "label": "x",
             "formula_hint": "gate_a = a - b",
             "output_name": "gate_a", "output_unit": "EUR",
             "depends_on": ["a", "b"], "why_first": "x"},
            {"id": "gate_b", "label": "x",
             "formula_hint": "gate_b = c - d",
             "output_name": "gate_b", "output_unit": "EUR",
             "depends_on": ["c", "d"], "why_first": "x"},
            {"id": "gate_c", "label": "x",
             "formula_hint": "gate_c = e - f",
             "output_name": "gate_c", "output_unit": "EUR",
             "depends_on": ["e", "f"], "why_first": "x"},
            {"id": "weakest_gate", "label": "x",
             "formula_hint": "weakest_gate = min(gate_a, gate_b, gate_c)",
             "output_name": "weakest_gate", "output_unit": "EUR",
             "depends_on": ["gate_a", "gate_b", "gate_c"], "why_first": "x"},
        ]
        missing = [{"id": v, "label": "x", "unit": "EUR",
                    "why_needed": "x", "suggested_estimation_method": "x"}
                   for v in "abcdef"]
        # gate_a is the dominant binder: a vs b overlap, gate_a swings near zero;
        # gate_b borderline; gate_c almost always positive.
        bnds = {
            "a": make_bound(unit="EUR", low=80, base=100, high=120, sampling_discipline="continuous"),
            "b": make_bound(unit="EUR", low=90, base=105, high=130, sampling_discipline="continuous"),
            "c": make_bound(unit="EUR", low=80, base=100, high=120, sampling_discipline="continuous"),
            "d": make_bound(unit="EUR", low=85, base=95, high=105, sampling_discipline="continuous"),
            "e": make_bound(unit="EUR", low=500, base=600, high=700, sampling_discipline="continuous"),
            "f": make_bound(unit="EUR", low=10, base=20, high=30, sampling_discipline="continuous"),
        }
        # Mark a/b as data-source, others as assumption to test confidence grading.
        for k in ("a", "b"):
            bnds[k]["source"] = "data"
        for k in ("c", "d", "e", "f"):
            bnds[k]["source"] = "assumption"
        return run_with_fixture(
            tmpdir,
            missing_values=missing,
            recommended=recommended,
            bounds=bnds,
            calc_source=calc,
            _settings={"n_runs": 500, "seed": 1,
                       "thresholds": {"weakest_gate": {"operator": ">=", "value": 0}}},
        )

    def test_binding_gate_identified_for_min_aggregate(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._faraday_like_fixture(Path(td))
        self.assertIn("binding_gate_analysis", result)
        bg = result["binding_gate_analysis"].get("weakest_gate")
        self.assertIsNotNone(bg)
        # gate_a is structurally most negative (a ≪ b), so it should dominate the binding distribution.
        top = bg["binding_when_aggregate_fails"][0]
        self.assertEqual(top["dependency"], "gate_a")
        self.assertGreater(top["frequency"], 0.5)

    def test_quartile_analysis_present_for_thresholds(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._faraday_like_fixture(Path(td))
        self.assertIn("quartile_analysis", result)
        q = result["quartile_analysis"].get("weakest_gate")
        self.assertIsNotNone(q)
        # Every row has the three required keys.
        for row in q:
            self.assertIn("id", row)
            self.assertIn("p_pass_low_quartile", row)
            self.assertIn("p_pass_high_quartile", row)
            self.assertIn("delta_pp", row)

    def test_required_input_thresholds_empty_when_unreachable(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._faraday_like_fixture(Path(td))
        # weakest_gate is structurally infeasible; no single-input restriction reaches 80%.
        self.assertEqual(result["required_input_thresholds"].get("weakest_gate", []), [])

    def test_missing_value_priority_ranks_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._faraday_like_fixture(Path(td))
        mv = result["missing_value_priority"]
        self.assertGreater(len(mv), 0)
        # b drives gate_a (the binding gate); it should rank highly.
        ids = [e["id"] for e in mv[:2]]
        self.assertIn("b", ids)

    def test_model_confidence_grades_present_for_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._faraday_like_fixture(Path(td))
        mc = result["model_confidence"]
        self.assertIn("weakest_gate", mc)
        grade = mc["weakest_gate"]["grade"]
        self.assertIn(grade, {"HIGH", "MEDIUM", "LOW"})
        # 2/6 inputs data-sourced (a, b); under the data-fraction rule that's < 30%, so LOW expected
        # unless bound widths compensate. Either MEDIUM or LOW is acceptable depending on widths.
        self.assertIn(grade, {"LOW", "MEDIUM"})


if __name__ == "__main__":
    unittest.main()
