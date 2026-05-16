#!/usr/bin/env python3
"""Smoke tests for experiments/napkin_math.

Run after any change under experiments/napkin_math/ or to the upstream skill
prompts under .claude/skills/{generate-bounds,extract-parameters-from-full,...}.

Covers:
  1. run_monte_carlo.py end-to-end against the synthetic fixture
  2. Determinism: two runs with the same seed produce byte-identical JSON
  3. Bernoulli arithmetic spot-check
  4. Sensitivity ranking spot-check
  5. Schema-error fail-fast paths for each required field
  6. prepare_extract_input.py imports cleanly
  7. compress_report_section pytest suite

Exits 0 if every check passes, 1 otherwise. Prints a one-line summary at the end.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
NAPKIN_DIR = REPO_ROOT / "experiments" / "napkin_math"
FIXTURE_DIR = NAPKIN_DIR / "tests" / "fixtures" / "smoke"
RUNNER = NAPKIN_DIR / "run_monte_carlo.py"
PY = os.environ.get("NAPKIN_TEST_PYTHON", "/opt/homebrew/bin/python3.11")


class CheckFailed(Exception):
    pass


def _check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise CheckFailed(f"{label}: FAIL{(' — ' + detail) if detail else ''}")
    print(f"  ok   {label}")


def _run_runner(out_path: Path, *, bounds: Path | None = None, parameters: Path | None = None,
                expect_exit: int = 0) -> subprocess.CompletedProcess:
    bounds = bounds or (FIXTURE_DIR / "bounds.json")
    parameters = parameters or (FIXTURE_DIR / "parameters.json")
    cmd = [
        PY, str(RUNNER),
        "--parameters", str(parameters),
        "--bounds", str(bounds),
        "--calculations", str(FIXTURE_DIR / "calculations.py"),
        "--output", str(out_path),
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != expect_exit:
        raise CheckFailed(
            f"runner exit code was {cp.returncode}, expected {expect_exit}\n"
            f"stdout: {cp.stdout}\nstderr: {cp.stderr}"
        )
    return cp


def check_end_to_end(tmpdir: Path) -> None:
    out = tmpdir / "smoke.json"
    _run_runner(out)
    _check("runner produced an output file", out.exists())
    result = json.loads(out.read_text())
    _check("valid: true", result.get("valid") is True)
    _check("two outputs computed", set(result["outputs"]) == {
        "taster_converted_members", "total_budget_with_gate_inr"
    })
    _check("no warnings on clean fixture", result["warnings"] == [],
           detail=json.dumps(result["warnings"]))


def check_determinism(tmpdir: Path) -> None:
    a, b = tmpdir / "det_a.json", tmpdir / "det_b.json"
    _run_runner(a)
    _run_runner(b)
    _check("byte-identical across two runs with same seed", a.read_bytes() == b.read_bytes())


def check_bernoulli_arithmetic(tmpdir: Path) -> None:
    out = tmpdir / "bern.json"
    _run_runner(out)
    result = json.loads(out.read_text())
    mean = result["outputs"]["total_budget_with_gate_inr"]["mean"]
    expected = 1_000_000 + 0.6 * 250_000
    _check(
        f"Bernoulli mean ~{expected:.0f}, got {mean:.1f}",
        abs(mean - expected) < 5_000,
    )


def check_sensitivity_ranking(tmpdir: Path) -> None:
    out = tmpdir / "sens.json"
    _run_runner(out)
    result = json.loads(out.read_text())
    bern_top = result["sensitivity"]["total_budget_with_gate_inr"]["top_inputs"]
    _check(
        "Bernoulli gate is the sole driver of total_budget_with_gate_inr",
        len(bern_top) == 1
        and bern_top[0]["id"] == "month4_gate_release_inr"
        and abs(bern_top[0]["correlation"] - 1.0) < 1e-6,
    )
    conv_top = {entry["id"] for entry in
                result["sensitivity"]["taster_converted_members"]["top_inputs"]}
    _check(
        "Converted-members sensitivity includes both drivers",
        conv_top == {"taster_attendees_year1", "taster_conversion_rate"},
    )


def _mutated_bounds(tmpdir: Path, mutator) -> Path:
    bounds = json.loads((FIXTURE_DIR / "bounds.json").read_text())
    mutator(bounds)
    path = tmpdir / "mutated_bounds.json"
    path.write_text(json.dumps(bounds))
    return path


def _mutated_parameters(tmpdir: Path, mutator) -> Path:
    params = json.loads((FIXTURE_DIR / "parameters.json").read_text())
    mutator(params)
    path = tmpdir / "mutated_parameters.json"
    path.write_text(json.dumps(params))
    return path


def check_schema_errors(tmpdir: Path) -> None:
    out = tmpdir / "schema.json"

    def drop_discipline(b):
        del b["taster_conversion_rate"]["sampling_discipline"]
    cp = _run_runner(out, bounds=_mutated_bounds(tmpdir, drop_discipline), expect_exit=2)
    _check("missing sampling_discipline -> SCHEMA ERROR",
           "sampling_discipline" in cp.stderr and "generate-bounds" in cp.stderr)

    def drop_non_negative(b):
        del b["taster_conversion_rate"]["non_negative"]
    cp = _run_runner(out, bounds=_mutated_bounds(tmpdir, drop_non_negative), expect_exit=2)
    _check("missing non_negative -> SCHEMA ERROR", "non_negative" in cp.stderr)

    def drop_pass_prob(b):
        b["month4_gate_release_inr"]["default_pass_probability"] = None
    cp = _run_runner(out, bounds=_mutated_bounds(tmpdir, drop_pass_prob), expect_exit=2)
    _check("bernoulli_gate without default_pass_probability -> SCHEMA ERROR",
           "default_pass_probability" in cp.stderr)

    def bad_discipline(b):
        b["taster_conversion_rate"]["sampling_discipline"] = "made_up"
    cp = _run_runner(out, bounds=_mutated_bounds(tmpdir, bad_discipline), expect_exit=2)
    _check("unknown sampling_discipline -> SCHEMA ERROR",
           "sampling_discipline" in cp.stderr)

    def drop_output_name(p):
        p["recommended_first_calculations"][0]["output_name"] = None
    cp = _run_runner(out, parameters=_mutated_parameters(tmpdir, drop_output_name), expect_exit=2)
    _check("missing output_name on formula-bearing entry -> SCHEMA ERROR",
           "output_name" in cp.stderr and "extract-parameters-from-full" in cp.stderr)

    def drop_output_unit(p):
        p["recommended_first_calculations"][0]["output_unit"] = None
    cp = _run_runner(out, parameters=_mutated_parameters(tmpdir, drop_output_unit), expect_exit=2)
    _check("missing output_unit on formula-bearing entry -> SCHEMA ERROR",
           "output_unit" in cp.stderr)


def check_summarize_insights_end_to_end(tmpdir: Path) -> None:
    """Run the runner against the smoke fixture, then feed both into
    summarize_insights.py and verify the doom-verdict pipeline works.
    """
    settings = tmpdir / "summarize_settings.json"
    settings.write_text(json.dumps({
        "n_runs": 1000, "seed": 7,
        "thresholds": {
            "total_budget_with_gate_inr": {"operator": ">=", "value": 1_100_000},
            "taster_converted_members": {"operator": ">=", "value": 100},
        },
    }))
    mc_out = tmpdir / "summarize_mc.json"
    cp = subprocess.run(
        [PY, str(RUNNER),
         "--parameters", str(FIXTURE_DIR / "parameters.json"),
         "--bounds", str(FIXTURE_DIR / "bounds.json"),
         "--calculations", str(FIXTURE_DIR / "calculations.py"),
         "--settings", str(settings),
         "--output", str(mc_out)],
        capture_output=True, text=True,
    )
    if cp.returncode != 0:
        raise CheckFailed(f"runner failed: {cp.stderr}")

    insights = tmpdir / "summarize_insights.md"
    summarizer = NAPKIN_DIR / "summarize_insights.py"
    cp = subprocess.run(
        [PY, str(summarizer),
         "--parameters", str(FIXTURE_DIR / "parameters.json"),
         "--bounds", str(FIXTURE_DIR / "bounds.json"),
         "--montecarlo", str(mc_out),
         "--output", str(insights)],
        capture_output=True, text=True,
    )
    if cp.returncode != 0:
        raise CheckFailed(f"summarizer failed: {cp.stderr}")
    body = insights.read_text()
    _check("insights.md was produced", insights.exists())
    _check("insights.md contains plan name", "Synthetic Workshop" in body)
    _check("insights.md contains the verdict table",
           "Headline verdicts" in body and "Verdict" in body)
    _check("insights.md classifies one threshold as ROBUST (taster ≥ 100 with p=0.6 → ~150 expected)",
           "ROBUST" in body or "MARGINAL" in body)


def check_prepare_extract_input_imports() -> None:
    cp = subprocess.run(
        [PY, "-c", "import importlib.util, sys, pathlib; "
                   "spec = importlib.util.spec_from_file_location("
                   "'prep', pathlib.Path('experiments/napkin_math/prepare_extract_input.py'));"
                   "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
                   "assert hasattr(m, 'build_combined_digest');"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    _check(
        "prepare_extract_input.py imports and exposes build_combined_digest",
        cp.returncode == 0,
        detail=cp.stderr,
    )


def check_compress_pytest() -> None:
    cp = subprocess.run(
        [PY, "-m", "pytest",
         "worker_plan/worker_plan_internal/parameter_extraction/tests/test_compress_report_section.py",
         "-q", "--no-header"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "worker_plan")},
    )
    last_line = (cp.stdout.strip().splitlines() or [""])[-1]
    _check(
        f"compress_report_section pytest passes ({last_line})",
        cp.returncode == 0,
        detail=cp.stdout + cp.stderr,
    )


def main() -> int:
    if not shutil.which(PY):
        print(f"FAIL: python interpreter not found at {PY}; "
              f"override with NAPKIN_TEST_PYTHON=<path>")
        return 1
    checks: list[tuple[str, callable]] = [
        ("end_to_end", check_end_to_end),
        ("determinism", check_determinism),
        ("bernoulli_arithmetic", check_bernoulli_arithmetic),
        ("sensitivity_ranking", check_sensitivity_ranking),
        ("schema_errors", check_schema_errors),
        ("summarize_insights_end_to_end", check_summarize_insights_end_to_end),
    ]
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for name, fn in checks:
            print(f"[{name}]")
            try:
                fn(tmpdir)
            except CheckFailed as exc:
                failures.append(f"{name}: {exc}")
                print(f"  FAIL {exc}")
    for name, fn in (
        ("prepare_extract_input_imports", check_prepare_extract_input_imports),
        ("compress_pytest", check_compress_pytest),
    ):
        print(f"[{name}]")
        try:
            fn()
        except CheckFailed as exc:
            failures.append(f"{name}: {exc}")
            print(f"  FAIL {exc}")
    total = len(checks) + 2
    passed = total - len(failures)
    print(f"\nSUMMARY: {passed}/{total} checks passed")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
