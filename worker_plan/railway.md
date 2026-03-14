# Railway Configuration for `worker_plan`

```
OPENROUTER_API_KEY="${{shared.OPENROUTER_API_KEY}}"
PLANEXE_CONFIG_PATH="/app"
PLANEXE_HOST_RUN_DIR="/app/run"
PLANEXE_RUN_DIR="/app/run"
PLANEXE_WORKER_RELAY_PROCESS_OUTPUT="true"
PLANEXE_POSTGRES_PASSWORD="${{shared.PLANEXE_POSTGRES_PASSWORD}}"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES="${{shared.PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES}}"
```

## Volume - None

The `worker_plan` gets initialized via env vars. It does write to disk inside the `run` dir.

## Settings - Private Networking

Create `workerplan.railway.internal` as IPv4 and IPv6.
