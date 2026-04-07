"""Extract the pipeline DAG from Luigi task introspection.

Walks the FullPlanPipeline task graph via requires()/output() and produces
a JSON description of every stage: name, output files, primary output, and
upstream stages.  This replaces the hand-maintained registry with a generated
artifact that stays in sync with the actual pipeline code.

Usage:
    cd worker_plan
    python -m worker_plan_internal.flaw_tracer.extract_dag
    python -m worker_plan_internal.flaw_tracer.extract_dag --output pipeline_dag.json
"""
import json
import re
import sys
from pathlib import Path
from typing import Any

import luigi


def _class_name_to_stage_name(class_name: str) -> str:
    """Convert CamelCase task class name to snake_case stage name.

    Removes the 'Task' suffix, then converts CamelCase → snake_case.

    Examples:
        PotentialLeversTask       → potential_levers
        SWOTAnalysisTask          → swot_analysis
        WBSProjectLevel1AndLevel2Task → wbs_project_level1_and_level2
        GovernancePhase1AuditTask → governance_phase1_audit
    """
    name = class_name.removesuffix("Task")
    # Insert underscore between lowercase/digit and uppercase
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore between consecutive uppercase run and uppercase+lowercase
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return name.lower()


def _pick_primary_output(filenames: list[str]) -> str:
    """Pick the best primary output from a list of filenames.

    Preference: .md > .html > non-raw file > first file.
    """
    for ext in (".md", ".html"):
        for f in filenames:
            if f.endswith(ext):
                return f
    # Prefer non-raw files
    non_raw = [f for f in filenames if "_raw" not in f]
    if non_raw:
        return non_raw[0]
    return filenames[0] if filenames else ""


def _extract_output_filenames(task: luigi.Task) -> list[str]:
    """Extract output filenames (basenames) from a task's output() method."""
    try:
        outputs = task.output()
    except Exception:
        return []

    targets: list[Any] = []
    if isinstance(outputs, dict):
        targets = list(outputs.values())
    elif isinstance(outputs, (list, tuple)):
        targets = list(outputs)
    else:
        targets = [outputs]

    filenames: list[str] = []
    for target in targets:
        if hasattr(target, "path"):
            filenames.append(Path(target.path).name)
    return filenames


def _extract_upstream_tasks(task: luigi.Task) -> list[luigi.Task]:
    """Extract upstream task instances from a task's requires() method."""
    try:
        deps = task.requires()
    except Exception:
        return []

    if deps is None:
        return []
    if isinstance(deps, dict):
        return list(deps.values())
    if isinstance(deps, (list, tuple)):
        return list(deps)
    if isinstance(deps, luigi.Task):
        return [deps]
    return []


def _output_sort_key(stage: dict[str, Any]) -> tuple[int, int, str]:
    """Sort key: numeric prefix from the primary output filename, then name."""
    filename = stage.get("primary_output", "") or ""
    if not filename and stage.get("output_files"):
        filename = stage["output_files"][0]
    match = re.match(r"(\d+)-?(\d+)?", filename)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        return (major, minor, stage["name"])
    return (9999, 0, stage["name"])


def extract_dag() -> list[dict[str, Any]]:
    """Walk the FullPlanPipeline task graph and extract DAG info.

    Returns a list of stage dicts sorted by output file prefix (pipeline order).
    """
    from worker_plan_internal.plan.stages.full_plan_pipeline import FullPlanPipeline

    root = FullPlanPipeline(run_id_dir=Path("/tmp/_dag_extract_dummy"))

    stages: list[dict[str, Any]] = []
    visited: set[str] = set()

    def _walk(task: luigi.Task) -> None:
        class_name = task.__class__.__name__
        if class_name in visited:
            return
        visited.add(class_name)

        upstream_tasks = _extract_upstream_tasks(task)

        # Recurse into dependencies first (depth-first)
        for dep in upstream_tasks:
            _walk(dep)

        # Skip the orchestrator itself
        if class_name == "FullPlanPipeline":
            return

        stage_name = _class_name_to_stage_name(class_name)
        output_files = _extract_output_filenames(task)
        primary_output = _pick_primary_output(output_files)
        upstream_stage_names = sorted(set(
            _class_name_to_stage_name(dep.__class__.__name__)
            for dep in upstream_tasks
        ))

        stages.append({
            "name": stage_name,
            "output_files": output_files,
            "primary_output": primary_output,
            "upstream_stages": upstream_stage_names,
        })

    _walk(root)

    stages.sort(key=_output_sort_key)
    return stages


def main() -> None:
    output_path = None
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--output":
        output_path = args[1]

    stages = extract_dag()
    dag_json = json.dumps(stages, indent=2, ensure_ascii=False)

    if output_path:
        Path(output_path).write_text(dag_json + "\n", encoding="utf-8")
        print(f"Wrote {len(stages)} stages to {output_path}", file=sys.stderr)
    else:
        print(dag_json)


if __name__ == "__main__":
    main()
