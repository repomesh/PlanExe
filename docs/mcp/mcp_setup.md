---
title: MCP setup
---

# MCP setup

This is the shortest path to a working PlanExe MCP integration.

---

## 1. Understand the flow

1. Ask for prompt examples.
2. Inspect `model_profile` options and available models.
3. Expand the user idea into a high‑quality prompt (non-tool step) and get user approval.
4. Create the plan task.
5. Poll for status (about every 5 minutes).
6. Download the report (HTML or zip).

---

## 2. Minimal tool usage

1. `prompt_examples`
2. `model_profiles`
3. `task_create`
4. `task_status`
5. `task_download`

For `task_create`:

- Visible arguments: `prompt` (required), `model_profile` (optional).
- Hidden developer metadata: `speed_vs_detail` (`ping` | `fast` | `all`).
- Reference: [PlanExe MCP interface](planexe_mcp_interface.md#62-task_create)

---

## 3. Success criteria

- You can fetch example prompts.
- You can create a plan task.
- You can download the report artifact.
- Your client can parse `error.code` and `error.message` and handle `{}` from `task_file_info` as "not ready yet".
- If running parallel work, your client tracks multiple `task_id`s explicitly (server-side global cap is not enforced).

---

## Next steps

- Full tool details: [MCP details](mcp_details.md)
- Reference schema: [PlanExe MCP interface](planexe_mcp_interface.md)
- App setup guides: [Cursor](cursor.md), [Codex](codex.md), [LM Studio](lm_studio.md)
