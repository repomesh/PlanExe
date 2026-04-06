# Flaw Tracer

Root-cause analysis tool for PlanExe reports. Given a flaw observed in a pipeline output, it traces upstream through the DAG of intermediary files to find where the flaw originated.

## How it works

PlanExe runs a DAG of ~70 tasks. Each task reads upstream files, calls an LLM, and writes output files (prefixed `001-` through `030-`). Flaws introduced early propagate downstream into later stages and the final report.

The flaw tracer performs a recursive depth-first search:

1. **Phase 1 — Identify flaws.** Reads the starting file and locates the specific flaw you described, plus any closely related flaws in the same problem family.
2. **Phase 2 — Trace upstream.** For each flaw, walks upstream through the DAG one hop at a time, asking the LLM whether the flaw was *caused by* content in each input file (requires causal link, not just topical overlap). Continues until it finds a stage where the flaw exists in the output but not in any inputs.
3. **Phase 3 — Analyze source code and classify.** At the origin stage, reads the Python source code and classifies the root cause:
   - **Prompt fixable** — the prompt has a gap that can be fixed by editing it
   - **Domain complexity** — the topic is inherently uncertain or contentious, no prompt change resolves it
   - **Missing input** — the user's plan prompt didn't provide enough detail

Output is a JSON file (`flaw_trace.json`), a markdown report (`flaw_trace.md`), and a live event log (`events.jsonl`), sorted by trace depth so the deepest root cause appears first.

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
    --flaw "Description of the flaw you observed" \
    --verbose
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--dir` | Yes | Path to the output directory containing intermediary files |
| `--file` | Yes | Starting file to analyze (relative to `--dir`) |
| `--flaw` | Yes | Text description of the observed flaw(s) |
| `--output-dir` | No | Where to write reports (defaults to `--dir`) |
| `--max-depth` | No | Maximum upstream hops per flaw (default: 15) |
| `--verbose` | No | Print each LLM call to stderr as the trace runs |

### Starting files

You can start from any intermediary file. Common starting points:

| File | What it is |
|------|------------|
| `030-report.html` | The final HTML report (largest, most flaws to find) |
| `029-2-self_audit.md` | Self-audit (already identifies issues — good for tracing them back) |
| `025-2-executive_summary.md` | Executive summary |
| `024-2-review_plan.md` | Plan review |
| `028-2-premortem.md` | Premortem analysis |

### Examples

Trace a flaw from the self-audit:

```bash
/opt/homebrew/bin/python3.11 -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output/20250101_india_census \
    --file 029-2-self_audit.md \
    --flaw "No Real-World Proof. The plan combines a digital census with caste enumeration at an unprecedented scale, lacking independent evidence of success." \
    --output-dir /tmp/flaw-analysis \
    --verbose
```

Trace a zoning/permits flaw:

```bash
/opt/homebrew/bin/python3.11 -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output/20251016_minecraft_escape \
    --file 029-2-self_audit.md \
    --flaw "Infeasible Constraints Rated MEDIUM because the plan mentions zoning and permits but lacks specifics for the Shanghai location." \
    --output-dir /tmp/flaw-analysis2 \
    --verbose
```

### Monitoring progress

While the tracer runs, watch the live event log in another terminal:

```bash
tail -f /tmp/flaw-analysis/events.jsonl
```

### Output

Each run produces three files in `--output-dir` (or `--dir` if not specified):

- `flaw_trace.json` — machine-readable trace with full details
- `flaw_trace.md` — human-readable report with trace tables
- `events.jsonl` — live event log for monitoring progress

Flaws are sorted by trace depth (deepest root cause first). Each flaw's origin includes a **category** (`prompt_fixable`, `domain_complexity`, or `missing_input`) so you know whether the fix is a prompt edit, a domain limitation to accept, or a need for more detail in the plan input.

A typical run finds 2-3 focused flaws and makes 15-30 LLM calls.

## Running tests

```bash
cd worker_plan
/opt/homebrew/bin/python3.11 -m pytest worker_plan_internal/flaw_tracer/tests/ -v
```
