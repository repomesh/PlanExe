"""
Prepare compressed input for the future extract-parameters-compress skill.

Given a PlanExe sample directory (e.g.
``/Users/neoneye/git/PlanExe-web/20260215_nuuk_clay_workshop``), this script:

1. Runs ``compress_report_section`` on the four sections worth compressing
   (selected_scenario, review_plan, premortem, expert_criticism), feeding each
   one the same multi-file blob the corresponding Luigi node ingests, plus
   that node's own output appended. See proposals 137 and 139 for the
   rationale.
2. Writes the four per-section markdown digests and raw JSON to the output
   directory.
3. Concatenates the four markdown digests into ``extract_parameters_input.md``
   with a small legend block at the top. That single file is the input you
   point the future ``extract-parameters-compress`` skill at, to compare
   against the existing ``extract-parameters`` skill which reads the full
   PlanExe HTML report.

Defaults to a sibling ``output/<planexe-dir-name>/`` directory next to this
script. Override with ``--output-dir`` or ``--llm``.

PROMPT> python experiments/napkin_math/prepare_extract_input.py \\
            --planexe-dir /Users/neoneye/git/PlanExe-web/20260215_nuuk_clay_workshop
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_PLAN_DIR = REPO_ROOT / "worker_plan"
NAPKIN_MATH_DIR = Path(__file__).resolve().parent

SECTION_NAMES = ("selected_scenario", "review_plan", "premortem", "expert_criticism")

LEGEND = """# Compressed PlanExe digest for extract-parameters

Each section below is a structured digest of one PlanExe report section,
produced by the ``compress_report_section`` pipeline. Inline tags on each
bullet have the form ``[<source_status> | e=N r=N | quote: verified|unverified]``:

- ``explicit``    — the plan commits directly to this value
- ``derived``     — calculable from one or more ``explicit`` values
- ``inferred``    — source-stated non-binding claim, or a model-added
                    plausible guess
- ``stress_test`` — a downside-scenario magnitude, not a plan fact
- ``missing``     — a primitive input the source does not supply

- ``e=N`` — LLM-rated source evidence (1-5)
- ``r=N`` — LLM-rated modelling relevance (1-5)
- ``quote: verified|unverified`` — code-side substring check of the
  LLM-supplied ``source_quote`` against the original section text

When extracting parameters: prefer ``explicit`` and ``derived`` items with
``quote: verified``. Treat ``stress_test`` items as downside-scenario inputs
rather than baseline plan facts. Items in ``Missing data to estimate`` are
the ones to surface as ``missing_values_to_estimate`` in the output.
"""


def run_compress(planexe_dir: Path, output_dir: Path, llm: str | None) -> None:
    """Invoke the existing run_compress_full driver as a module. Sample and
    output directories are passed via the env vars the driver already
    supports.
    """
    env = os.environ.copy()
    env["COMPRESS_FULL_SAMPLE_DIR"] = str(planexe_dir)
    env["COMPRESS_FULL_OUTPUT_DIR"] = str(output_dir)
    if llm:
        env["COMPRESS_FULL_LLM"] = llm
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{WORKER_PLAN_DIR}{os.pathsep}{existing_pp}" if existing_pp else str(WORKER_PLAN_DIR)
    )
    cmd = [
        sys.executable,
        "-m",
        "worker_plan_internal.parameter_extraction.run_compress_full",
    ]
    print(f"Running: {' '.join(cmd)}")
    print(f"  COMPRESS_FULL_SAMPLE_DIR = {planexe_dir}")
    print(f"  COMPRESS_FULL_OUTPUT_DIR = {output_dir}")
    if llm:
        print(f"  COMPRESS_FULL_LLM        = {llm}")
    subprocess.run(cmd, env=env, cwd=str(WORKER_PLAN_DIR), check=True)


def build_combined_digest(output_dir: Path) -> Path:
    """Concatenate the four per-section markdown digests with a legend at the
    top. Missing sections are skipped with a warning rather than aborting,
    so partial output is still usable.
    """
    parts: list[str] = [LEGEND.rstrip(), "", "---", ""]
    found_any = False
    for name in SECTION_NAMES:
        md_path = output_dir / f"compress_{name}.md"
        if not md_path.exists():
            print(f"WARNING: {md_path.name} not produced; skipping in combined digest")
            continue
        parts.append(md_path.read_text(encoding="utf-8").strip())
        parts.append("")
        parts.append("---")
        parts.append("")
        found_any = True
    if not found_any:
        raise SystemExit(
            f"No compress_<section>.md files were produced under {output_dir}. "
            "Check the run_compress_full output above for the underlying error."
        )
    combined = output_dir / "extract_parameters_input.md"
    combined.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return combined


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--planexe-dir",
        required=True,
        type=Path,
        help="PlanExe sample directory containing plan.txt, premortem.md, etc.",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write the four section digests and combined file. "
        "Default: experiments/napkin_math/output/<planexe-dir-name>/",
    )
    ap.add_argument(
        "--llm",
        default=None,
        help="LLM name passed through to run_compress_full via "
        "COMPRESS_FULL_LLM. Default: run_compress_full's own default model.",
    )
    args = ap.parse_args()

    planexe_dir: Path = args.planexe_dir.resolve()
    if not planexe_dir.is_dir():
        raise SystemExit(f"--planexe-dir not found or not a directory: {planexe_dir}")

    output_dir: Path = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else NAPKIN_MATH_DIR / "output" / planexe_dir.name
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Planexe dir : {planexe_dir}")
    print(f"Output dir  : {output_dir}")
    print(f"LLM         : {args.llm or '(run_compress_full default)'}\n")

    run_compress(planexe_dir, output_dir, args.llm)
    combined = build_combined_digest(output_dir)

    print(f"\nWrote combined digest: {combined}")
    print("Feed this file to the future extract-parameters-compress skill.")


if __name__ == "__main__":
    main()
