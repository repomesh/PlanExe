# Prompt Optimizer

Optimizes system prompts for pipeline steps in `run_plan_pipeline.py`. Re-executes a pipeline step with a candidate system prompt against baseline training data and captures the output, enabling comparison of candidate prompts against baseline outputs.

Currently supports the `IdentifyPotentialLevers` step. Each pipeline step requires a custom adapter (input assembly, execute call, output filenames), but the runner infrastructure (progress tracking, CLI, output structure) is shared.

## Usage

```bash
python -m prompt_optimizer.runner \
    --system-prompt-file candidate.txt \
    --baseline-dir /path/to/baseline/train \
    --output-dir /path/to/runs/my_run/outputs \
    --model ollama-llama3.1
```

### Options

| Flag | Required | Description |
|------|----------|-------------|
| `--system-prompt-file` | Yes | Path to a text file containing the candidate system prompt |
| `--baseline-dir` | No | Directory containing plan subdirectories (process all) |
| `--plan-dir` | No | Single plan directory to process (overrides `--baseline-dir`) |
| `--output-dir` | Yes | Directory where outputs will be written |
| `--model` | Yes | LLM model name. First is primary; additional are fallbacks |

Either `--baseline-dir` or `--plan-dir` must be provided.

## Output Structure

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
    --output-dir /tmp/prompt_opt_test/outputs \
    --model ollama-llama3.1
```

## Architecture

The runner is designed to extend to other pipeline steps. Each step needs four things:

1. **Input files** — which files to read and how to assemble the user prompt
2. **Execute call** — which class/method to invoke
3. **Output filenames** — which files to save
4. **Step name** — identifier for meta.json
