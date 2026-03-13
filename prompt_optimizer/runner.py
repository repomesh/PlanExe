"""
Run the IdentifyPotentialLevers pipeline step with a candidate system prompt
against baseline training data and capture the output.

Usage:
    python -m prompt_optimizer.runner \
        --system-prompt-file candidate.txt \
        --baseline-dir /path/to/baseline/train \
        --output-dir /path/to/runs/my_run/outputs \
        --model ollama-llama3.1
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Add worker_plan/ to sys.path so worker_plan_internal imports work.
_worker_plan_dir = str(Path(__file__).resolve().parent.parent / "worker_plan")
if _worker_plan_dir not in sys.path:
    sys.path.insert(0, _worker_plan_dir)

from worker_plan_internal.lever.identify_potential_levers import IdentifyPotentialLevers
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelFromName

logger = logging.getLogger(__name__)

INPUT_FILES = [
    "001-2-plan.txt",
    "002-6-identify_purpose.md",
    "002-8-plan_type.md",
]

FILE_LABELS = [
    "plan.txt",
    "purpose.md",
    "plan_type.md",
]


def load_user_prompt(plan_dir: Path) -> str:
    """
    Read the 3 input files from a plan directory and concatenate them
    exactly as PotentialLeversTask.run_inner() does.
    """
    parts = []
    for filename, label in zip(INPUT_FILES, FILE_LABELS):
        file_path = plan_dir / filename
        content = file_path.read_text()
        parts.append(f"File '{label}':\n{content}")
    return "\n\n".join(parts)


@dataclass
class PlanResult:
    plan_name: str
    status: str
    lever_count: int
    duration_seconds: float
    error: str | None = None


def run_single_plan(
    plan_dir: Path,
    output_dir: Path,
    system_prompt: str,
    llm_executor: LLMExecutor,
) -> PlanResult:
    """
    Run IdentifyPotentialLevers for one plan directory. Writes the raw and
    clean JSON outputs into output_dir/<plan_name>/.
    """
    plan_name = plan_dir.name
    plan_output_dir = output_dir / plan_name
    plan_output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    try:
        user_prompt = load_user_prompt(plan_dir)
        result = IdentifyPotentialLevers.execute(
            llm_executor, user_prompt, system_prompt=system_prompt
        )

        raw_path = plan_output_dir / "002-9-potential_levers_raw.json"
        clean_path = plan_output_dir / "002-10-potential_levers.json"
        result.save_raw(str(raw_path))
        result.save_clean(str(clean_path))

        duration = time.monotonic() - t0
        lever_count = len(result.levers)
        logger.info(f"{plan_name}: {lever_count} levers in {duration:.1f}s")
        return PlanResult(
            plan_name=plan_name,
            status="ok",
            lever_count=lever_count,
            duration_seconds=round(duration, 2),
        )
    except Exception as e:
        duration = time.monotonic() - t0
        logger.error(f"{plan_name}: failed after {duration:.1f}s — {e}")
        return PlanResult(
            plan_name=plan_name,
            status="error",
            lever_count=0,
            duration_seconds=round(duration, 2),
            error=str(e),
        )


def run(
    system_prompt: str,
    plan_dirs: list[Path],
    output_dir: Path,
    model_names: list[str],
) -> dict:
    """
    Iterate over plan directories, run the lever step for each, and write
    meta.json one level above output_dir.
    """
    llm_models = LLMModelFromName.from_names(model_names)
    llm_executor = LLMExecutor(llm_models=llm_models)

    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_sha256 = hashlib.sha256(system_prompt.encode()).hexdigest()

    results: list[PlanResult] = []
    total_t0 = time.monotonic()

    for plan_dir in plan_dirs:
        pr = run_single_plan(plan_dir, output_dir, system_prompt, llm_executor)
        results.append(pr)

    total_duration = round(time.monotonic() - total_t0, 2)

    meta = {
        "step": "identify_potential_levers",
        "system_prompt_sha256": prompt_sha256,
        "models": model_names,
        "plans": [
            {
                "plan_name": r.plan_name,
                "status": r.status,
                "lever_count": r.lever_count,
                "duration_seconds": r.duration_seconds,
                "error": r.error,
            }
            for r in results
        ],
        "total_duration_seconds": total_duration,
    }

    meta_path = output_dir.parent / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info(f"Wrote {meta_path}")

    return meta


def main():
    parser = argparse.ArgumentParser(
        description="Run IdentifyPotentialLevers with a candidate system prompt."
    )
    parser.add_argument(
        "--system-prompt-file",
        required=True,
        type=Path,
        help="Path to a text file containing the candidate system prompt.",
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        help="Directory containing plan subdirectories (process all).",
    )
    parser.add_argument(
        "--plan-dir",
        type=Path,
        help="Single plan directory to process (overrides --baseline-dir).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where outputs will be written.",
    )
    parser.add_argument(
        "--model",
        required=True,
        action="append",
        dest="models",
        help="LLM model name (can be repeated).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    system_prompt = args.system_prompt_file.read_text()

    if args.plan_dir:
        plan_dirs = [args.plan_dir]
    elif args.baseline_dir:
        plan_dirs = sorted(
            p for p in args.baseline_dir.iterdir() if p.is_dir()
        )
    else:
        parser.error("Either --plan-dir or --baseline-dir is required.")

    if not plan_dirs:
        parser.error("No plan directories found.")

    meta = run(system_prompt, plan_dirs, args.output_dir, args.models)

    ok = sum(1 for p in meta["plans"] if p["status"] == "ok")
    total = len(meta["plans"])
    print(f"\nDone: {ok}/{total} plans succeeded in {meta['total_duration_seconds']}s")


if __name__ == "__main__":
    main()
