# Proposal 75 — Post-rename cleanup issues (`task_` -> `plan_`, `TaskItem` -> `PlanItem`)

## Status

Implemented

## Context

Proposal 73 renamed public MCP tools from `task_*` to `plan_*`.
Proposal 74 renamed the internal model class from `TaskItem` to `PlanItem`.

This document tracks remaining cleanup issues found after those renames.

Scope note:
- Included: active code paths, tests, AGENTS docs, and user-facing docs.
- Excluded: historical proposal files in `docs/proposals/` that intentionally preserve old names for historical accuracy.

---

## Findings

### 1) User-facing MCP doc still references old tool name

`docs/mcp/lm_studio.md` still tells users to invoke `task_status` instead of `plan_status`.

- File: `docs/mcp/lm_studio.md`
- Line: 47
- Impact: user confusion; wrong tool name in current interface docs.
- Fix: replace `task_status` with `plan_status`.

### 2) AGENTS / ops docs still use `TaskItem` / `TaskState` wording

These docs still mention pre-rename class names.

- File: `AGENTS.md`
- Line: 31
- Current text: `TaskItem.run_track_activity_jsonl`

- File: `docker-compose.md`
- Line: 89
- Current text: worker polls `TaskItem` rows

- Impact: contributor-facing documentation drift.
- Fix:
  - `TaskItem` -> `PlanItem`
  - `TaskState.pending` example -> `PlanState.pending` (or plain public state strings).

### 3) Compatibility aliases still expose legacy `task_*` internals

Legacy alias support still exists in MCP server internals.

- File: `mcp_cloud/app.py`
- Lines: 777, 791, 1820-1825

- Impact: not incorrect if backward compatibility is intentional, but rename is not fully clean.
- Decision needed:
  - Keep aliases for compatibility window, or
  - Remove aliases for strict post-rename surface.

### 4) MCP cloud tests still use `task_*` naming conventions

Test file names/classes/helpers still use old naming (while calling new handlers).

- Files:
  - `mcp_cloud/tests/test_task_create_tool.py`
  - `mcp_cloud/tests/test_task_status_tool.py`
  - `mcp_cloud/tests/test_task_retry_tool.py`
  - `mcp_cloud/tests/test_task_file_info_tool.py`

Also one assertion payload string still references old model profile guidance text:

- File: `mcp_cloud/tests/test_model_profiles_tool.py`
- Lines: 33, 48
- Current text: `"Use one of these profile values in task_create.model_profile."`

- Impact: test naming/docs drift; no runtime break.
- Fix:
  - Rename tests and symbols to `plan_*` naming where desired.
  - Update expected string to `plan_create.model_profile`.

---

## Verified non-issues

`PlanItem` class and DB table mapping are correct and intentionally preserved:

- File: `database_api/model_planitem.py`
- Line: 42
- `__tablename__ = "task_item"`

This is expected for backward-compatible DB schema usage.

---

## Suggested cleanup order

1. Fix user-facing docs/tool descriptions (Finding 1).
2. Fix AGENTS/docs wording (Finding 2).
3. Decide alias policy, then keep/remove legacy aliases (Finding 3).
4. Normalize test naming and assertion strings (Finding 4).

---

## Re-scan command

Use this after fixes (excluding historical proposals):

```bash
rg -n "task_create|task_status|task_stop|task_retry|task_list|task_file_info|TaskItem|TaskState|model_taskitem|test_taskitem" PlanExe --glob '!PlanExe/docs/proposals/**'
```
