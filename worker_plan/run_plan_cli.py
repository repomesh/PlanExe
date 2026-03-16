"""
CLI bootstrap script for direct PlanExe pipeline invocation.

The Gradio/Flask frontend normally creates a set of bootstrap files in the run
directory *before* invoking Luigi.  When you want to run the pipeline directly
from the command line (no frontend), those files are missing and Luigi exits
immediately with an AssertionError.

This script replicates the frontend bootstrap step so you can run the full
pipeline without a UI dependency.

Usage examples
--------------
Bootstrap only (inspect files, then invoke the pipeline manually):

    python -m worker_plan.run_plan_cli \\
        --plan-text "Small coffee shop in Copenhagen, Denmark" \\
        --run-id-dir ./planexe-outputs/2026-03-16/MyCoffeeShop_v1

Bootstrap *and* launch the pipeline immediately:

    python -m worker_plan.run_plan_cli \\
        --plan-text "Small coffee shop in Copenhagen, Denmark" \\
        --run-id-dir ./planexe-outputs/2026-03-16/MyCoffeeShop_v1 \\
        --launch

Read the plan prompt from a file instead of the command line:

    python -m worker_plan.run_plan_cli \\
        --plan-file my_plan.txt \\
        --run-id-dir ./planexe-outputs/2026-03-16/MyCoffeeShop_v1 \\
        --launch
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def _utc_iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string (seconds precision, Z suffix)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bootstrap_run_dir(run_id_dir: Path, plan_text: str) -> None:
    """
    Create the run directory and write the bootstrap files that the Gradio
    frontend normally produces before Luigi is invoked.

    Files written
    -------------
    001-1-start_time.json
        ``{"server_iso_utc": "<current UTC ISO timestamp>"}``

    001-2-plan.txt
        The plain-text plan prompt supplied by the caller.

    Parameters
    ----------
    run_id_dir:
        Absolute or relative path to the run directory.  Created (including
        any missing parents) if it does not already exist.
    plan_text:
        The plan prompt text.
    """
    run_id_dir.mkdir(parents=True, exist_ok=True)

    # 001-1-start_time.json
    start_time_path = run_id_dir / "001-1-start_time.json"
    start_time_data = {"server_iso_utc": _utc_iso_now()}
    start_time_path.write_text(json.dumps(start_time_data, indent=2), encoding="utf-8")
    print(f"  ✓ {start_time_path}")

    # 001-2-plan.txt
    plan_path = run_id_dir / "001-2-plan.txt"
    plan_path.write_text(plan_text, encoding="utf-8")
    print(f"  ✓ {plan_path}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_plan_cli",
        description=(
            "Bootstrap a PlanExe run directory so the Luigi pipeline can be "
            "invoked directly without the Gradio frontend."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    plan_source = parser.add_mutually_exclusive_group(required=True)
    plan_source.add_argument(
        "--plan-text",
        metavar="TEXT",
        help="Plan prompt text (pass as a quoted string).",
    )
    plan_source.add_argument(
        "--plan-file",
        metavar="PATH",
        type=Path,
        help="Path to a .txt file containing the plan prompt.",
    )

    parser.add_argument(
        "--run-id-dir",
        required=True,
        metavar="DIR",
        type=Path,
        help="Output directory for this run (created if it does not exist).",
    )

    parser.add_argument(
        "--launch",
        action="store_true",
        default=False,
        help=(
            "After bootstrapping, immediately invoke the pipeline via "
            "``python -m worker_plan_internal.plan.run_plan_pipeline``.  "
            "The RUN_ID_DIR environment variable is set automatically."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve plan text.
    if args.plan_text is not None:
        plan_text: str = args.plan_text
    else:
        plan_file: Path = args.plan_file
        if not plan_file.exists():
            print(f"ERROR: --plan-file does not exist: {plan_file}", file=sys.stderr)
            return 1
        plan_text = plan_file.read_text(encoding="utf-8")

    run_id_dir: Path = args.run_id_dir.resolve()

    print(f"\nBootstrapping run directory: {run_id_dir}")
    bootstrap_run_dir(run_id_dir, plan_text)
    print(f"\nRun directory ready: {run_id_dir}\n")

    if not args.launch:
        print("Next step — run the pipeline:")
        print(
            f"  RUN_ID_DIR={run_id_dir} "
            "python -m worker_plan_internal.plan.run_plan_pipeline\n"
        )
        return 0

    # --launch: invoke the pipeline in-process.
    print("Launching pipeline …\n")
    env = {**os.environ, "RUN_ID_DIR": str(run_id_dir)}

    # Run as a subprocess so Luigi can initialise its own logging cleanly.
    result = subprocess.run(
        [sys.executable, "-m", "worker_plan_internal.plan.run_plan_pipeline"],
        env=env,
        cwd=Path(__file__).parent,  # worker_plan/
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
