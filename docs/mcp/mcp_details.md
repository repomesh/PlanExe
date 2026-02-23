# PlanExe MCP Details

MCP is work-in-progress, and I (Simon Strandgaard, the developer) may change it as I see fit.
If there is a particular tool you want. Write to me on the [PlanExe Discord](https://planexe.org/discord), and I will see what I can do.

This document lists the MCP tools exposed by PlanExe and example prompts for agents.

## Overview

- The primary MCP server runs in the cloud (see `mcp_cloud`).
- The local MCP proxy (`mcp_local`) forwards calls to the server and adds a local download helper.
- Tool responses return JSON in both `content.text` and `structuredContent`.
- Workflow note: drafting and user approval of the prompt is a non-tool step between setup tools and `task_create`.

## Tool Catalog, `mcp_cloud`

### prompt_examples

Returns around five example prompts that show what good prompts look like. Each sample is typically 300–800 words: detailed context, requirements, and success criteria. Usually the AI does the heavy lifting: the user has a vague idea, the agent calls `prompt_examples`, then expands that idea into a high-quality prompt (300–800 words). The prompt is shown to the user, who can ask for further changes or confirm it’s good to go. When the user confirms, the agent then calls `task_create`. Shorter or vaguer prompts produce lower-quality plans.

Example prompt:
```
Get example prompts for creating a plan.
```

Example call:
```json
{}
```

Response includes `samples` (array of prompt strings, each 300–800 words) and `message`.

### model_profiles

Returns profile guidance and model availability for `task_create.model_profile`.
This helps agents pick a profile without knowing internal `llm_config/*.json` details.

Example prompt:
```
List available model profiles and models.
```

Example call:
```json
{}
```

Response includes:
- `default_profile`
- `whitelist_active`
- `whitelisted_classes`
- `profiles[]` with:
  - `profile`
  - `title`
  - `summary`
  - `config_filename`
  - `available`
  - `model_count`
  - `filtered_out_count`
  - `models[]` (`key`, `provider_class`, `model`, `priority`)

### task_create

Create a new plan task.

Example prompt:
> Create a plan for: Weekly meetup for humans where participants are randomly paired every 5 minutes...

Example call:
```json
{"prompt": "Weekly meetup for humans where participants are randomly paired every 5 minutes..."}
```

Optional visible argument:
```text
model_profile: "baseline" | "premium" | "frontier" | "custom"
```

Developer-only hidden metadata (not part of visible tool schema shown to agents):
```text
speed_vs_detail: "ping" | "fast" | "all"
```

Example with visible `model_profile`:
```json
{"prompt": "Weekly meetup for humans where participants are randomly paired every 5 minutes...", "model_profile": "premium"}
```

Example with hidden metadata override. The `ping` only checks if the LLMs are connected and doesn't trigger a full plan to be created:
```json
{
  "prompt": "Weekly meetup for humans where participants are randomly paired every 5 minutes...",
  "metadata": {
    "task_create": {
      "speed_vs_detail": "ping"
    }
  }
}
```

Example with hidden metadata override. The `fast` triggers a plan to be created, where the entire Luigi pipeline gets exercised, while skipping as much detail as possible:
```json
{
  "prompt": "Weekly meetup for humans where participants are randomly paired every 5 minutes...",
  "metadata": {
    "task_create": {
      "speed_vs_detail": "fast"
    }
  }
}
```

Example with hidden metadata override. The `all` is the default setting. Creates a plan with **ALL** details:
```json
{
  "prompt": "Weekly meetup for humans where participants are randomly paired every 5 minutes...",
  "metadata": {
    "task_create": {
      "speed_vs_detail": "all"
    }
  }
}
```

Counterexamples (do NOT use PlanExe for these):

- "Give me a 5-point checklist for X."
- "Summarize this paragraph in 6 bullets."
- "Rewrite this email."
- "Identify the risks of this project."
- "Make a SWOT for this document."

What to do instead:

- For one-shot outputs, use a normal LLM response directly.
- For PlanExe, send a substantial multi-phase project prompt with scope, constraints, timeline, budget, stakeholders, and success criteria.
- PlanExe always runs a fixed end-to-end pipeline; it does not support selecting only internal pipeline subsets.

### task_status

Fetch status/progress and recent files for a task.

Example prompt:
```
Get status for task 2d57a448-1b09-45aa-ad37-e69891ff6ec7.
```

Example call:
```json
{"task_id": "2d57a448-1b09-45aa-ad37-e69891ff6ec7"}
```

State contract:

- `pending`: queued and waiting for a worker, keep polling.
- `processing`: picked up by a worker, keep polling.
- `completed`: terminal success, proceed to download.
- `failed`: terminal error.

### task_stop

Request an active task to stop.

Example prompt:
```
Stop task 2d57a448-1b09-45aa-ad37-e69891ff6ec7.
```

Example call:
```json
{"task_id": "2d57a448-1b09-45aa-ad37-e69891ff6ec7"}
```

### task_file_info

Return download metadata for report or zip artifacts.

Example prompt:
```
Get report info for task 2d57a448-1b09-45aa-ad37-e69891ff6ec7.
```

Example call:
```json
{"task_id": "2d57a448-1b09-45aa-ad37-e69891ff6ec7", "artifact": "report"}
```

Available artifacts:
```
"report" | "zip"
```

Typical successful response:
```json
{
  "content_type": "application/zip",
  "sha256": "f8ad556b635b14e375222150664e85b426bf7f9209ede2f37f47a8975e286323",
  "download_size": 17262032,
  "download_url": "https://mcp.planexe.org/download/<task_id>/run.zip"
}
```

### Download with `curl`

When `task_file_info` returns a `download_url`, you can download directly with the same `X-API-Key` used for MCP authentication.

Download zip:
```bash
curl -H "X-API-Key: pex_0123456789abcdef" -O "https://mcp.planexe.org/download/2d57a448-1b09-45aa-ad37-e69891ff6ec7/run.zip"
```

Download report:
```bash
curl -H "X-API-Key: pex_0123456789abcdef" -O "https://mcp.planexe.org/download/2d57a448-1b09-45aa-ad37-e69891ff6ec7/030-report.html"
```

## Tool Catalog, `mcp_local`

The local proxy exposes the same tools as the server, and adds:

### task_download

Download report or zip to a local path.

Example prompt:
```
Download the report for task 2d57a448-1b09-45aa-ad37-e69891ff6ec7.
```

Example call:
```json
{"task_id": "2d57a448-1b09-45aa-ad37-e69891ff6ec7", "artifact": "report"}
```

`PLANEXE_PATH` behavior for `task_download`:
- Save directory is `PLANEXE_PATH`, or current working directory if unset.
- Non-existing directories are created automatically.
- If `PLANEXE_PATH` points to a file, download fails.
- Filename is prefixed with task id (for example `<task_id>-030-report.html`).
- Response includes `saved_path` with the exact local file location.

## Minimal error-handling contract

Error payload shape:
```json
{"error": {"code": "SOME_CODE", "message": "Human readable message", "details": {}}}
```

Common cloud/core error codes:
- `TASK_NOT_FOUND`
- `INVALID_USER_API_KEY`
- `USER_API_KEY_REQUIRED`
- `INSUFFICIENT_CREDITS`
- `INTERNAL_ERROR`
- `generation_failed`
- `content_unavailable`

Common local proxy error codes:
- `REMOTE_ERROR`
- `DOWNLOAD_FAILED`

Special case:
- `task_file_info` may return `{}` while the artifact is not ready yet (not an error).

## Typical Flow

### 1. Get example prompts

The user often starts with a vague idea. The AI calls `prompt_examples` first to see what good prompts look like (around five samples, 300–800 words each), then expands the user’s idea into a high-quality prompt and shows it to the user.

Prompt:
```
Get example prompts for creating a plan.
```

Tool call:
```json
{}
```

### 2. Inspect model profiles (optional but recommended)

Prompt:
```
Show model profile options and available models.
```

Tool call:
```json
{}
```

### 3. Draft and approve the prompt (non-tool step)

At this step, the agent writes a high-quality prompt draft, shows it to the user, and waits for approval.

### 4. Create a plan

The user reviews the prompt and either asks for further changes or confirms it’s good to go. When the user confirms, the agent calls `task_create` with that prompt.

Tool call:
```json
{"prompt": "..."}
```

### 5. Get status

Prompt:
```
Get status for my latest task.
```

Tool call:
```json
{"task_id": "<task_id_from_task_create>"}
```

### 6. Download the report

Prompt:
```
Download the report for my task.
```

Tool call:
```json
{"task_id": "<task_id_from_task_create>", "artifact": "report"}
```
