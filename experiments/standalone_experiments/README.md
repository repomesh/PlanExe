# Standalone Experiments - that can fit inside a single file

Standalone proof-of-concept scripts used during development of PlanExe.
These are **not production code** and are not imported by any service.

## Running

Scripts assume `worker_plan` is installed (e.g. `pip install -e ./worker_plan`). Run from the repo root:

```bash
python experiments/standalone_experiments/run_chat.py
```

Some scripts require API keys (e.g. `OPENROUTER_API_KEY`). Check the docstring at the top of each file for details.
