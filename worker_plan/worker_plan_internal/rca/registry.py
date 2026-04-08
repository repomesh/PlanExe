# worker_plan/worker_plan_internal/rca/registry.py
"""DAG registry for RCA, built from Luigi task introspection.

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
class NodeInput:
    """One input to a pipeline node: the upstream node name and the artifact it provides."""
    from_node: str
    artifact_path: str


@dataclass(frozen=True)
class NodeInfo:
    """One pipeline node."""
    name: str
    output_files: tuple[str, ...]
    inputs: tuple[NodeInput, ...] = ()
    source_code_files: tuple[str, ...] = ()


def _build_registry() -> tuple[NodeInfo, ...]:
    """Build the registry from Luigi task introspection."""
    dag = extract_dag()
    nodes = []
    for entry in dag["nodes"]:
        output_files = tuple(a["path"] for a in entry["artifacts"])
        inputs = tuple(
            NodeInput(from_node=inp["from_node"], artifact_path=inp["artifact_path"])
            for inp in entry["inputs"]
        )
        nodes.append(NodeInfo(
            name=entry["id"],
            output_files=output_files,
            inputs=inputs,
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
    """Return (node_name, file_path) pairs for upstream nodes whose artifact exists on disk."""
    node = _NODE_BY_NAME.get(node_name)
    if node is None:
        return []

    result = []
    for inp in node.inputs:
        artifact_path = output_dir / inp.artifact_path
        if artifact_path.exists():
            result.append((inp.from_node, artifact_path))
    return result


def get_source_code_paths(node_name: str) -> list[Path]:
    """Return absolute paths to source code files for a node."""
    node = _NODE_BY_NAME.get(node_name)
    if node is None:
        return []
    return [_SOURCE_BASE / f for f in node.source_code_files]
