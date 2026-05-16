#!/usr/bin/env python3
"""Deterministic Monte Carlo runner for PlanExe parameter pipeline.

Consumes parameters.json + bounds.json + calculations.py (the same trio as
run-scenarios) and an optional settings JSON. Emits montecarlo.json next to
the parameters file. Replaces the prior LLM-driven skill, whose sampling and
correlation steps could not actually be performed in-prompt.
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import math
import re
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

INTEGER_UNIT_TOKENS = {
    "people", "buyers", "customers", "households", "units", "kits",
    "centers", "sites", "months", "days", "hours", "events", "staff",
    "attendees", "residents", "kits",
}

GATE_RATIONALE_KEYWORDS = (
    "binary", "gate", "release", "tranche", "pass", "fail", "withheld", "conditional",
)

THRESHOLD_OPS = {
    ">":  lambda a, b: a >  b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a <  b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def load_calculations_module(path: Path):
    spec = importlib.util.spec_from_file_location("calculations", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load calculations module from {path}")
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


def unit_tokens(unit: str) -> set[str]:
    if not unit:
        return set()
    return set(re.split(r"[^a-zA-Z0-9]+", unit.lower()))


def is_integer_unit(unit: str) -> bool:
    if not unit:
        return False
    low = unit.lower()
    if "_per_" in low or low.startswith("per_") or "_rate" in low:
        return False
    return bool(unit_tokens(unit) & INTEGER_UNIT_TOKENS)


def is_fraction_unit(unit: str) -> bool:
    return (unit or "").lower() == "fraction"


def is_monetary_unit(unit: str) -> bool:
    return bool(re.search(r"(?:^|_)(eur|usd|gbp|dkk|nok|sek|isk|chf|jpy|cny|inr)(?:$|_)", (unit or "").lower()))


def is_bernoulli_gate(bound: dict) -> bool:
    if not is_monetary_unit(bound.get("unit", "")):
        return False
    low, base, high = bound.get("low"), bound.get("base"), bound.get("high")
    if not (isinstance(low, (int, float)) and low == 0 and base == high):
        return False
    rationale = (bound.get("rationale") or "").lower()
    return any(k in rationale for k in GATE_RATIONALE_KEYWORDS)


def sample_one(rng: np.random.Generator, bound: dict, distribution_default: str,
               gate_probabilities: dict, var_id: str, warnings_out: list[str]) -> float:
    unit = bound.get("unit", "")
    low, base, high = bound.get("low"), bound.get("base"), bound.get("high")
    if not all(isinstance(x, (int, float)) for x in (low, base, high)):
        return math.nan
    if low == base == high:
        return float(low)
    if is_bernoulli_gate(bound):
        if var_id not in gate_probabilities:
            msg = f"binary gate '{var_id}' has no explicit gate_probability; defaulted to 0.5."
            if msg not in warnings_out:
                warnings_out.append(msg)
            p = 0.5
        else:
            p = float(gate_probabilities[var_id])
        return float(high) if rng.random() < p else float(low)
    if distribution_default == "uniform":
        val = rng.uniform(low, high)
    else:
        try:
            val = rng.triangular(low, base, high)
        except ValueError:
            lo, hi = min(low, high), max(low, high)
            mode = min(max(base, lo), hi)
            val = rng.triangular(lo, mode, hi)
    val = float(min(max(val, low), high))
    if is_fraction_unit(unit):
        val = min(max(val, 0.0), 1.0)
    if is_integer_unit(unit):
        val = float(round(val))
        val = min(max(val, low), high)
    elif val < 0 and not is_bernoulli_gate(bound):
        val = max(val, 0.0)
    return val


FORMULA_LHS_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def parse_function_name(entry: dict) -> str | None:
    hint = entry.get("formula_hint") or ""
    m = FORMULA_LHS_RE.match(hint)
    if m:
        return m.group(1)
    if hint.strip():
        return entry.get("id")
    return None


def build_calculation_plan(params: dict, module) -> tuple[list[tuple[str, Any]], list[str]]:
    """Return ordered [(output_name, function), ...] and warnings."""
    plan: list[tuple[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for entry in params.get("recommended_first_calculations", []):
        fn_name = parse_function_name(entry)
        if not fn_name:
            warnings.append(f"recommended_first_calculations entry '{entry.get('id')}' has no formula_hint; skipped.")
            continue
        fn = getattr(module, fn_name, None)
        if fn is None:
            warnings.append(f"function '{fn_name}' not found in calculations.py; skipped.")
            continue
        if fn_name in seen:
            continue
        seen.add(fn_name)
        plan.append((fn_name, fn))
    for entry in params.get("derived_questions", []):
        fn_name = parse_function_name(entry)
        if not fn_name:
            warnings.append(f"derived_question '{entry.get('id')}' has no formula_hint; skipped.")
            continue
        fn = getattr(module, fn_name, None)
        if fn is None:
            warnings.append(f"function '{fn_name}' not found in calculations.py; skipped.")
            continue
        if fn_name in seen:
            continue
        seen.add(fn_name)
        plan.append((fn_name, fn))
    return plan, warnings


def collect_input_specs(params: dict, bounds: dict) -> dict[str, dict]:
    """Map var_id -> spec with 'fixed' or 'bound' key."""
    specs: dict[str, dict] = {}
    for kv in params.get("key_values", []):
        vid = kv["id"]
        if vid in bounds:
            specs[vid] = {"bound": bounds[vid]}
        elif kv.get("value") is not None and isinstance(kv["value"], (int, float)):
            specs[vid] = {"fixed": float(kv["value"])}
    for mv in params.get("missing_values_to_estimate", []):
        vid = mv["id"]
        if vid in bounds:
            specs[vid] = {"bound": bounds[vid]}
    return specs


UNIT_INFERENCE_RULES = [
    (re.compile(r"_eur(?:$|_)|_dkk(?:$|_)|_usd(?:$|_)|_gbp(?:$|_)|_nok(?:$|_)|_sek(?:$|_)"), "currency"),
    (re.compile(r"(?:^|_)(?:fraction|ratio|rate|share|probability|effectiveness|penetration|percent)(?:$|_)"), "fraction"),
    (re.compile(r"(?:^|_)(?:cost|budget|reserve|tranche|funding|revenue|spend|cash|profit|margin|arpu|price)(?:$|_)"), "currency"),
    (re.compile(r"(?:^|_)(?:buyer|buyers|customer|customers|attendee|attendees|person|people|resident|residents|population|contacted|protected|members?)(?:$|_)"), "people"),
    (re.compile(r"(?:^|_)(?:unit|units|sku|skus|item|items)(?:$|_)"), "units"),
    (re.compile(r"(?:^|_)(?:kit|kits)(?:$|_)"), "kits"),
    (re.compile(r"(?:^|_)(?:household|households|home|homes)(?:$|_)"), "households"),
    (re.compile(r"(?:^|_)(?:event|events|death|deaths|harm|mortality|illness)(?:$|_)"), "events"),
    (re.compile(r"(?:^|_)(?:month|months)(?:$|_)"), "months"),
    (re.compile(r"(?:^|_)(?:day|days)(?:$|_)"), "days"),
    (re.compile(r"(?:^|_)(?:hour|hours)(?:$|_)"), "hours"),
    (re.compile(r"(?:^|_)(?:fte|staffing)(?:$|_)"), "people"),
]


def infer_unit(output_id: str, known_units: dict[str, str]) -> str:
    if output_id in known_units:
        return known_units[output_id]
    low = output_id.lower()
    for pat, label in UNIT_INFERENCE_RULES:
        if pat.search(low):
            if label == "currency":
                m = re.search(r"_(eur|dkk|usd|gbp|nok|sek)(?:$|_)", low)
                return m.group(1).upper() if m else "money"
            return label
    return "unknown"


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
    sample_warnings: list[str] = []

    input_specs = collect_input_specs(params, bounds)
    plan, plan_warnings = build_calculation_plan(params, module)
    warnings_text.extend(plan_warnings)

    known_units: dict[str, str] = {}
    for kv in params.get("key_values", []):
        if kv.get("unit"):
            known_units[kv["id"]] = kv["unit"]
    for mv in params.get("missing_values_to_estimate", []):
        if mv.get("unit"):
            known_units[mv["id"]] = mv["unit"]

    input_arrays: dict[str, np.ndarray] = {vid: np.empty(n_runs) for vid in input_specs}
    output_arrays: dict[str, np.ndarray] = {name: np.full(n_runs, np.nan) for name, _ in plan}
    exception_counts: dict[str, dict[str, int]] = {name: {} for name, _ in plan}
    fn_signatures: dict[str, list[str]] = {
        name: list(inspect.signature(fn).parameters) for name, fn in plan
    }

    for vid, spec in input_specs.items():
        if "fixed" in spec:
            input_arrays[vid].fill(spec["fixed"])
        else:
            arr = input_arrays[vid]
            for i in range(n_runs):
                arr[i] = sample_one(
                    rng, spec["bound"], settings["distribution_default"],
                    settings["gate_probabilities"], vid, sample_warnings,
                )

    for i in range(n_runs):
        pool: dict[str, float] = {vid: float(input_arrays[vid][i]) for vid in input_specs
                                  if math.isfinite(input_arrays[vid][i])}
        for name, fn in plan:
            args = fn_signatures[name]
            try:
                kwargs = {a: pool[a] for a in args}
            except KeyError:
                continue
            try:
                val = fn(**kwargs)
            except Exception as exc:
                exception_counts[name][type(exc).__name__] = (
                    exception_counts[name].get(type(exc).__name__, 0) + 1
                )
                continue
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                continue
            output_arrays[name][i] = val
            pool[name] = float(val)

    warnings_text.extend(sample_warnings)
    for name, counts in exception_counts.items():
        for exc_name, count in counts.items():
            warnings_text.append(f"output '{name}' raised {exc_name} on {count} of {n_runs} runs.")

    outputs_of_interest = settings["outputs_of_interest"] or [name for name, _ in plan]
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
            "unit": infer_unit(name, known_units),
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
            warnings_text.append(f"threshold '{output_id}' has unsupported operator '{op}'; ignored.")
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
        used_args = set(fn_signatures.get(name, []))
        all_used = set(used_args)
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
    result = run(args.parameters, args.bounds, args.calculations, args.settings, output_path)
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
