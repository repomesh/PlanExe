"""Extract the pipeline DAG from Luigi task introspection.

Walks the FullPlanPipeline task graph via requires()/output() and produces
a JSON description of every stage: name, output files, upstream stages,
and source code files.  This replaces the hand-maintained registry with a
generated artifact that stays in sync with the actual pipeline code.

Usage:
    cd worker_plan
    python -m worker_plan_internal.extract_dag
    python -m worker_plan_internal.extract_dag --output pipeline_dag.json
"""
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

import luigi

_WORKER_PLAN_DIR = Path(__file__).resolve().parent.parent  # worker_plan/

# Module prefixes that are infrastructure/utilities, not implementation logic.
# Imports from these are excluded from source_files auto-detection.
_INFRASTRUCTURE_PREFIXES = (
    "worker_plan_internal.plan.stages.",
    "worker_plan_internal.plan.run_plan_pipeline",
    "worker_plan_internal.plan.pipeline_environment",
    "worker_plan_internal.plan.ping_llm",
    "worker_plan_internal.llm_util.",
    "worker_plan_internal.llm_factory",
    "worker_plan_internal.luigi_util.",
    "worker_plan_internal.utils.",
    "worker_plan_internal.format_",
    "worker_plan_api.",
)


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


def _detect_implementation_files(cls: type) -> list[str]:
    """Auto-detect implementation source files from module-level imports.

    Scans the module that defines *cls* for classes and functions imported
    from ``worker_plan_internal.*`` that are NOT infrastructure (stages,
    LLM utilities, API types, etc.).  Returns paths relative to worker_plan/.
    """
    module = inspect.getmodule(cls)
    if module is None:
        return []

    files: list[str] = []
    seen_modules: set[str] = set()

    for attr_name in dir(module):
        obj = getattr(module, attr_name, None)
        if obj is None or not (inspect.isclass(obj) or inspect.isfunction(obj)):
            continue

        obj_module_name = getattr(obj, "__module__", "") or ""
        if not obj_module_name.startswith("worker_plan_internal."):
            continue
        if any(obj_module_name.startswith(p) for p in _INFRASTRUCTURE_PREFIXES):
            continue
        if obj_module_name in seen_modules:
            continue
        seen_modules.add(obj_module_name)

        try:
            obj_file = Path(inspect.getfile(obj)).resolve()
            rel = str(obj_file.relative_to(_WORKER_PLAN_DIR))
            if rel not in files:
                files.append(rel)
        except (TypeError, ValueError, OSError):
            continue

    return files


def _extract_source_files(task: luigi.Task) -> list[str]:
    """Get source files: task's own file + auto-detected implementation files."""
    cls = type(task)

    # The task's own file
    result: list[str] = []
    try:
        task_file = Path(inspect.getfile(cls)).resolve()
        result.append(str(task_file.relative_to(_WORKER_PLAN_DIR)))
    except (TypeError, ValueError, OSError):
        pass

    # Supplement with auto-detected implementation files
    for f in _detect_implementation_files(cls):
        if f not in result:
            result.append(f)

    return result


def _output_sort_key(stage: dict[str, Any]) -> tuple[int, int, str]:
    """Sort key: numeric prefix from the first output filename, then name."""
    filename = stage["output_files"][0] if stage.get("output_files") else ""
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

        cls = type(task)
        stage_name = _class_name_to_stage_name(class_name)
        description = cls.description() if hasattr(cls, "description") else ""
        output_files = _extract_output_filenames(task)
        source_files = _extract_source_files(task)
        upstream_stage_names = sorted(set(
            _class_name_to_stage_name(dep.__class__.__name__)
            for dep in upstream_tasks
        ))

        stages.append({
            "name": stage_name,
            "description": description,
            "output_files": output_files,
            "upstream_stages": upstream_stage_names,
            "source_files": source_files,
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
