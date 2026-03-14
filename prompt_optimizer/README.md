# Prompt Optimizer

Optimizes system prompts for pipeline steps in `run_plan_pipeline.py`. Re-executes a pipeline step with a candidate system prompt against baseline training data and captures the output, enabling comparison of candidate prompts against baseline outputs.

Currently supports the `IdentifyPotentialLevers` step. Each pipeline step requires a custom adapter (input assembly, execute call, output filenames), but the runner infrastructure (progress tracking, CLI, output structure) is shared.

## Usage

```bash
# Auto-increment into prompt-lab history/
python -m prompt_optimizer.runner \
    --system-prompt-file candidate.txt \
    --baseline-dir /path/to/baseline/train \
    --prompt-lab-dir /path/to/PlanExe-prompt-lab \
    --model ollama-llama3.1

# Or manual output directory
python -m prompt_optimizer.runner \
    --system-prompt-file candidate.txt \
    --baseline-dir /path/to/baseline/train \
    --output-dir /path/to/my_run/outputs \
    --model ollama-llama3.1
```

### Options

| Flag | Required | Description |
|------|----------|-------------|
| `--system-prompt-file` | Yes | Path to a text file containing the candidate system prompt |
| `--baseline-dir` | No | Directory containing plan subdirectories (process all) |
| `--plan-dir` | No | Single plan directory to process (overrides `--baseline-dir`) |
| `--prompt-lab-dir` | No | Path to PlanExe-prompt-lab repo (auto-creates history run dir) |
| `--output-dir` | No | Manual output directory (alternative to `--prompt-lab-dir`) |
| `--model` | Yes | LLM model name. First is primary; additional are fallbacks |

Either `--baseline-dir` or `--plan-dir` must be provided.
Either `--prompt-lab-dir` or `--output-dir` must be provided.

## Output Structure

With `--prompt-lab-dir`, outputs go to `history/{counter // 100}/{counter % 100:02d}_{step}/`. The counter auto-increments by scanning existing history directories.

```
<run-dir>/
  meta.json          # written at start: step name, system_prompt SHA256, model, workers, system
  outputs.jsonl      # one row per completed plan: {name, status, duration_seconds, error}
  events.jsonl       # timestamped events: run_single_plan_start, _complete, _error
  outputs/
    <plan_name>/
      002-9-potential_levers_raw.json
      002-10-potential_levers.json
      activity_overview.json
      usage_metrics.jsonl
```

## Quick Start

Extract the current default system prompt to a file, then run against a single plan:

```bash
python -c "
import sys; sys.path.insert(0, 'worker_plan')
from worker_plan_internal.lever.identify_potential_levers import IDENTIFY_POTENTIAL_LEVERS_SYSTEM_PROMPT
print(IDENTIFY_POTENTIAL_LEVERS_SYSTEM_PROMPT.strip())
" > baseline_prompt.txt

python -m prompt_optimizer.runner \
    --system-prompt-file baseline_prompt.txt \
    --plan-dir /path/to/baseline/train/20250321_silo \
    --prompt-lab-dir /path/to/PlanExe-prompt-lab \
    --model ollama-llama3.1
```

## Parallelism

The runner automatically parallelizes based on the `luigi_workers` value in `llm_config/*.json` for the model being used. Cloud models typically use 4 workers; local models use 1. The worker count is recorded in `meta.json`.

Each plan runs in its own thread with an independent `LLMExecutor`. Usage metrics use thread-local storage to avoid cross-thread interference.

## Architecture

The runner is designed to extend to other pipeline steps. Each step needs four things:

1. **Input files** — which files to read and how to assemble the user prompt
2. **Execute call** — which class/method to invoke
3. **Output filenames** — which files to save
4. **Step name** — identifier for meta.json
