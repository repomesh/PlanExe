# Railway Configuration for `worker_plan_database`

Use a single Railway service named `worker_plan_database`, then scale that service to N replicas.

## How to set up replicas

1. Create one service from `worker_plan_database`.
2. Set `Deploy/Scaling` region to `US West (California, USA`.
3. Set `Deploy/Scaling` count to the number of workers you want (for example `2` or `3`).
4. Configure the service variables below.

Railway runs one process per replica and injects:
- `RAILWAY_REPLICA_REGION`
- `RAILWAY_REPLICA_ID`

The worker derives:
- `PLANEXE_WORKER_ID="<region>_<replica-id>"`

Do not set `PLANEXE_WORKER_ID` manually unless you intentionally want to override replica-based IDs.

## Service variables example

```
OPENROUTER_API_KEY="${{shared.OPENROUTER_API_KEY}}"
PLANEXE_IFRAME_GENERATOR_CONFIRMATION_DEVELOPMENT_URL="${{shared.PLANEXE_IFRAME_GENERATOR_CONFIRMATION_DEVELOPMENT_URL}}"
PLANEXE_IFRAME_GENERATOR_CONFIRMATION_PRODUCTION_URL="${{shared.PLANEXE_IFRAME_GENERATOR_CONFIRMATION_PRODUCTION_URL}}"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES="${{shared.PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES}}"
PLANEXE_POSTGRES_PASSWORD="${{shared.PLANEXE_POSTGRES_PASSWORD}}"
PLANEXE_POSTGRES_HOST="${{shared.PLANEXE_POSTGRES_HOST}}"
```

- Set `OPENROUTER_API_KEY` (and any other model keys referenced by `llm_config/<profile>.json` files) so the pipeline can call the LLM provider.
- `PLANEXE_IFRAME_GENERATOR_CONFIRMATION_*` are required; the worker exits early if they are missing.

## Volume - None

The `worker_plan_database` service gets initialized via env vars. It does write to disk inside the `run` dir.
