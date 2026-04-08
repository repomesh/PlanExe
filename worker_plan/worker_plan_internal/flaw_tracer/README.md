# Root Cause Analysis (RCA) for PlanExe

> **Naming note:** This module is currently named `flaw_tracer`. Candidate names under consideration:
> - `rca` — direct, matches the goal (root cause analysis)
> - `trace` — short, verb-oriented
> - `provenance` — emphasizes the artifact lineage aspect
> - `upstream_tracer` — describes the direction of analysis
>
> The module may be renamed in a future PR.

Given a problem observed in a pipeline output, this tool traces upstream through the DAG of intermediary artifacts to find where the problem originated and classify its root cause.

## How it works

PlanExe runs a DAG of ~70 nodes. Each node reads upstream artifacts, calls an LLM, and writes output artifacts (prefixed `001-` through `030-`). Problems introduced early propagate downstream into later nodes and the final report.

The DAG structure is extracted automatically from the Luigi task graph by `extract_dag.py` — no hand-maintained registry needed. The registry builds at import time via Luigi task introspection.

The tool performs a recursive depth-first search:

1. **Phase 1 — Identify problems.** Reads the starting artifact and locates the specific problem you described, plus any closely related problems in the same family.
2. **Phase 2 — Trace upstream.** For each problem, walks upstream through the DAG one hop at a time, asking the LLM whether the problem was *caused by* content in each input artifact (requires causal link, not just topical overlap). Continues until it finds a node where the problem exists in the output but not in any inputs.
3. **Phase 3 — Analyze source code and classify.** At the origin node, reads the Python source code and classifies the root cause:
   - **Prompt fixable** — the prompt has a gap that can be fixed by editing it
   - **Domain complexity** — the topic is inherently uncertain or contentious, no prompt change resolves it
   - **Missing input** — the user's plan prompt didn't provide enough detail

Output is a JSON file (`flaw_trace.json`), a markdown report (`flaw_trace.md`), and a live event log (`events.jsonl`), sorted by trace depth so the deepest root cause appears first.

## DAG integration

The pipeline DAG is defined in `extract_dag.py` which introspects the actual Luigi task graph at import time. Each node in the DAG provides:
- **artifacts** — output files the node produces
- **inputs** — which upstream node and specific artifact each node reads
- **source_files** — the workflow node file and business logic files

This means the RCA tool always stays in sync with the pipeline — no manual registry updates needed when nodes are added, removed, or renamed.

## Prerequisites

- Python 3.11 (`/opt/homebrew/bin/python3.11` on macOS with Homebrew)
- An LLM configured via `PLANEXE_MODEL_PROFILE` environment variable (defaults to `baseline`)
- API key for your LLM provider (e.g., `OPENROUTER_API_KEY`)

## Usage

All commands are run from the `worker_plan/` directory:

```bash
cd worker_plan
```

Basic usage:

```bash
/opt/homebrew/bin/python3.11 -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output \
    --file 030-report.html \
    --flaw "Description of the problem you observed" \
    --verbose
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--dir` | Yes | Path to the output directory containing intermediary artifacts |
| `--file` | Yes | Starting artifact to analyze (relative to `--dir`) |
| `--flaw` | Yes | Text description of the observed problem(s) |
| `--output-dir` | No | Where to write reports (defaults to `--dir`) |
| `--max-depth` | No | Maximum upstream hops per problem (default: 15) |
| `--verbose` | No | Print each LLM call to stderr as the trace runs |

### Starting files

You can start from any intermediary artifact. Common starting points:

| File | What it is |
|------|------------|
| `030-report.html` | The final HTML report (largest, most problems to find) |
| `029-2-self_audit.md` | Self-audit (already identifies issues — good for tracing them back) |
| `025-2-executive_summary.md` | Executive summary |
| `024-2-review_plan.md` | Plan review |
| `028-2-premortem.md` | Premortem analysis |

### Examples

Trace a problem from the self-audit:

```bash
/opt/homebrew/bin/python3.11 -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output/20250101_india_census \
    --file 029-2-self_audit.md \
    --flaw "No Real-World Proof. The plan combines a digital census with caste enumeration at an unprecedented scale, lacking independent evidence of success." \
    --output-dir /tmp/rca-analysis \
    --verbose
```

Trace a zoning/permits problem:

```bash
/opt/homebrew/bin/python3.11 -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output/20251016_minecraft_escape \
    --file 029-2-self_audit.md \
    --flaw "Infeasible Constraints Rated MEDIUM because the plan mentions zoning and permits but lacks specifics for the Shanghai location." \
    --output-dir /tmp/rca-analysis2 \
    --verbose
```

### Monitoring progress

While the tracer runs, watch the live event log in another terminal:

```bash
tail -f /tmp/rca-analysis/events.jsonl
```

### Output

Each run produces three files in `--output-dir` (or `--dir` if not specified):

- `flaw_trace.json` — machine-readable trace with full details
- `flaw_trace.md` — human-readable report with trace tables
- `events.jsonl` — live event log for monitoring progress

Problems are sorted by trace depth (deepest root cause first). Each problem's origin includes a **category** (`prompt_fixable`, `domain_complexity`, or `missing_input`) so you know whether the fix is a prompt edit, a domain limitation to accept, or a need for more detail in the plan input.

A typical run finds 2-3 focused problems and makes 15-30 LLM calls.

## RCA investigation strategy

The tool implements the investigation strategy described in `docs/proposals/133-dag-and-rca.md`:

1. Start from the final artifact (e.g., `030-report.html`)
2. Inspect direct input artifacts to the producing node
3. Search those artifacts for the false claim or problem
4. When found upstream, recurse into that node's inputs
5. Continue until reaching the earliest artifact containing the problem
6. Inspect the producing node's source files
7. Classify the failure mode

## Tips

- **Start from `029-2-self_audit.md`.** This file already contains identified issues, so you're tracing *known* problems upstream rather than asking the LLM to find problems from scratch.
- **Trust the trace chains more than the suggestions.** The upstream path (which nodes the problem passed through) is mechanically grounded in the DAG. The suggestions are LLM opinions — useful starting points, not patches.
- **Check the category before acting.** If the origin is `domain_complexity`, don't spend time tweaking the prompt. If it's `prompt_fixable`, the suggestion is likely actionable.
- **Results are non-deterministic.** This is LLM judging LLM output. Two runs on the same input may produce slightly different traces. If a finding matters, run it twice.

## Limitations

- **LLM subjectivity.** Every hop in the trace is a judgment call by the LLM ("did this upstream artifact cause the downstream problem?"). The causal-link requirement helps, but it's still one LLM's opinion.
- **First-match-wins.** When a problem has precursors in multiple parallel upstream branches, only the first branch found is followed. Real problems often have multiple contributing causes.
- **Text-only.** The tracer can only catch problems that leave textual evidence in intermediary artifacts. Timing issues, model-specific quirks, or structural DAG problems are invisible to it.
- **Artifact-level, not claim-level.** The tool can identify which artifact and node likely introduced a problem, but cannot yet prove which exact sentence transformation introduced a specific false claim (see `docs/proposals/133-dag-and-rca.md` for the gap analysis).
- **Diagnostic, not prescriptive.** It tells you *where* and *why*, but someone still has to decide what to do about it.

## Running tests

```bash
cd worker_plan
/opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/flaw_tracer/tests/ -v
```
