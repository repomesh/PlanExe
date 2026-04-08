# worker_plan/worker_plan_internal/rca/tracer.py
"""Recursive depth-first root cause analyzer for PlanExe pipeline outputs."""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

from llama_index.core.llms.llm import LLM

from worker_plan_internal.rca.registry import (
    find_node_by_filename,
    get_upstream_files,
    get_source_code_paths,
)
from worker_plan_internal.rca.prompts import (
    ProblemIdentificationResult,
    UpstreamCheckResult,
    SourceCodeAnalysisResult,
    build_problem_identification_messages,
    build_upstream_check_messages,
    build_source_code_analysis_messages,
)
from worker_plan_internal.llm_util.llm_executor import LLMExecutor

logger = logging.getLogger(__name__)


@dataclass
class TraceEntry:
    """One hop in a problem's upstream trace."""
    node: str
    file: str
    evidence: str
    is_origin: bool = False


@dataclass
class OriginInfo:
    """Source code analysis at a problem's origin node."""
    node: str
    file: str
    source_code_files: list[str]
    category: str  # "prompt_fixable", "domain_complexity", or "missing_input"
    likely_cause: str
    suggestion: str


@dataclass
class TracedProblem:
    """A fully traced problem with its upstream chain."""
    id: str
    description: str
    severity: str
    starting_evidence: str
    trace: list[TraceEntry]
    origin_node: str | None = None
    origin: OriginInfo | None = None
    depth: int = 0
    trace_complete: bool = True


@dataclass
class RCAResult:
    """Complete result of a root cause analysis run."""
    starting_file: str
    problem_description: str
    output_dir: str
    problems: list[TracedProblem]
    llm_calls_made: int = 0


class EventLogger:
    """Appends JSON events to a JSONL file for live monitoring.

    Usage: tail -f events.jsonl
    """

    def __init__(self, path: Path | None):
        self._path = path
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Truncate on start so each run is a fresh log
            self._path.write_text("", encoding="utf-8")

    def log(self, event_type: str, **data: object) -> None:
        if self._path is None:
            return
        entry = {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": event_type,
            **data,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class RootCauseAnalyzer:
    """Traces problems upstream through the PlanExe pipeline DAG."""

    def __init__(
        self,
        output_dir: Path,
        llm_executor: LLMExecutor,
        max_depth: int = 15,
        verbose: bool = False,
        events_path: Path | None = None,
    ):
        self.output_dir = output_dir
        self.llm_executor = llm_executor
        self.max_depth = max_depth
        self.verbose = verbose
        self._llm_calls = 0
        self._checked: set[tuple[str, str]] = set()  # (node_name, problem_description) dedup
        self._events = EventLogger(events_path)

    def trace(self, starting_file: str, problem_description: str) -> RCAResult:
        """Main entry point. Identify problems and trace each upstream."""
        self._llm_calls = 0
        self._checked.clear()

        file_path = self.output_dir / starting_file
        if not file_path.exists():
            raise FileNotFoundError(f"Starting file not found: {file_path}")

        file_content = file_path.read_text(encoding="utf-8")
        found_node = find_node_by_filename(starting_file)
        node_name = found_node.name if found_node else "unknown"

        # Phase 1: Identify problems
        self._log(f"Phase 1: Identifying problems in {starting_file}")
        self._events.log("phase1_start", file=starting_file, node=node_name)
        identified = self._identify_problems(starting_file, file_content, problem_description)
        self._log(f"  Found {len(identified.problems)} problem(s)")
        self._events.log("phase1_done", problems_found=len(identified.problems),
                         summaries=[p.description for p in identified.problems])

        traced_problems: list[TracedProblem] = []
        for i, problem in enumerate(identified.problems):
            problem_id = f"problem_{i + 1:03d}"
            self._log(f"\nTracing {problem_id}: {problem.description}")
            self._events.log("trace_problem_start", problem_id=problem_id,
                             problem_index=i + 1, problem_total=len(identified.problems),
                             description=problem.description, severity=problem.severity)

            starting_entry = TraceEntry(
                node=node_name,
                file=starting_file,
                evidence=problem.evidence,
                is_origin=False,
            )

            traced = TracedProblem(
                id=problem_id,
                description=problem.description,
                severity=problem.severity,
                starting_evidence=problem.evidence,
                trace=[starting_entry],
            )

            if found_node and self.max_depth > 0:
                self._trace_upstream(traced, node_name, problem.description, problem.evidence, depth=0)

            # Mark the last trace entry as origin if no deeper origin was found
            if traced.origin_node is None and traced.trace:
                last = traced.trace[-1]
                last.is_origin = True
                traced.origin_node = last.node
                traced.depth = len(traced.trace) - 1

            # Phase 3: Source code analysis at origin (always, when origin is known)
            if traced.origin_node is not None:
                self._events.log("phase3_start", problem_id=problem_id, origin_node=traced.origin_node)
                self._analyze_source_code(
                    traced, traced.origin_node, problem.description,
                    next((e.evidence for e in traced.trace if e.node == traced.origin_node), problem.evidence)
                )

            self._events.log("trace_problem_done", problem_id=problem_id,
                             origin_node=traced.origin_node, depth=traced.depth)
            traced_problems.append(traced)

        # Sort by depth (deepest origin first)
        traced_problems.sort(key=lambda f: f.depth, reverse=True)

        self._events.log("trace_complete", total_problems=len(traced_problems),
                         llm_calls=self._llm_calls)

        return RCAResult(
            starting_file=starting_file,
            problem_description=problem_description,
            output_dir=str(self.output_dir),
            problems=traced_problems,
            llm_calls_made=self._llm_calls,
        )

    def _identify_problems(self, filename: str, file_content: str, user_description: str) -> ProblemIdentificationResult:
        """Phase 1: Ask LLM to identify discrete problems in the starting file."""
        messages = build_problem_identification_messages(filename, file_content, user_description)

        def execute(llm: LLM) -> ProblemIdentificationResult:
            sllm = llm.as_structured_llm(ProblemIdentificationResult)
            response = sllm.chat(messages)
            return response.raw

        self._llm_calls += 1
        return self.llm_executor.run(execute)

    def _check_upstream(self, problem_description: str, evidence: str, upstream_filename: str, upstream_content: str) -> UpstreamCheckResult:
        """Phase 2: Ask LLM if a problem exists in an upstream file."""
        messages = build_upstream_check_messages(problem_description, evidence, upstream_filename, upstream_content)

        def execute(llm: LLM) -> UpstreamCheckResult:
            sllm = llm.as_structured_llm(UpstreamCheckResult)
            response = sllm.chat(messages)
            return response.raw

        self._llm_calls += 1
        return self.llm_executor.run(execute)

    def _trace_upstream(
        self,
        traced: TracedProblem,
        current_node: str,
        problem_description: str,
        evidence: str,
        depth: int,
    ) -> None:
        """Recursively trace a problem through upstream nodes."""
        if depth >= self.max_depth:
            traced.trace_complete = False
            self._log(f"  Max depth {self.max_depth} reached at {current_node}")
            return

        upstream_files = get_upstream_files(current_node, self.output_dir)
        if not upstream_files:
            return  # No upstream = this is the origin

        found_upstream = False
        for upstream_name, upstream_path in upstream_files:
            # Dedup key uses problem_description so different problems get independent
            # upstream checks. If the LLM returns duplicate descriptions, they
            # share check results.
            dedup_key = (upstream_name, problem_description)
            if dedup_key in self._checked:
                self._log(f"  Skipping {upstream_name} (already checked for this problem)")
                continue
            self._checked.add(dedup_key)

            upstream_content = upstream_path.read_text(encoding="utf-8")
            self._log(f"  Checking upstream: {upstream_name} ({upstream_path.name})")
            self._events.log("upstream_check", node=upstream_name,
                             file=upstream_path.name, depth=depth)

            result = self._check_upstream(problem_description, evidence, upstream_path.name, upstream_content)

            if result.found:
                self._log(f"  -> FOUND in {upstream_name}")
                self._events.log("upstream_found", node=upstream_name,
                                 file=upstream_path.name, depth=depth)
                found_upstream = True
                entry = TraceEntry(
                    node=upstream_name,
                    file=upstream_path.name,
                    evidence=result.evidence or "",
                    is_origin=False,
                )
                traced.trace.append(entry)

                # Recurse deeper
                self._trace_upstream(
                    traced, upstream_name, problem_description,
                    result.evidence or evidence, depth + 1,
                )
                # First-match-wins: once an origin is found in one upstream
                # branch, stop exploring others.
                if traced.origin_node is not None:
                    return

        if not found_upstream:
            # Current node is the origin — problem exists here but not in any upstream
            traced.origin_node = current_node
            traced.depth = len(traced.trace) - 1
            self._events.log("origin_found", node=current_node, depth=traced.depth)
            # Mark the current node entry as origin
            for entry in traced.trace:
                if entry.node == current_node:
                    entry.is_origin = True

    def _analyze_source_code(self, traced: TracedProblem, node_name: str, problem_description: str, evidence: str) -> None:
        """Phase 3: Analyze source code at the origin node."""
        source_paths = get_source_code_paths(node_name)
        if not source_paths:
            return

        source_contents: list[tuple[str, str]] = []
        for path in source_paths:
            if path.exists():
                content = path.read_text(encoding="utf-8")
                short_name = f"{path.parent.name}/{path.name}"
                source_contents.append((short_name, content))

        if not source_contents:
            return

        self._log(f"  Phase 3: Analyzing source code for {node_name}")
        messages = build_source_code_analysis_messages(problem_description, evidence, source_contents)

        def execute(llm: LLM) -> SourceCodeAnalysisResult:
            sllm = llm.as_structured_llm(SourceCodeAnalysisResult)
            response = sllm.chat(messages)
            return response.raw

        self._llm_calls += 1
        try:
            analysis = self.llm_executor.run(execute)
            source_file_names = [name for name, _ in source_contents]
            traced.origin = OriginInfo(
                node=node_name,
                file=traced.trace[-1].file if traced.trace else "",
                source_code_files=source_file_names,
                category=analysis.category,
                likely_cause=analysis.likely_cause,
                suggestion=analysis.suggestion,
            )
        except Exception as e:
            logger.warning(f"Source code analysis failed for {node_name}: {e}")

    def _log(self, message: str) -> None:
        """Print to stderr if verbose mode is enabled."""
        if self.verbose:
            print(message, file=sys.stderr)
