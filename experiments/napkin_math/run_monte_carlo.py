#!/usr/bin/env python3
"""Deterministic Monte Carlo runner for PlanExe parameter pipeline.

Consumes parameters.json + bounds.json + calculations.py (the same trio as
run-scenarios) and an optional settings JSON. Emits montecarlo.json next to
the parameters file.

Every classification that depends on the meaning of a variable
(sampling distribution, integer/fraction/Bernoulli discipline, non-negativity,
output name, output unit) is declared by the upstream LLM stages and read
verbatim here. The runner does no pattern-matching on id or unit strings.
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_SETTINGS: dict[str, Any] = {
    "n_runs": 10000,
    "seed": 12345,
    "distribution_default": "triangular",
    "outputs_of_interest": [],
    "thresholds": {},
    "gate_probabilities": {},
    "correlation_groups": [],
}

VALID_DISCIPLINES = {"fixed", "bernoulli_gate", "integer", "fraction", "continuous"}

THRESHOLD_OPS = {
    ">":  lambda a, b: a >  b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a <  b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


class SchemaError(RuntimeError):
    """Raised when an upstream artifact is missing a required field. Re-run the upstream stage."""


def load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def load_calculations_module(path: Path):
    spec = importlib.util.spec_from_file_location("calculations", path)
    if spec is None or spec.loader is None:
        raise SchemaError(f"cannot load calculations module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def merge_settings(user: dict | None) -> tuple[dict, list[str]]:
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    warnings: list[str] = []
    user = user or {}
    if "n_runs" in user:
        try:
            n = int(user["n_runs"])
            if 100 <= n <= 100000:
                out["n_runs"] = n
            else:
                warnings.append(f"n_runs {n} out of [100, 100000]; using {out['n_runs']}.")
        except (TypeError, ValueError):
            warnings.append("n_runs invalid; using default.")
    if "seed" in user:
        try:
            out["seed"] = int(user["seed"])
        except (TypeError, ValueError):
            warnings.append("seed invalid; using default.")
    if "distribution_default" in user:
        v = user["distribution_default"]
        if v in ("triangular", "uniform"):
            out["distribution_default"] = v
        else:
            warnings.append(f"distribution_default '{v}' unsupported; using triangular.")
    for k in ("outputs_of_interest", "thresholds", "gate_probabilities", "correlation_groups"):
        if k in user and user[k] is not None:
            out[k] = user[k]
    return out, warnings


def validate_bound(var_id: str, bound: dict) -> None:
    discipline = bound.get("sampling_discipline")
    if discipline not in VALID_DISCIPLINES:
        raise SchemaError(
            f"bound '{var_id}' is missing 'sampling_discipline' or has unknown value {discipline!r}; "
            f"expected one of {sorted(VALID_DISCIPLINES)}. Re-run generate-bounds."
        )
    if "non_negative" not in bound or not isinstance(bound["non_negative"], bool):
        raise SchemaError(
            f"bound '{var_id}' is missing required boolean 'non_negative'. Re-run generate-bounds."
        )
    if discipline == "bernoulli_gate":
        prob = bound.get("default_pass_probability")
        if not isinstance(prob, (int, float)) or not (0.0 <= prob <= 1.0):
            raise SchemaError(
                f"bound '{var_id}' has sampling_discipline 'bernoulli_gate' but "
                f"default_pass_probability is {prob!r}; expected a number in [0, 1]."
            )
    else:
        if "default_pass_probability" not in bound or bound["default_pass_probability"] is not None:
            raise SchemaError(
                f"bound '{var_id}' has sampling_discipline {discipline!r} but "
                f"default_pass_probability is not null."
            )
    for k in ("low", "base", "high"):
        if not isinstance(bound.get(k), (int, float)):
            raise SchemaError(
                f"bound '{var_id}' has non-numeric '{k}' = {bound.get(k)!r}."
            )


def sample_one(rng: np.random.Generator, bound: dict, distribution_default: str,
               gate_probabilities: dict, var_id: str) -> float:
    discipline = bound["sampling_discipline"]
    low, base, high = float(bound["low"]), float(bound["base"]), float(bound["high"])
    non_negative = bound["non_negative"]

    if discipline == "fixed":
        return low

    if discipline == "bernoulli_gate":
        p = gate_probabilities.get(var_id, bound["default_pass_probability"])
        return high if rng.random() < p else low

    if low == high:
        val = low
    elif distribution_default == "uniform":
        val = rng.uniform(low, high)
    else:
        lo, hi = min(low, high), max(low, high)
        mode = min(max(base, lo), hi)
        val = rng.triangular(lo, mode, hi)

    val = float(min(max(val, low), high))
    if discipline == "fraction":
        val = min(max(val, 0.0), 1.0)
    elif discipline == "integer":
        val = float(round(val))
        val = min(max(val, low), high)
    if non_negative and val < 0:
        val = 0.0
    return val


def collect_calculation_entries(params: dict) -> list[dict]:
    """All entries that produce a computed output, in execution order."""
    out: list[dict] = []
    for entry in params.get("recommended_first_calculations", []):
        if entry.get("formula_hint"):
            out.append(entry)
    for entry in params.get("derived_questions", []):
        if entry.get("formula_hint"):
            out.append(entry)
    return out


def validate_calculation_entry(entry: dict) -> None:
    if not entry.get("output_name"):
        raise SchemaError(
            f"calculation entry '{entry.get('id')}' has non-null formula_hint but no 'output_name'. "
            f"Re-run extract-parameters (or extract-parameters-from-digest)."
        )
    if not entry.get("output_unit"):
        raise SchemaError(
            f"calculation entry '{entry.get('id')}' has non-null formula_hint but no 'output_unit'. "
            f"Re-run extract-parameters (or extract-parameters-from-digest)."
        )


def build_calculation_plan(params: dict, module) -> tuple[list[tuple[str, str, Any]], list[str]]:
    """Return [(output_name, output_unit, function), ...] in execution order."""
    plan: list[tuple[str, str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for entry in collect_calculation_entries(params):
        validate_calculation_entry(entry)
        name = entry["output_name"]
        unit = entry["output_unit"]
        if name in seen:
            continue
        fn = getattr(module, name, None)
        if fn is None:
            warnings.append(f"function '{name}' not found in calculations.py; skipped.")
            continue
        seen.add(name)
        plan.append((name, unit, fn))
    return plan, warnings


def collect_input_specs(params: dict, bounds: dict) -> dict[str, dict]:
    """Map var_id -> {'fixed': float} or {'bound': bound_dict}."""
    specs: dict[str, dict] = {}
    for kv in params.get("key_values", []):
        vid = kv["id"]
        if vid in bounds:
            validate_bound(vid, bounds[vid])
            specs[vid] = {"bound": bounds[vid]}
        elif kv.get("value") is not None and isinstance(kv["value"], (int, float)):
            specs[vid] = {"fixed": float(kv["value"])}
    for mv in params.get("missing_values_to_estimate", []):
        vid = mv["id"]
        if vid in bounds:
            validate_bound(vid, bounds[vid])
            specs[vid] = {"bound": bounds[vid]}
    return specs


def percentiles(arr: np.ndarray) -> dict:
    if arr.size == 0:
        return {k: None for k in ("mean", "std", "min", "p05", "p25", "p50", "p75", "p95", "max")}
    return {
        "mean": float(np.mean(arr)),
        "std":  float(np.std(arr, ddof=0)),
        "min":  float(np.min(arr)),
        "p05":  float(np.percentile(arr, 5)),
        "p25":  float(np.percentile(arr, 25)),
        "p50":  float(np.percentile(arr, 50)),
        "p75":  float(np.percentile(arr, 75)),
        "p95":  float(np.percentile(arr, 95)),
        "max":  float(np.max(arr)),
    }


def safe_pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if x.size < 20 or y.size < 20 or x.size != y.size:
        return None
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    if not math.isfinite(r):
        return None
    return r


def run(params_path: Path, bounds_path: Path, calc_path: Path,
        settings_path: Path | None, output_path: Path) -> dict:
    params = load_json(params_path)
    bounds = load_json(bounds_path)
    module = load_calculations_module(calc_path)
    user_settings = load_json(settings_path) if settings_path and settings_path.exists() else {}
    settings, setting_warnings = merge_settings(user_settings)

    n_runs = settings["n_runs"]
    rng = np.random.default_rng(settings["seed"])

    warnings_text: list[str] = list(setting_warnings)

    input_specs = collect_input_specs(params, bounds)
    plan, plan_warnings = build_calculation_plan(params, module)
    warnings_text.extend(plan_warnings)

    input_units: dict[str, str] = {}
    for kv in params.get("key_values", []):
        if kv.get("unit"):
            input_units[kv["id"]] = kv["unit"]
    for mv in params.get("missing_values_to_estimate", []):
        if mv.get("unit"):
            input_units[mv["id"]] = mv["unit"]
    output_units = {name: unit for name, unit, _ in plan}

    input_arrays: dict[str, np.ndarray] = {vid: np.empty(n_runs) for vid in input_specs}
    output_arrays: dict[str, np.ndarray] = {name: np.full(n_runs, np.nan) for name, _, _ in plan}
    exception_counts: dict[str, dict[str, int]] = {name: {} for name, _, _ in plan}
    fn_signatures: dict[str, list[str]] = {
        name: list(inspect.signature(fn).parameters) for name, _, fn in plan
    }
    fn_lookup: dict[str, Any] = {name: fn for name, _, fn in plan}

    for vid, spec in input_specs.items():
        if "fixed" in spec:
            input_arrays[vid].fill(spec["fixed"])
        else:
            arr = input_arrays[vid]
            for i in range(n_runs):
                arr[i] = sample_one(
                    rng, spec["bound"], settings["distribution_default"],
                    settings["gate_probabilities"], vid,
                )

    for i in range(n_runs):
        pool: dict[str, float] = {vid: float(input_arrays[vid][i]) for vid in input_specs
                                  if math.isfinite(input_arrays[vid][i])}
        for name, _, _ in plan:
            args = fn_signatures[name]
            try:
                kwargs = {a: pool[a] for a in args}
            except KeyError:
                continue
            try:
                val = fn_lookup[name](**kwargs)
            except Exception as exc:
                exception_counts[name][type(exc).__name__] = (
                    exception_counts[name].get(type(exc).__name__, 0) + 1
                )
                continue
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                continue
            output_arrays[name][i] = val
            pool[name] = float(val)

    for name, counts in exception_counts.items():
        for exc_name, count in counts.items():
            warnings_text.append(f"output '{name}' raised {exc_name} on {count} of {n_runs} runs.")

    outputs_of_interest = settings["outputs_of_interest"] or [name for name, _, _ in plan]
    outputs_section: dict[str, dict] = {}
    for name in outputs_of_interest:
        arr_full = output_arrays.get(name)
        if arr_full is None:
            warnings_text.append(f"requested output '{name}' was not computed.")
            continue
        finite_mask = np.isfinite(arr_full)
        finite = arr_full[finite_mask]
        missing_count = int(n_runs - finite.size)
        stats = percentiles(finite)
        outputs_section[name] = {
            "unit": output_units.get(name, "unknown"),
            "count": int(finite.size),
            "missing_count": missing_count,
            **stats,
        }
        if missing_count > 0:
            collapse_rate = missing_count / n_runs
            warnings_text.append(
                f"output '{name}' had {missing_count} non-finite runs; collapse_rate={collapse_rate:.4f}."
            )

    thresholds_section: dict[str, dict] = {}
    for output_id, spec in (settings["thresholds"] or {}).items():
        op = spec.get("operator")
        if op not in THRESHOLD_OPS:
            warnings_text.append(f"threshold '{output_id}' has unsupported operator {op!r}; ignored.")
            continue
        arr = output_arrays.get(output_id)
        if arr is None:
            warnings_text.append(f"threshold references unknown output '{output_id}'; ignored.")
            continue
        finite = arr[np.isfinite(arr)]
        valid_count = int(finite.size)
        value = spec.get("value")
        success_count = int(np.sum(THRESHOLD_OPS[op](finite, value))) if valid_count else 0
        probability = (success_count / valid_count) if valid_count else None
        thresholds_section[output_id] = {
            "operator": op,
            "value": value,
            "success_count": success_count,
            "valid_count": valid_count,
            "probability": probability,
        }

    sensitivity_section: dict[str, dict] = {}
    for name in outputs_section:
        out_arr = output_arrays[name]
        all_used = set(fn_signatures.get(name, []))
        changed = True
        while changed:
            changed = False
            for other_name, other_args in fn_signatures.items():
                if other_name in all_used and not set(other_args).issubset(all_used):
                    all_used.update(other_args)
                    changed = True
        candidates: list[tuple[str, float]] = []
        finite_mask = np.isfinite(out_arr)
        for vid, arr in input_arrays.items():
            if vid not in all_used:
                continue
            if np.std(arr) == 0:
                continue
            mask = finite_mask & np.isfinite(arr)
            if mask.sum() < 20:
                continue
            r = safe_pearson(arr[mask], out_arr[mask])
            if r is None:
                continue
            candidates.append((vid, r))
        candidates.sort(key=lambda x: abs(x[1]), reverse=True)
        sensitivity_section[name] = {
            "top_inputs": [{"id": vid, "correlation": round(r, 4)} for vid, r in candidates[:5]]
        }

    result = {
        "valid": True,
        "plan_summary": {
            "plan_name": params.get("plan_summary", {}).get("plan_name", ""),
            "plan_type": params.get("plan_summary", {}).get("plan_type", ""),
        },
        "settings": {
            "n_runs": settings["n_runs"],
            "seed": settings["seed"],
            "distribution_default": settings["distribution_default"],
        },
        "outputs": outputs_section,
        "thresholds": thresholds_section,
        "sensitivity": sensitivity_section,
        "warnings": [
            {"stage": "monte_carlo", "run": None, "calculation": None,
             "message": msg, "severity": "WARN"}
            for msg in warnings_text
        ],
    }

    output_path.write_text(json.dumps(result, indent=2))
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--parameters", required=True, type=Path)
    p.add_argument("--bounds", required=True, type=Path)
    p.add_argument("--calculations", required=True, type=Path)
    p.add_argument("--settings", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    output_path = args.output or (args.parameters.parent / "montecarlo.json")
    try:
        result = run(args.parameters, args.bounds, args.calculations, args.settings, output_path)
    except SchemaError as exc:
        print(f"SCHEMA ERROR: {exc}", file=sys.stderr)
        return 2
    summary = (
        f"{output_path} "
        f"n_runs={result['settings']['n_runs']} "
        f"outputs={len(result['outputs'])} "
        f"thresholds={len(result['thresholds'])} "
        f"warnings={len(result['warnings'])}"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
