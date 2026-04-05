# Flaw Tracer

Root-cause analysis tool for PlanExe reports. Given a flaw observed in a pipeline output, it traces upstream through the DAG of intermediary files to find where the flaw originated.

## How it works

PlanExe runs a DAG of ~70 tasks. Each task reads upstream files, calls an LLM, and writes output files (prefixed `001-` through `030-`). Flaws introduced early propagate downstream into later stages and the final report.

The flaw tracer performs a recursive depth-first search:

1. **Phase 1 — Identify flaws.** Reads the starting file and asks the LLM to identify discrete flaws based on your description.
2. **Phase 2 — Trace upstream.** For each flaw, walks upstream through the DAG one hop at a time, asking the LLM whether the flaw or a precursor exists in each input file. Continues until it finds a stage where the flaw exists in the output but not in any inputs.
3. **Phase 3 — Analyze source code.** At the origin stage, reads the Python source code that generated the output and asks the LLM what in the prompt or logic likely caused the flaw.

Output is a JSON file (`flaw_trace.json`) and a markdown report (`flaw_trace.md`), sorted by trace depth so the deepest root cause appears first.

## Usage

From the `worker_plan/` directory:

```bash
python -m worker_plan_internal.flaw_tracer \
    --dir /path/to/output \
    --file 030-report.html \
    --flaw "The budget is CZK 500,000 but this number appears unvalidated. No market sizing or unit economics are provided." \
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

### Example

```bash
python -m worker_plan_internal.flaw_tracer \
    --dir /Users/you/planexe-output/20250101_india_census \
    --file 025-2-executive_summary.md \
    --flaw "The budget claims CZK 500,000 but also states costs may exceed that by 20%. The budget is an unvalidated placeholder, not a reliable plan." \
    --output-dir /tmp/flaw-analysis \
    --verbose
```

This produces:
- `/tmp/flaw-analysis/flaw_trace.json` — machine-readable trace
- `/tmp/flaw-analysis/flaw_trace.md` — human-readable report

## Running tests

```bash
cd worker_plan
python -m pytest worker_plan_internal/flaw_tracer/tests/ -v
```
