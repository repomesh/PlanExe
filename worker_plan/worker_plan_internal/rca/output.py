# worker_plan/worker_plan_internal/rca/output.py
"""JSON and markdown report generation for root cause analysis results."""
import json
from datetime import datetime, UTC
from pathlib import Path

from worker_plan_internal.rca.tracer import RCAResult


def write_json_report(result: RCAResult, output_path: Path) -> None:
    """Write the RCA result as a JSON file."""
    data = {
        "input": {
            "starting_file": result.starting_file,
            "problem_description": result.problem_description,
            "output_dir": result.output_dir,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "problems": [],
        "summary": {
            "total_problems": len(result.problems),
            "deepest_origin_node": None,
            "deepest_origin_depth": 0,
            "llm_calls_made": result.llm_calls_made,
        },
    }

    max_depth = 0
    deepest_node = None

    for problem in result.problems:
        problem_data = {
            "id": problem.id,
            "description": problem.description,
            "severity": problem.severity,
            "starting_evidence": problem.starting_evidence,
            "trace": [
                {
                    "node": entry.node,
                    "file": entry.file,
                    "evidence": entry.evidence,
                    "is_origin": entry.is_origin,
                }
                for entry in problem.trace
            ],
            "origin": None,
            "depth": problem.depth,
            "trace_complete": problem.trace_complete,
        }

        if problem.origin:
            problem_data["origin"] = {
                "node": problem.origin.node,
                "file": problem.origin.file,
                "source_code_files": problem.origin.source_code_files,
                "category": problem.origin.category,
                "likely_cause": problem.origin.likely_cause,
                "suggestion": problem.origin.suggestion,
            }

        if problem.depth > max_depth:
            max_depth = problem.depth
            deepest_node = problem.origin_node

        data["problems"].append(problem_data)

    data["problems"].sort(key=lambda p: p["depth"], reverse=True)
    data["summary"]["deepest_origin_node"] = deepest_node
    data["summary"]["deepest_origin_depth"] = max_depth

    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown_report(result: RCAResult, output_path: Path) -> None:
    """Write the RCA result as a markdown report."""
    lines: list[str] = []
    lines.append("# Root Cause Analysis Report")
    lines.append("")
    lines.append(f"**Input:** {result.starting_file}")
    lines.append(f"**Problems found:** {len(result.problems)}")

    if result.problems:
        deepest = max(result.problems, key=lambda p: p.depth)
        lines.append(f"**Deepest origin:** {deepest.origin_node} (depth {deepest.depth})")
    lines.append(f"**LLM calls:** {result.llm_calls_made}")
    lines.append("")

    sorted_problems = sorted(result.problems, key=lambda p: p.depth, reverse=True)
    for problem in sorted_problems:
        lines.append("---")
        lines.append("")
        lines.append(f"## {problem.id.replace('_', ' ').title()} ({problem.severity}): {problem.description}")
        lines.append("")

        # Trace chain summary
        node_names = [entry.node for entry in problem.trace]
        chain_parts = []
        for name in node_names:
            if name == problem.origin_node:
                chain_parts.append(f"**{name}** (origin)")
            else:
                chain_parts.append(name)
        lines.append(f"**Trace:** {' -> '.join(chain_parts)}")
        lines.append("")

        if not problem.trace_complete:
            lines.append("*Note: trace incomplete — max depth reached.*")
            lines.append("")

        # Trace table
        lines.append("| Node | File | Evidence |")
        lines.append("|-------|------|----------|")
        for entry in problem.trace:
            node_cell = f"**{entry.node}**" if entry.is_origin else entry.node
            evidence_cell = _escape_table_cell(entry.evidence)
            lines.append(f"| {node_cell} | {entry.file} | {evidence_cell} |")
        lines.append("")

        # Origin analysis
        if problem.origin:
            category_labels = {
                "prompt_fixable": "Prompt fixable",
                "domain_complexity": "Domain complexity",
                "missing_input": "Missing input",
            }
            category_label = category_labels.get(problem.origin.category, problem.origin.category)
            lines.append(f"**Category:** {category_label}")
            lines.append("")
            lines.append(f"**Root cause:** {problem.origin.likely_cause}")
            lines.append("")
            lines.append(f"**Source files:** {', '.join(problem.origin.source_code_files)}")
            lines.append("")
            lines.append(f"**Suggestion:** {problem.origin.suggestion}")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _escape_table_cell(text: str) -> str:
    """Escape pipe characters and collapse newlines for markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ")
