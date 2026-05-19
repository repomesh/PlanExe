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

VALID_DISCIPLINES = {"fixed", "bernoulli_gate", "integer", "fraction", "continuous"}

THRESHOLD_SUFFIXES = (
    "_threshold", "_target", "_ceiling", "_floor",
    "_limit", "_cap", "_max", "_min",
)

_MARGIN_PATTERN = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*-\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*$"
)

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


def _margin_operands(formula_hint: str) -> tuple[str, str] | None:
    """If formula is `A - B` (after stripping any `LHS =`), return (A, B)."""
    rhs = formula_hint.split("=", 1)[1] if "=" in formula_hint else formula_hint
    m = _MARGIN_PATTERN.fullmatch(rhs)
    if m is None:
        return None
    return m.group(1), m.group(2)


def _collect_formula_threshold_ids(parameters: dict) -> set[str]:
    """IDs that appear as the non-`actual_` operand in a binary-subtraction
    margin formula. Multiplicative formulas and `min()` aggregates are
    skipped — their operands are coefficients or sub-margins, not thresholds.
    """
    threshold_ids: set[str] = set()
    for src in ("recommended_first_calculations", "derived_questions"):
        for entry in parameters.get(src, []) or []:
            hint = entry.get("formula_hint") or ""
            operands = _margin_operands(hint)
            if operands is None:
                continue
            left, right = operands
            left_actual = left.startswith("actual_")
            right_actual = right.startswith("actual_")
            if left_actual and not right_actual:
                threshold_ids.add(right)
            elif right_actual and not left_actual:
                threshold_ids.add(left)
    return threshold_ids


def strip_threshold_bounds(
    bounds: dict, parameters: dict,
) -> tuple[dict, list[dict]]:
    """Remove bounds entries for threshold/target variables.

    Bounds entries on threshold variables silently change what `pass_rate`
    measures from "does actual >= stated_threshold" to
    "does actual >= randomized_threshold". The simulation should test against
    the literal stated threshold value — the fixed-value fallback in
    `collect_input_specs` does this automatically when the threshold variable
    is absent from bounds. This function enforces that absence.

    Deterministic backstop for the rule documented in
    `.claude/skills/generate-bounds/system-prompt.txt`. The LLM is asked to
    skip threshold variables but does not reliably do so when parameter-JSON
    metadata (medium uncertainty + critical/high priority) signals strongly
    to include them.

    Identification:
      1. id suffix match against `THRESHOLD_SUFFIXES`
      2. id appears as the non-`actual_` operand in a binary-subtraction
         margin formula declared in `recommended_first_calculations` or
         `derived_questions`

    Variables prefixed `actual_` are never stripped.

    Returns ``(cleaned_bounds, stripped)``. ``stripped`` is an ordered list
    of ``{"id": str, "reason": "suffix" | "formula-side"}`` records. The
    input ``bounds`` is not mutated.
    """
    formula_threshold_ids = _collect_formula_threshold_ids(parameters)
    cleaned: dict = {}
    stripped: list[dict] = []
    for bound_id, bound in bounds.items():
        if bound_id.startswith("actual_"):
            cleaned[bound_id] = bound
            continue
        if bound_id.endswith(THRESHOLD_SUFFIXES):
            stripped.append({"id": bound_id, "reason": "suffix"})
            continue
        if bound_id in formula_threshold_ids:
            stripped.append({"id": bound_id, "reason": "formula-side"})
            continue
        cleaned[bound_id] = bound
    return cleaned, stripped


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
            f"Re-run extract-parameters-from-full (or extract-parameters-from-digest)."
        )
    if not entry.get("output_unit"):
        raise SchemaError(
            f"calculation entry '{entry.get('id')}' has non-null formula_hint but no 'output_unit'. "
            f"Re-run extract-parameters-from-full (or extract-parameters-from-digest)."
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
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    if not math.isfinite(r):
        return None
    return r


def is_min_aggregate(entry: dict) -> bool:
    """Identify aggregates whose magnitude is not a usual surplus."""
    hint = (entry or {}).get("formula_hint") or ""
    return "min(" in hint


def collect_min_aggregates(params: dict) -> dict[str, list[str]]:
    """Map output_name -> ordered list of dependency output_names for min() aggregates."""
    out: dict[str, list[str]] = {}
    for src in ("recommended_first_calculations", "derived_questions"):
        for entry in params.get(src, []):
            if is_min_aggregate(entry) and entry.get("output_name"):
                out[entry["output_name"]] = list(entry.get("depends_on") or [])
    return out


def threshold_passes(arr: np.ndarray, op: str, value: float) -> np.ndarray:
    """Boolean mask of runs where the threshold passes, NaN runs counted as fails."""
    finite_mask = np.isfinite(arr)
    pass_mask = np.zeros_like(arr, dtype=bool)
    pass_mask[finite_mask] = THRESHOLD_OPS[op](arr[finite_mask], value)
    return pass_mask


def quartile_pass_rates(input_arr: np.ndarray, threshold_pass: np.ndarray) -> dict | None:
    """For one input × one threshold, return P(pass | input in bottom/top quartile)."""
    if np.ptp(input_arr) == 0 or input_arr.size < 100:
        return None
    q1 = np.percentile(input_arr, 25)
    q3 = np.percentile(input_arr, 75)
    bottom_mask = input_arr <= q1
    top_mask = input_arr >= q3
    if bottom_mask.sum() < 20 or top_mask.sum() < 20:
        return None
    p_low = float(threshold_pass[bottom_mask].mean())
    p_high = float(threshold_pass[top_mask].mean())
    return {"p_pass_low_quartile": p_low,
            "p_pass_high_quartile": p_high,
            "delta_pp": round((p_high - p_low) * 100, 2)}


def required_input_percentile(input_arr: np.ndarray, threshold_pass: np.ndarray,
                              target_prob: float = 0.80) -> dict | None:
    """For a failing threshold, find which percentile of the input is required
    for conditional pass-probability to reach the target. Returns the direction
    (the input has to stay below / above that percentile)."""
    if np.ptp(input_arr) == 0 or input_arr.size < 100:
        return None
    # Try both directions. The actionable one is the one that gives the looser bound.
    best = None
    for direction in ("above", "below"):
        for pct in (5, 10, 15, 25, 33, 50, 67, 75, 85, 90, 95):
            if direction == "above":
                cutoff = float(np.percentile(input_arr, pct))
                mask = input_arr >= cutoff
            else:
                cutoff = float(np.percentile(input_arr, 100 - pct))
                mask = input_arr <= cutoff
            if mask.sum() < 20:
                continue
            cond_p = float(threshold_pass[mask].mean())
            if cond_p >= target_prob:
                # Looser bound = larger admitted fraction (1 - pct/100 for above; (100-pct)/100 for below)
                admitted = mask.mean()
                if best is None or admitted > best["admitted_fraction"]:
                    best = {
                        "direction": direction,
                        "input_percentile_cutoff": pct,
                        "cutoff_value": cutoff,
                        "conditional_pass_prob": round(cond_p, 4),
                        "admitted_fraction": round(float(admitted), 4),
                    }
                break  # take loosest pct in this direction
    return best


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

    bounds, stripped_threshold_bounds = strip_threshold_bounds(bounds, params)
    for entry in stripped_threshold_bounds:
        warnings_text.append(
            f"stripped threshold variable '{entry['id']}' from bounds "
            f"(reason: {entry['reason']}); simulation will use the stated value "
            f"from parameters.json"
        )

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
    min_aggregates = collect_min_aggregates(params)
    binding_dep_arrays: dict[str, list[str | None]] = {name: [None] * n_runs for name in min_aggregates}

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
            if name in min_aggregates:
                for dep in min_aggregates[name]:
                    if dep in pool and pool[dep] == val:
                        binding_dep_arrays[name][i] = dep
                        break

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
            if np.ptp(arr) == 0:
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

    binding_gate_analysis: dict[str, dict] = {}
    for agg_name, deps in min_aggregates.items():
        if agg_name not in thresholds_section:
            continue
        t = thresholds_section[agg_name]
        agg_arr = output_arrays[agg_name]
        fail_mask = ~threshold_passes(agg_arr, t["operator"], t["value"]) & np.isfinite(agg_arr)
        if fail_mask.sum() == 0:
            continue
        counts: dict[str, int] = {dep: 0 for dep in deps}
        for i in range(n_runs):
            if not fail_mask[i]:
                continue
            d = binding_dep_arrays[agg_name][i]
            if d is not None:
                counts[d] = counts.get(d, 0) + 1
        total = sum(counts.values())
        if total == 0:
            continue
        binding_gate_analysis[agg_name] = {
            "fail_count": int(fail_mask.sum()),
            "binding_when_aggregate_fails": [
                {"dependency": d, "frequency": round(c / total, 4)}
                for d, c in sorted(counts.items(), key=lambda x: -x[1]) if c > 0
            ],
        }

    quartile_analysis: dict[str, list[dict]] = {}
    required_input_thresholds: dict[str, list[dict]] = {}
    for output_id, t in thresholds_section.items():
        if t.get("probability") is None:
            continue
        pass_arr = threshold_passes(output_arrays[output_id], t["operator"], t["value"])
        all_used = set(fn_signatures.get(output_id, []))
        changed = True
        while changed:
            changed = False
            for other_name, other_args in fn_signatures.items():
                if other_name in all_used and not set(other_args).issubset(all_used):
                    all_used.update(other_args)
                    changed = True
        rows = []
        req_rows = []
        for vid in input_arrays:
            if vid not in all_used or vid not in input_specs or "bound" not in input_specs[vid]:
                continue
            q = quartile_pass_rates(input_arrays[vid], pass_arr)
            if q is None:
                continue
            rows.append({"id": vid, **q})
            if t["probability"] is not None and t["probability"] < 0.80:
                req = required_input_percentile(input_arrays[vid], pass_arr)
                if req is not None:
                    req_rows.append({"id": vid, **req})
        if rows:
            rows.sort(key=lambda x: -abs(x["delta_pp"]))
            quartile_analysis[output_id] = rows[:5]
        if req_rows:
            req_rows.sort(key=lambda x: -x["admitted_fraction"])
            required_input_thresholds[output_id] = req_rows[:5]

    missing_value_priority: list[dict] = []
    missing_ids = [mv["id"] for mv in params.get("missing_values_to_estimate", [])]
    for vid in missing_ids:
        if vid not in input_arrays:
            continue
        bound = bounds.get(vid, {})
        low, high, base = bound.get("low", 0), bound.get("high", 0), bound.get("base", 0)
        denom = max(abs(base), 1e-9) if base else max(abs(high - low), 1e-9)
        bound_width_ratio = abs(high - low) / denom
        score = 0.0
        worst_threshold: str | None = None
        for output_id, t in thresholds_section.items():
            p = t.get("probability")
            if p is None:
                continue
            rows = quartile_analysis.get(output_id, [])
            entry = next((r for r in rows if r["id"] == vid), None)
            if entry is None:
                continue
            impact = abs(entry["delta_pp"]) * (1.0 - p) * bound_width_ratio
            if impact > score:
                score = impact
                worst_threshold = output_id
        if worst_threshold:
            missing_value_priority.append({
                "id": vid,
                "score": round(score, 4),
                "worst_gate": worst_threshold,
                "bound_width_ratio": round(bound_width_ratio, 4),
                "source": bound.get("source", "assumption"),
            })
    missing_value_priority.sort(key=lambda x: -x["score"])

    model_confidence: dict[str, dict] = {}
    for output_id in outputs_section:
        used: set[str] = set(fn_signatures.get(output_id, []))
        changed = True
        while changed:
            changed = False
            for other_name, other_args in fn_signatures.items():
                if other_name in used and not set(other_args).issubset(used):
                    used.update(other_args)
                    changed = True
        bound_inputs = [vid for vid in used if vid in input_specs and "bound" in input_specs[vid]]
        if not bound_inputs:
            model_confidence[output_id] = {"grade": "HIGH",
                                           "reasons": ["all inputs are fixed values"]}
            continue
        data_n = sum(1 for vid in bound_inputs if bounds.get(vid, {}).get("source") == "data")
        assumption_n = len(bound_inputs) - data_n
        data_fraction = data_n / len(bound_inputs)
        widths = []
        for vid in bound_inputs:
            b = bounds.get(vid, {})
            base = b.get("base", 0)
            denom = max(abs(base), 1e-9) if base else max(abs(b.get("high", 0) - b.get("low", 0)), 1e-9)
            widths.append(abs(b.get("high", 0) - b.get("low", 0)) / denom)
        avg_width = sum(widths) / len(widths)
        reasons: list[str] = []
        if data_fraction >= 0.70 and avg_width < 0.5:
            grade = "HIGH"
        elif data_fraction < 0.30 or avg_width > 1.5:
            grade = "LOW"
        else:
            grade = "MEDIUM"
        reasons.append(f"{data_n}/{len(bound_inputs)} input bounds anchored in data; {assumption_n}/{len(bound_inputs)} are assumptions")
        reasons.append(f"average bound-width-to-base ratio = {avg_width:.2f}")
        model_confidence[output_id] = {
            "grade": grade,
            "data_source_fraction": round(data_fraction, 4),
            "average_bound_width_ratio": round(avg_width, 4),
            "reasons": reasons,
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
        "quartile_analysis": quartile_analysis,
        "binding_gate_analysis": binding_gate_analysis,
        "required_input_thresholds": required_input_thresholds,
        "missing_value_priority": missing_value_priority,
        "model_confidence": model_confidence,
        "bounds_post_processor": {
            "stripped_threshold_ids": stripped_threshold_bounds,
        },
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
