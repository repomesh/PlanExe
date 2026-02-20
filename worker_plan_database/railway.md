# Railway Configuration for `worker_plan_database`

Create minimum 1 instance. With more traffic, create N instances.

Below is an example of what a `worker_plan_database_1` instance may be configured as:

```
OPENROUTER_API_KEY="${{shared.OPENROUTER_API_KEY}}"
PLANEXE_WORKER_ID="1"
PLANEXE_IFRAME_GENERATOR_CONFIRMATION_PRODUCTION_URL="${{shared.PLANEXE_IFRAME_GENERATOR_CONFIRMATION_PRODUCTION_URL}}"
PLANEXE_IFRAME_GENERATOR_CONFIRMATION_DEVELOPMENT_URL="${{shared.PLANEXE_IFRAME_GENERATOR_CONFIRMATION_DEVELOPMENT_URL}}"
PLANEXE_POSTGRES_PASSWORD="${{shared.PLANEXE_POSTGRES_PASSWORD}}"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES="${{shared.PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES}}"
```

- Set `OPENROUTER_API_KEY` (and any other model keys referenced by `llm_config/<profile>.json` files) so the pipeline can call the LLM provider.
- `PLANEXE_WORKER_ID` a unique id that identifies what worker instance it is.
- `PLANEXE_IFRAME_GENERATOR_CONFIRMATION_*` are required; the worker exits early if they are missing.

## Volume - None

The `worker_plan_database_1` gets initialized via env vars. It does write to disk inside the `run` dir.
