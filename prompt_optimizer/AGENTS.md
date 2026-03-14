# Agent instructions for prompt_optimizer

## What this does

Optimizes system prompts for pipeline steps in `run_plan_pipeline.py`. Re-executes a step with a candidate system prompt against baseline training data and captures the output. Currently supports `IdentifyPotentialLevers`; will extend to other pipeline tasks.

## Prerequisites

- Python venv: `worker_plan/.venv/bin/python` (has llama_index and dependencies)
- Ollama running locally with a model (e.g. `ollama-llama3.1`)
- Baseline training data at: `/Users/neoneye/git/PlanExeGroup/PlanExe-prompt-lab/baseline/train/`

## Extract the default system prompt

```bash
worker_plan/.venv/bin/python -c "
import sys; sys.path.insert(0, 'worker_plan')
from worker_plan_internal.lever.identify_potential_levers import IDENTIFY_POTENTIAL_LEVERS_SYSTEM_PROMPT
print(IDENTIFY_POTENTIAL_LEVERS_SYSTEM_PROMPT.strip())
" > /tmp/baseline_prompt.txt
```

## Run against a single plan

```bash
worker_plan/.venv/bin/python -m prompt_optimizer.runner \
    --system-prompt-file /tmp/baseline_prompt.txt \
    --plan-dir /Users/neoneye/git/PlanExeGroup/PlanExe-prompt-lab/baseline/train/20250321_silo \
    --output-dir /tmp/prompt_opt_run/outputs \
    --model ollama-llama3.1
```

## Run against all baseline plans

```bash
worker_plan/.venv/bin/python -m prompt_optimizer.runner \
    --system-prompt-file /tmp/baseline_prompt.txt \
    --baseline-dir /Users/neoneye/git/PlanExeGroup/PlanExe-prompt-lab/baseline/train \
    --output-dir /tmp/prompt_opt_run/outputs \
    --model ollama-llama3.1
```

## Monitor progress during a run

```bash
tail -f /tmp/prompt_opt_run/events.jsonl
```

## Output structure

```
<run-dir>/
  meta.json          # written at start: step name, system_prompt SHA256, model, system
  outputs.jsonl      # one row per completed plan: {name, status, duration_seconds, error}
  events.jsonl       # timestamped events: run_single_plan_start, _complete, _error
  outputs/
    <plan_name>/
      002-9-potential_levers_raw.json
      002-10-potential_levers.json
```

## Timing

Each plan takes ~60-80 seconds on a local ollama-llama3.1. Five plans take ~5-7 minutes.

## Available baseline plans

- `20250321_silo`
- `20250329_gta_game`
- `20260308_sovereign_identity`
- `20260310_hong_kong_game`
- `20260311_parasomnia_research_unit`

## Architecture notes

The runner is designed to extend to other pipeline steps. Each step adapter needs:

1. **Input files** — which files to read and how to assemble the user prompt
2. **Execute call** — which class/method to invoke
3. **Output filenames** — which files to save
4. **Step name** — identifier for meta.json

The outer infrastructure (CLI, progress tracking via events.jsonl/outputs.jsonl, meta.json) is shared across all steps.
