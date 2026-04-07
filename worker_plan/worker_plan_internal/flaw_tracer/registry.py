# worker_plan/worker_plan_internal/flaw_tracer/registry.py
"""DAG registry for the flaw tracer, built from Luigi task introspection.

Replaces the former hand-maintained static registry with data extracted
from the actual pipeline via extract_dag.  The public API is unchanged:
  - find_node_by_filename(filename) -> NodeInfo | None
  - get_upstream_files(node_name, output_dir) -> list[tuple[str, Path]]
  - get_source_code_paths(node_name) -> list[Path]
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
    depends_on: tuple[str, ...] = ()
    source_code_files: tuple[str, ...] = ()


def _pick_primary_output(filenames: list[str]) -> str:
    """Pick the best file to read when checking a node for flaws.

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
    nodes = []
    for entry in dag["nodes"]:
        output_files = tuple(a["path"] for a in entry["artifacts"])
        nodes.append(NodeInfo(
            name=entry["id"],
            output_files=output_files,
            depends_on=tuple(entry["depends_on"]),
            source_code_files=tuple(f["path"] for f in entry["source_files"]),
        ))
    return tuple(nodes)


# ── Build once at import time ──────────────────────────────────────────

NODES: tuple[NodeInfo, ...] = _build_registry()

_NODE_BY_NAME: dict[str, NodeInfo] = {n.name: n for n in NODES}
_NODE_BY_FILENAME: dict[str, NodeInfo] = {}
for _node in NODES:
    for _fname in _node.output_files:
        _NODE_BY_FILENAME[_fname] = _node


def find_node_by_filename(filename: str) -> NodeInfo | None:
    """Given an output filename, return the node that produced it."""
    return _NODE_BY_FILENAME.get(filename)


def get_upstream_files(node_name: str, output_dir: Path) -> list[tuple[str, Path]]:
    """Return (node_name, file_path) pairs for upstream nodes whose primary output exists on disk."""
    node = _NODE_BY_NAME.get(node_name)
    if node is None:
        return []

    result = []
    for upstream_name in node.depends_on:
        upstream_node = _NODE_BY_NAME.get(upstream_name)
        if upstream_node is None:
            continue
        primary = _pick_primary_output(list(upstream_node.output_files))
        if not primary:
            continue
        primary_path = output_dir / primary
        if primary_path.exists():
            result.append((upstream_name, primary_path))
    return result


def get_source_code_paths(node_name: str) -> list[Path]:
    """Return absolute paths to source code files for a node."""
    node = _NODE_BY_NAME.get(node_name)
    if node is None:
        return []
    return [_SOURCE_BASE / f for f in node.source_code_files]
