# worker_plan/worker_plan_internal/flaw_tracer/output.py
"""JSON and markdown report generation for flaw trace results."""
import json
from datetime import datetime, UTC
from pathlib import Path

from worker_plan_internal.flaw_tracer.tracer import FlawTraceResult


def write_json_report(result: FlawTraceResult, output_path: Path) -> None:
    """Write the flaw trace result as a JSON file."""
    data = {
        "input": {
            "starting_file": result.starting_file,
            "flaw_description": result.flaw_description,
            "output_dir": result.output_dir,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "flaws": [],
        "summary": {
            "total_flaws": len(result.flaws),
            "deepest_origin_node": None,
            "deepest_origin_depth": 0,
            "llm_calls_made": result.llm_calls_made,
        },
    }

    max_depth = 0
    deepest_node = None

    for flaw in result.flaws:
        flaw_data = {
            "id": flaw.id,
            "description": flaw.description,
            "severity": flaw.severity,
            "starting_evidence": flaw.starting_evidence,
            "trace": [
                {
                    "node": entry.node,
                    "file": entry.file,
                    "evidence": entry.evidence,
                    "is_origin": entry.is_origin,
                }
                for entry in flaw.trace
            ],
            "origin": None,
            "depth": flaw.depth,
            "trace_complete": flaw.trace_complete,
        }

        if flaw.origin:
            flaw_data["origin"] = {
                "node": flaw.origin.node,
                "file": flaw.origin.file,
                "source_code_files": flaw.origin.source_code_files,
                "category": flaw.origin.category,
                "likely_cause": flaw.origin.likely_cause,
                "suggestion": flaw.origin.suggestion,
            }

        if flaw.depth > max_depth:
            max_depth = flaw.depth
            deepest_node = flaw.origin_node

        data["flaws"].append(flaw_data)

    data["flaws"].sort(key=lambda f: f["depth"], reverse=True)
    data["summary"]["deepest_origin_node"] = deepest_node
    data["summary"]["deepest_origin_depth"] = max_depth

    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(result: FlawTraceResult, output_path: Path) -> None:
    """Write the flaw trace result as a markdown report."""
    lines: list[str] = []
    lines.append("# Flaw Trace Report")
    lines.append("")
    lines.append(f"**Input:** {result.starting_file}")
    lines.append(f"**Flaws found:** {len(result.flaws)}")

    if result.flaws:
        deepest = max(result.flaws, key=lambda f: f.depth)
        lines.append(f"**Deepest origin:** {deepest.origin_node} (depth {deepest.depth})")
    lines.append(f"**LLM calls:** {result.llm_calls_made}")
    lines.append("")

    sorted_flaws = sorted(result.flaws, key=lambda f: f.depth, reverse=True)
    for flaw in sorted_flaws:
        lines.append("---")
        lines.append("")
        lines.append(f"## {flaw.id.replace('_', ' ').title()} ({flaw.severity}): {flaw.description}")
        lines.append("")

        # Trace chain summary
        node_names = [entry.node for entry in flaw.trace]
        chain_parts = []
        for name in node_names:
            if name == flaw.origin_node:
                chain_parts.append(f"**{name}** (origin)")
            else:
                chain_parts.append(name)
        lines.append(f"**Trace:** {' -> '.join(chain_parts)}")
        lines.append("")

        if not flaw.trace_complete:
            lines.append("*Note: trace incomplete — max depth reached.*")
            lines.append("")

        # Trace table
        lines.append("| Node | File | Evidence |")
        lines.append("|-------|------|----------|")
        for entry in flaw.trace:
            node_cell = f"**{entry.node}**" if entry.is_origin else entry.node
            evidence_cell = _escape_table_cell(entry.evidence)
            lines.append(f"| {node_cell} | {entry.file} | {evidence_cell} |")
        lines.append("")

        # Origin analysis
        if flaw.origin:
            category_labels = {
                "prompt_fixable": "Prompt fixable",
                "domain_complexity": "Domain complexity",
                "missing_input": "Missing input",
            }
            category_label = category_labels.get(flaw.origin.category, flaw.origin.category)
            lines.append(f"**Category:** {category_label}")
            lines.append("")
            lines.append(f"**Root cause:** {flaw.origin.likely_cause}")
            lines.append("")
            lines.append(f"**Source files:** {', '.join(flaw.origin.source_code_files)}")
            lines.append("")
            lines.append(f"**Suggestion:** {flaw.origin.suggestion}")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _escape_table_cell(text: str) -> str:
    """Escape pipe characters and collapse newlines for markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ")
