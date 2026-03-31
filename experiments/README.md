# Experiments

Standalone proof-of-concept scripts used during early development of PlanExe.
These are **not production code** and are not imported by any service.

## Status

Archived. These scripts were originally in `worker_plan/worker_plan_internal/proof_of_concepts/` and moved here to keep the production tree clean.

## Running

Scripts assume `worker_plan` is installed (e.g. `pip install -e ./worker_plan`). Run from the repo root:

```bash
python experiments/run_chat.py
```

Some scripts require API keys (e.g. `OPENROUTER_API_KEY`). Check the docstring at the top of each file for details.
