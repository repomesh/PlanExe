# worker_plan/worker_plan_internal/flaw_tracer/tracer.py
"""Recursive depth-first flaw tracer for PlanExe pipeline outputs."""
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from llama_index.core.llms.llm import LLM

from worker_plan_internal.flaw_tracer.registry import (
    find_stage_by_filename,
    get_upstream_files,
    get_source_code_paths,
)
from worker_plan_internal.flaw_tracer.prompts import (
    FlawIdentificationResult,
    UpstreamCheckResult,
    SourceCodeAnalysisResult,
    build_flaw_identification_messages,
    build_upstream_check_messages,
    build_source_code_analysis_messages,
)
from worker_plan_internal.llm_util.llm_executor import LLMExecutor

logger = logging.getLogger(__name__)


@dataclass
class TraceEntry:
    """One hop in a flaw's upstream trace."""
    stage: str
    file: str
    evidence: str
    is_origin: bool = False


@dataclass
class OriginInfo:
    """Source code analysis at a flaw's origin stage."""
    stage: str
    file: str
    source_code_files: list[str]
    likely_cause: str
    suggestion: str


@dataclass
class TracedFlaw:
    """A fully traced flaw with its upstream chain."""
    id: str
    description: str
    severity: str
    starting_evidence: str
    trace: list[TraceEntry]
    origin_stage: Optional[str] = None
    origin: Optional[OriginInfo] = None
    depth: int = 0
    trace_complete: bool = True


@dataclass
class FlawTraceResult:
    """Complete result of a flaw trace run."""
    starting_file: str
    flaw_description: str
    output_dir: str
    flaws: list[TracedFlaw]
    llm_calls_made: int = 0


class FlawTracer:
    """Traces flaws upstream through the PlanExe pipeline DAG."""

    def __init__(
        self,
        output_dir: Path,
        llm_executor: LLMExecutor,
        source_code_base: Path,
        max_depth: int = 15,
        verbose: bool = False,
    ):
        self.output_dir = output_dir
        self.llm_executor = llm_executor
        self.source_code_base = source_code_base
        self.max_depth = max_depth
        self.verbose = verbose
        self._llm_calls = 0
        self._checked: set[tuple[str, str]] = set()  # (stage_name, flaw_description) dedup

    def trace(self, starting_file: str, flaw_description: str) -> FlawTraceResult:
        """Main entry point. Identify flaws and trace each upstream."""
        self._llm_calls = 0
        self._checked.clear()

        file_path = self.output_dir / starting_file
        if not file_path.exists():
            raise FileNotFoundError(f"Starting file not found: {file_path}")

        file_content = file_path.read_text(encoding="utf-8")
        stage = find_stage_by_filename(starting_file)
        stage_name = stage.name if stage else "unknown"

        # Phase 1: Identify flaws
        self._log(f"Phase 1: Identifying flaws in {starting_file}")
        identified = self._identify_flaws(starting_file, file_content, flaw_description)
        self._log(f"  Found {len(identified.flaws)} flaw(s)")

        traced_flaws: list[TracedFlaw] = []
        for i, flaw in enumerate(identified.flaws):
            flaw_id = f"flaw_{i + 1:03d}"
            self._log(f"\nTracing {flaw_id}: {flaw.description}")

            starting_entry = TraceEntry(
                stage=stage_name,
                file=starting_file,
                evidence=flaw.evidence,
                is_origin=False,
            )

            traced = TracedFlaw(
                id=flaw_id,
                description=flaw.description,
                severity=flaw.severity,
                starting_evidence=flaw.evidence,
                trace=[starting_entry],
            )

            if stage and self.max_depth > 0:
                self._trace_upstream(traced, stage_name, flaw.description, flaw.evidence, depth=0)

            # Mark the last trace entry as origin if no deeper origin was found
            if traced.origin_stage is None and traced.trace:
                last = traced.trace[-1]
                last.is_origin = True
                traced.origin_stage = last.stage
                traced.depth = len(traced.trace) - 1

            # Phase 3: Source code analysis at origin (always, when origin is known)
            if traced.origin_stage is not None:
                self._analyze_source_code(
                    traced, traced.origin_stage, flaw.description,
                    next((e.evidence for e in traced.trace if e.stage == traced.origin_stage), flaw.evidence)
                )

            traced_flaws.append(traced)

        # Sort by depth (deepest origin first)
        traced_flaws.sort(key=lambda f: f.depth, reverse=True)

        return FlawTraceResult(
            starting_file=starting_file,
            flaw_description=flaw_description,
            output_dir=str(self.output_dir),
            flaws=traced_flaws,
            llm_calls_made=self._llm_calls,
        )

    def _identify_flaws(self, filename: str, file_content: str, user_description: str) -> FlawIdentificationResult:
        """Phase 1: Ask LLM to identify discrete flaws in the starting file."""
        messages = build_flaw_identification_messages(filename, file_content, user_description)

        def execute(llm: LLM) -> FlawIdentificationResult:
            sllm = llm.as_structured_llm(FlawIdentificationResult)
            response = sllm.chat(messages)
            return response.raw

        self._llm_calls += 1
        return self.llm_executor.run(execute)

    def _check_upstream(self, flaw_description: str, evidence: str, upstream_filename: str, upstream_content: str) -> UpstreamCheckResult:
        """Phase 2: Ask LLM if a flaw exists in an upstream file."""
        messages = build_upstream_check_messages(flaw_description, evidence, upstream_filename, upstream_content)

        def execute(llm: LLM) -> UpstreamCheckResult:
            sllm = llm.as_structured_llm(UpstreamCheckResult)
            response = sllm.chat(messages)
            return response.raw

        self._llm_calls += 1
        return self.llm_executor.run(execute)

    def _trace_upstream(
        self,
        traced: TracedFlaw,
        current_stage: str,
        flaw_description: str,
        evidence: str,
        depth: int,
    ) -> None:
        """Recursively trace a flaw through upstream stages."""
        if depth >= self.max_depth:
            traced.trace_complete = False
            self._log(f"  Max depth {self.max_depth} reached at {current_stage}")
            return

        upstream_files = get_upstream_files(current_stage, self.output_dir)
        if not upstream_files:
            return  # No upstream = this is the origin

        found_upstream = False
        for upstream_name, upstream_path in upstream_files:
            dedup_key = (upstream_name, flaw_description)
            if dedup_key in self._checked:
                self._log(f"  Skipping {upstream_name} (already checked for this flaw)")
                continue
            self._checked.add(dedup_key)

            upstream_content = upstream_path.read_text(encoding="utf-8")
            self._log(f"  Checking upstream: {upstream_name} ({upstream_path.name})")

            result = self._check_upstream(flaw_description, evidence, upstream_path.name, upstream_content)

            if result.found:
                self._log(f"  -> FOUND in {upstream_name}")
                found_upstream = True
                entry = TraceEntry(
                    stage=upstream_name,
                    file=upstream_path.name,
                    evidence=result.evidence or "",
                    is_origin=False,
                )
                traced.trace.append(entry)

                # Recurse deeper
                self._trace_upstream(
                    traced, upstream_name, flaw_description,
                    result.evidence or evidence, depth + 1,
                )
                # After recursion, if origin was found deeper, stop tracing other branches
                if traced.origin_stage is not None:
                    return

        if not found_upstream:
            # Current stage is the origin — flaw exists here but not in any upstream
            traced.origin_stage = current_stage
            traced.depth = len(traced.trace)
            # Mark the current stage entry as origin
            for entry in traced.trace:
                if entry.stage == current_stage:
                    entry.is_origin = True

    def _analyze_source_code(self, traced: TracedFlaw, stage_name: str, flaw_description: str, evidence: str) -> None:
        """Phase 3: Analyze source code at the origin stage."""
        source_paths = get_source_code_paths(stage_name)
        if not source_paths:
            return

        source_contents: list[tuple[str, str]] = []
        for path in source_paths:
            if path.exists():
                content = path.read_text(encoding="utf-8")
                source_contents.append((path.name, content))

        if not source_contents:
            return

        self._log(f"  Phase 3: Analyzing source code for {stage_name}")
        messages = build_source_code_analysis_messages(flaw_description, evidence, source_contents)

        def execute(llm: LLM) -> SourceCodeAnalysisResult:
            sllm = llm.as_structured_llm(SourceCodeAnalysisResult)
            response = sllm.chat(messages)
            return response.raw

        self._llm_calls += 1
        try:
            analysis = self.llm_executor.run(execute)
            source_file_names = [name for name, _ in source_contents]
            traced.origin = OriginInfo(
                stage=stage_name,
                file=traced.trace[-1].file if traced.trace else "",
                source_code_files=source_file_names,
                likely_cause=analysis.likely_cause,
                suggestion=analysis.suggestion,
            )
        except Exception as e:
            logger.warning(f"Source code analysis failed for {stage_name}: {e}")

    def _log(self, message: str) -> None:
        """Print to stderr if verbose mode is enabled."""
        if self.verbose:
            print(message, file=sys.stderr)
