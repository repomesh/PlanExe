# worker_plan/worker_plan_internal/flaw_tracer/__main__.py
"""CLI entry point for the flaw tracer.

Usage:
    python -m worker_plan_internal.flaw_tracer \
        --dir /path/to/output \
        --file 030-report.html \
        --flaw "The budget appears unvalidated..." \
        --output-dir /path/to/output \
        --max-depth 15 \
        --verbose
"""
import argparse
import sys
from pathlib import Path

from worker_plan_internal.flaw_tracer.tracer import FlawTracer
from worker_plan_internal.flaw_tracer.output import write_json_report, write_markdown_report
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelFromName, RetryConfig
from worker_plan_internal.llm_factory import get_llm_names_by_priority


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace flaws in PlanExe reports upstream to their root cause.",
    )
    parser.add_argument(
        "--dir", required=True, type=Path,
        help="Path to the output directory containing intermediary files",
    )
    parser.add_argument(
        "--file", required=True,
        help="Starting file to analyze (relative to --dir)",
    )
    parser.add_argument(
        "--flaw", required=True,
        help="Text description of the observed flaw(s)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Where to write flaw_trace.json and flaw_trace.md (defaults to --dir)",
    )
    parser.add_argument(
        "--max-depth", type=int, default=15,
        help="Maximum upstream hops per flaw (default: 15)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print each LLM call and result to stderr",
    )
    args = parser.parse_args()

    output_dir: Path = args.dir.resolve()
    if not output_dir.is_dir():
        print(f"Error: --dir is not a directory: {output_dir}", file=sys.stderr)
        sys.exit(1)

    starting_file = args.file
    if not (output_dir / starting_file).exists():
        print(f"Error: starting file not found: {output_dir / starting_file}", file=sys.stderr)
        sys.exit(1)

    report_dir: Path = (args.output_dir or args.dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    # Set up LLM executor with priority-ordered models from the active profile
    llm_names = get_llm_names_by_priority()
    if not llm_names:
        print("Error: no LLM models configured. Check PLANEXE_MODEL_PROFILE.", file=sys.stderr)
        sys.exit(1)

    llm_models = LLMModelFromName.from_names(llm_names)
    executor = LLMExecutor(
        llm_models=llm_models,
        retry_config=RetryConfig(max_retries=2),
        max_validation_retries=1,
    )

    events_path = report_dir / "events.jsonl"

    tracer = FlawTracer(
        output_dir=output_dir,
        llm_executor=executor,
        max_depth=args.max_depth,
        verbose=args.verbose,
        events_path=events_path,
    )

    print(f"Tracing flaws in {starting_file}...", file=sys.stderr)
    result = tracer.trace(starting_file, args.flaw)

    # Write reports
    json_path = report_dir / "flaw_trace.json"
    md_path = report_dir / "flaw_trace.md"
    write_json_report(result, json_path)
    write_markdown_report(result, md_path)

    # Print summary
    print(f"\nFlaws found: {len(result.flaws)}", file=sys.stderr)
    if result.flaws:
        deepest = max(result.flaws, key=lambda f: f.depth)
        print(f"Deepest origin: {deepest.origin_node} (depth {deepest.depth})", file=sys.stderr)
    print(f"LLM calls made: {result.llm_calls_made}", file=sys.stderr)
    print(f"\nReports written:", file=sys.stderr)
    print(f"  JSON: {json_path}", file=sys.stderr)
    print(f"  Markdown: {md_path}", file=sys.stderr)
    print(f"  Events: {events_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
