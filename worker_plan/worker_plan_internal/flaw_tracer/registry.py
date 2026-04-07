# worker_plan/worker_plan_internal/flaw_tracer/registry.py
"""DAG registry for the flaw tracer, built from Luigi task introspection.

Replaces the former hand-maintained static registry with data extracted
from the actual pipeline via extract_dag.  The public API is unchanged:
  - find_stage_by_filename(filename) -> NodeInfo | None
  - get_upstream_files(stage_name, output_dir) -> list[tuple[str, Path]]
  - get_source_code_paths(stage_name) -> list[Path]
"""
from dataclasses import dataclass
from pathlib import Path

from worker_plan_internal.extract_dag import extract_dag

# Base path for source code, relative to worker_plan/
_SOURCE_BASE = Path(__file__).resolve().parent.parent.parent  # worker_plan/


@dataclass(frozen=True)
class NodeInfo:
    """One pipeline node."""
    name: str
    output_files: tuple[str, ...]
    primary_output: str  # preferred file to read when checking for flaws
    depends_on: tuple[str, ...] = ()
    source_code_files: tuple[str, ...] = ()


def _pick_primary_output(filenames: list[str]) -> str:
    """Pick the best file to read when checking a stage for flaws.

    Preference: .md > .html > non-raw file > first file.
    """
    for ext in (".md", ".html"):
        for f in filenames:
            if f.endswith(ext):
                return f
    non_raw = [f for f in filenames if "_raw" not in f]
    if non_raw:
        return non_raw[0]
    return filenames[0] if filenames else ""


def _build_registry() -> tuple[NodeInfo, ...]:
    """Build the registry from Luigi task introspection."""
    dag = extract_dag()
    stages = []
    for node in dag["nodes"]:
        output_files = tuple(node["output_files"])
        stages.append(NodeInfo(
            name=node["id"],
            output_files=output_files,
            primary_output=_pick_primary_output(node["output_files"]),
            depends_on=tuple(node["depends_on"]),
            source_code_files=tuple(node["source_files"]),
        ))
    return tuple(stages)


# ── Build once at import time ──────────────────────────────────────────

STAGES: tuple[NodeInfo, ...] = _build_registry()

_STAGE_BY_NAME: dict[str, NodeInfo] = {s.name: s for s in STAGES}
_STAGE_BY_FILENAME: dict[str, NodeInfo] = {}
for _stage in STAGES:
    for _fname in _stage.output_files:
        _STAGE_BY_FILENAME[_fname] = _stage


def find_stage_by_filename(filename: str) -> NodeInfo | None:
    """Given an output filename, return the stage that produced it."""
    return _STAGE_BY_FILENAME.get(filename)


def get_upstream_files(stage_name: str, output_dir: Path) -> list[tuple[str, Path]]:
    """Return (stage_name, file_path) pairs for upstream stages whose primary output exists on disk."""
    stage = _STAGE_BY_NAME.get(stage_name)
    if stage is None:
        return []

    result = []
    for upstream_name in stage.depends_on:
        upstream_stage = _STAGE_BY_NAME.get(upstream_name)
        if upstream_stage is None:
            continue
        primary_path = output_dir / upstream_stage.primary_output
        if primary_path.exists():
            result.append((upstream_name, primary_path))
    return result


def get_source_code_paths(stage_name: str) -> list[Path]:
    """Return absolute paths to source code files for a stage."""
    stage = _STAGE_BY_NAME.get(stage_name)
    if stage is None:
        return []
    return [_SOURCE_BASE / f for f in stage.source_code_files]
