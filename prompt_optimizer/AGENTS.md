# Agent instructions for prompt_optimizer

## What this does

Runs the `IdentifyPotentialLevers` pipeline step with a candidate system prompt against baseline training data. Produces lever JSON outputs per plan and progress-tracking files.

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
  meta.json          # written at start: step name, system_prompt SHA256, models
  outputs.jsonl      # one row per completed plan: {name, status, lever_count, duration_seconds, error}
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
