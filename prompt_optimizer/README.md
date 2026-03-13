# Prompt Optimizer

Re-executes the `IdentifyPotentialLevers` pipeline step with a candidate system prompt against baseline training data and captures the output. This lets you compare candidate prompts against baseline outputs.

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
| `--model` | Yes | LLM model name (can be repeated for fallback) |

Either `--baseline-dir` or `--plan-dir` must be provided.

## Output Structure

```
<output-dir>/
  <plan_name>/
    002-9-potential_levers_raw.json
    002-10-potential_levers.json
  <plan_name>/
    ...
meta.json    (written one level above output-dir)
```

`meta.json` captures: step name, system prompt SHA256, models used, per-plan status/lever count/duration, and total duration.

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
