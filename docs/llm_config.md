---
title: LLM config profiles
---

# LLM config profiles

PlanExe supports **4 model profiles**:

- `baseline`
- `premium`
- `frontier`
- `custom`

Each profile maps to a separate config file:

- `baseline` → `llm_config.baseline.json`
- `premium` → `llm_config.premium.json`
- `frontier` → `llm_config.frontier.json`
- `custom` → `llm_config.custom.json` (or `PLANEXE_LLM_CONFIG_CUSTOM_FILENAME`)

If the selected profile file is missing or invalid, PlanExe safely falls back to `llm_config.baseline.json`.

---

## How profile selection works

### Runtime env var

Set:

- `PLANEXE_MODEL_PROFILE=baseline|premium|frontier|custom`

This is passed end-to-end in worker execution paths (frontend/API/task parameters → worker pipeline).

### Request/task parameter

Task producers (web frontend, MCP) can include:

- `model_profile`

Invalid values are normalized to `baseline`.

---

## Strict filename validation

Config filenames are strictly validated:

- must be a **filename only** (no `/`, `\\`, absolute path)
- must match: `llm_config*.json`

This prevents path traversal and unsafe file selection.

Legacy override `PLANEXE_LLM_CONFIG_NAME` is still supported for backward compatibility, but profile-based selection is preferred.

---

## Provider-priority ordering per profile

Within each profile config file, priority is defined per model entry:

- lower `priority` value = tried first
- higher `priority` value = fallback order

`auto` mode uses this profile-specific priority ordering.

---

## File format (same for all profile files)

```json
{
  "model-id": {
    "comment": "Human description",
    "priority": 1,
    "luigi_workers": 4,
    "class": "OpenRouter",
    "arguments": {
      "model": "google/gemini-2.0-flash-001",
      "api_key": "${OPENROUTER_API_KEY}",
      "temperature": 0.1,
      "timeout": 60.0,
      "max_tokens": 8192,
      "max_retries": 5
    }
  }
}
```

---

## Backward compatibility

When no profile is provided, PlanExe defaults to:

- `baseline`
- `llm_config.baseline.json`

So existing deployments continue to work without changes.
