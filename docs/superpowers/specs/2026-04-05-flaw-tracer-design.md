# Flaw Tracer — Root-Cause Analysis for PlanExe Reports

## Goal

A CLI tool that takes a PlanExe output directory, a starting file, and a flaw description, then recursively traces the flaw upstream through the DAG of intermediary files to find where it originated. Produces both JSON and markdown output. Built on PlanExe's existing LLM infrastructure so it can eventually become a pipeline stage.

## Architecture

The tool performs a recursive depth-first search through the pipeline DAG. Starting from a downstream file where a flaw is observed, it walks upstream one hop at a time — reading input files, asking an LLM whether the flaw or a precursor exists there, and continuing until it reaches a stage where the flaw exists in the output but not in any inputs. At that origin point, it reads the stage's source code to identify the likely cause.

Three LLM prompts drive the analysis: flaw identification (once at the start), upstream checking (at each hop), and source code analysis (at each origin). All use Pydantic models for structured output and LLMExecutor for fallback resilience.

## Components

```
worker_plan/worker_plan_internal/flaw_tracer/
    __init__.py
    __main__.py      — CLI entry point (argparse, LLM setup, orchestration)
    registry.py      — Static DAG mapping: stages, output files, dependencies, source code paths
    tracer.py        — Recursive tracing algorithm
    prompts.py       — Pydantic models and LLM prompt templates
    output.py        — JSON + markdown report generation
```

### `registry.py` — DAG Mapping

A static Python data structure mapping the full pipeline topology. Each entry describes one pipeline stage:

```python
@dataclass
class StageInfo:
    name: str                       # e.g., "potential_levers"
    output_files: list[str]         # e.g., ["002-9-potential_levers_raw.json", "002-10-potential_levers.json"]
    upstream_stages: list[str]      # e.g., ["setup", "identify_purpose", "plan_type", "extract_constraints"]
    source_code_files: list[str]    # Relative to worker_plan/, e.g., ["worker_plan_internal/plan/stages/potential_levers.py", "worker_plan_internal/lever/identify_potential_levers.py"]
```

The registry covers all ~48 pipeline stages. Key functions:

- `find_stage_by_filename(filename: str) -> StageInfo | None` — Given an output filename, return the stage that produced it.
- `get_upstream_files(stage_name: str, output_dir: Path) -> list[tuple[str, Path]]` — Return `(stage_name, file_path)` pairs for all upstream stages, resolved against the output directory. Skip files that don't exist on disk. When a stage has multiple output files (e.g., both `_raw.json` and `.json`), prefer the clean/processed file since that's what downstream stages consume. If only the raw file exists, use that.
- `get_source_code_paths(stage_name: str) -> list[Path]` — Return absolute paths to source code files for a stage.

The mapping is derived from the Luigi task classes (`requires()` and `output()` methods) but hard-coded for reliability. When the pipeline changes, this file needs updating.

### `prompts.py` — Pydantic Models and Prompt Templates

Three Pydantic models for structured LLM output:

```python
class IdentifiedFlaw(BaseModel):
    description: str = Field(description="One-sentence description of the flaw")
    evidence: str = Field(description="Direct quote from the file demonstrating the flaw")
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="HIGH: fabricated data or missing critical analysis. MEDIUM: weak reasoning or vague claims. LOW: minor gaps."
    )

class FlawIdentificationResult(BaseModel):
    flaws: list[IdentifiedFlaw] = Field(description="List of discrete flaws found in the file")

class UpstreamCheckResult(BaseModel):
    found: bool = Field(description="True if this file contains the flaw or a precursor to it")
    evidence: str | None = Field(description="Direct quote from the file if found, null otherwise")
    explanation: str = Field(description="How this connects to the downstream flaw, or why this file is clean")

class SourceCodeAnalysisResult(BaseModel):
    likely_cause: str = Field(description="What in the prompt or logic likely caused the flaw")
    relevant_code_section: str = Field(description="The specific code or prompt text responsible")
    suggestion: str = Field(description="How to fix or prevent this flaw")
```

Three prompt-building functions, each returning a `list[ChatMessage]`:

**`build_flaw_identification_prompt(filename, file_content, user_flaw_description)`**

System message:
```
You are analyzing an intermediary file from a project planning pipeline.
The user has identified problems in this output. Identify each discrete flaw.
For each flaw, provide a short description, a direct quote as evidence, and a severity level.
Only identify real flaws — do not flag stylistic preferences or minor formatting issues.
```

User message contains the filename, file content, and the user's flaw description.

**`build_upstream_check_prompt(flaw_description, evidence_quote, upstream_filename, upstream_file_content)`**

System message:
```
You are tracing a flaw through a project planning pipeline to find where it originated.
A downstream file contains a flaw. You are examining an upstream file that was an input
to the stage that produced the flawed output. Determine if this upstream file contains
the same problem or a precursor to it.
```

User message contains the flaw details and the upstream file content.

**`build_source_code_analysis_prompt(flaw_description, evidence_quote, source_code_contents)`**

System message:
```
A flaw was introduced at this pipeline stage. The flaw exists in its output but NOT
in any of its inputs. Examine the source code to identify what in the prompt text,
logic, or processing likely caused this flaw. Be specific — point to lines or prompt phrases.
```

User message contains the flaw details and the concatenated source code.

### `tracer.py` — Recursive Tracing Algorithm

```python
class FlawTracer:
    def __init__(self, output_dir: Path, llm_executor: LLMExecutor, source_code_base: Path, max_depth: int = 15, verbose: bool = False):
        ...

    def trace(self, starting_file: str, flaw_description: str) -> FlawTraceResult:
        """Main entry point. Returns the complete trace result."""
        ...
```

The `trace` method implements three phases:

**Phase 1 — Identify flaws.**
Read the starting file. Build the flaw identification prompt with the file content and user's description. Call the LLM via `LLMExecutor.run()` using `llm.as_structured_llm(FlawIdentificationResult)`. Returns a list of `IdentifiedFlaw` objects.

**Phase 2 — Recursive upstream trace.**
For each identified flaw, call `_trace_flaw_upstream(flaw, stage_name, current_file, depth)`:

1. Look up the current stage's upstream stages via the registry.
2. For each upstream stage, resolve its output files on disk.
3. Read each upstream file. Build the upstream check prompt. Call the LLM.
4. If `found=True`: append to the trace chain and recurse into that stage's upstream dependencies.
5. If `found=False`: this branch is clean, stop.
6. If depth reaches `max_depth`: stop and mark trace as incomplete.

**Deduplication:** Track which `(stage_name, flaw_description)` pairs have already been analyzed. If two flaws converge on the same upstream file, reuse the earlier result.

**Multiple upstream branches:** When a stage has multiple upstream inputs and the flaw is found in more than one, follow all branches. The trace can fork — the JSON output represents this as a list of trace entries per flaw (each entry has a stage and file), ordered from downstream to upstream.

**Phase 3 — Source code analysis at origin.**
When a flaw is found in a stage's output but not in any of its inputs, that stage is the origin. Read the source code files for that stage (via registry). Build the source code analysis prompt. Call the LLM. Attach the result to the flaw's origin data.

### `output.py` — Report Generation

Two functions:

**`write_json_report(result: FlawTraceResult, output_path: Path)`**

Writes the full trace as JSON:

```json
{
    "input": {
        "starting_file": "030-report.html",
        "flaw_description": "...",
        "output_dir": "/path/to/output",
        "timestamp": "2026-04-05T14:30:00Z"
    },
    "flaws": [
        {
            "id": "flaw_001",
            "description": "Budget of CZK 500,000 is unvalidated",
            "severity": "HIGH",
            "starting_evidence": "quote from starting file...",
            "trace": [
                {
                    "stage": "executive_summary",
                    "file": "025-2-executive_summary.md",
                    "evidence": "...",
                    "is_origin": false
                },
                {
                    "stage": "make_assumptions",
                    "file": "003-5-make_assumptions.md",
                    "evidence": "...",
                    "is_origin": true
                }
            ],
            "origin": {
                "stage": "make_assumptions",
                "file": "003-5-make_assumptions.md",
                "source_code_files": ["stages/make_assumptions.py", "assumption/make_assumptions.py"],
                "likely_cause": "The prompt asks the LLM to...",
                "suggestion": "Add a validation step that..."
            },
            "depth": 2
        }
    ],
    "summary": {
        "total_flaws": 3,
        "deepest_origin_stage": "make_assumptions",
        "deepest_origin_depth": 3,
        "llm_calls_made": 12
    }
}
```

**`write_markdown_report(result: FlawTraceResult, output_path: Path)`**

Writes a human-readable report:

```markdown
# Flaw Trace Report

**Input:** 030-report.html
**Flaws found:** 3
**Deepest origin:** make_assumptions (depth 3)

---

## Flaw 1 (HIGH): Budget of CZK 500,000 is unvalidated

**Trace:** executive_summary -> project_plan -> **make_assumptions** (origin)

| Stage | File | Evidence |
|-------|------|----------|
| executive_summary | 025-2-executive_summary.md | "The budget is CZK 500,000..." |
| project_plan | 005-2-project_plan.md | "Estimated budget: CZK 500,000..." |
| **make_assumptions** | 003-5-make_assumptions.md | "Assume total budget..." |

**Root cause:** The prompt asks the LLM to generate budget assumptions
without requiring external data sources...

**Suggestion:** Add a validation step that...
```

Flaws are sorted by depth (deepest origin first) so the most upstream root cause appears at the top.

### `__main__.py` — CLI Entry Point

```
python -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output \
    --file 030-report.html \
    --flaw "The budget is CZK 500,000 but this number appears unvalidated..." \
    --output-dir /path/to/output \
    --max-depth 15 \
    --verbose
```

Arguments:
- `--dir` (required): Path to the output directory containing intermediary files.
- `--file` (required): Starting file to analyze, relative to `--dir`.
- `--flaw` (required): Text description of the observed flaw(s).
- `--output-dir` (optional): Where to write `flaw_trace.json` and `flaw_trace.md`. Defaults to `--dir`.
- `--max-depth` (optional): Maximum upstream hops per flaw. Default 15.
- `--verbose` (optional): Print each LLM call and result to stderr as the trace runs.

Orchestration:
1. Parse arguments.
2. Load model profile via `PlanExeLLMConfig.load()` and create `LLMExecutor` with priority-ordered models from the profile.
3. Create `FlawTracer` instance.
4. Call `tracer.trace(starting_file, flaw_description)`.
5. Write JSON and markdown reports via `output.py`.
6. Print summary to stdout.

## LLM Infrastructure Integration

- **LLMExecutor** with `LLMModelFromName.from_names()` for multi-model fallback.
- **Pydantic models** with `llm.as_structured_llm()` for all three prompt types.
- **Model profile** loaded from `PLANEXE_MODEL_PROFILE` environment variable (defaults to baseline).
- **RetryConfig** with defaults (2 retries, exponential backoff) for transient errors.
- **`max_validation_retries=1`** to allow one structured output retry with feedback on parse failure.

## Scope Boundaries

**In scope:**
- CLI tool with `--dir`, `--file`, `--flaw`, `--output-dir`, `--max-depth`, `--verbose`.
- Static registry of all ~48 pipeline stages with dependencies and source code paths.
- Recursive depth-first upstream tracing with three LLM prompt types.
- JSON + markdown output sorted by trace depth.
- Source code analysis only at origin stages (lazy evaluation).
- Full file contents sent to LLM (no chunking or summarization).

**Out of scope (future work):**
- Library/module API (CLI first, refactor later).
- Integration as a Luigi pipeline stage.
- Approach B (full reverse-topological sweep).
- Approach C (scout-then-trace optimization).
- Automatic registry generation from Luigi task introspection.
- UI/web integration.
