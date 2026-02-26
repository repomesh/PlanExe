# Proposal 73 — Rename `task_` prefix in MCP tool names

## Status

Draft

---

## Problem

PlanExe's MCP tools use a `task_` prefix for the tools that manage a planning run:

| Current name     | Where exposed      |
|------------------|--------------------|
| `task_create`    | mcp_local, mcp_cloud |
| `task_status`    | mcp_local, mcp_cloud |
| `task_stop`      | mcp_local, mcp_cloud |
| `task_retry`     | mcp_local, mcp_cloud |
| `task_list`      | mcp_local, mcp_cloud |
| `task_file_info` | mcp_cloud only      |
| `task_download`  | mcp_local only      |

The MCP specification itself uses "task" as a protocol-level concept (the `tasks/run`, `tasks/get`, `tasks/cancel` RPC methods in the optional "Run as task" extension). When MCP clients read the PlanExe tool list, seeing `task_create` and `task_status` is ambiguous: it looks like PlanExe is implementing the MCP tasks protocol, which it explicitly does not (see `docs/mcp/planexe_mcp_interface.md` section 3.1).

Additionally, the word "task" is overloaded in this codebase: the internal Python model is `TaskItem` (a database row), the MCP protocol has its own "task" concept, and now MCP tool names carry `task_` too. This creates unnecessary cognitive load for contributors, users, and AI agents integrating PlanExe.

---

## Goals

1. Replace the `task_` prefix on public MCP tool names with a prefix that is unambiguous in the MCP context.
2. Update all code, tests, and docs in a single coordinated pass to keep the codebase consistent.
3. Maintain or improve clarity of what each tool does.

## Non-goals

- Renaming the internal `TaskItem` database model (internal concern; out of scope).
- Renaming the `task_id` response field (see the Decision Point section below).
- Changing tool functionality or signatures.

---

## Candidate Prefixes

### Option A — `plan_`  *(recommended)*

`plan_create`, `plan_status`, `plan_stop`, `plan_retry`, `plan_list`, `plan_file_info`, `plan_download`

**Pros:**
- Directly reflects what PlanExe produces: a *plan*.
- Strongly differentiates from the MCP protocol's "task" concept.
- Consistent with the product name (PlanExe) and existing tool docs phrasing ("the plan currently being created").
- `plan_create` as the entry point makes the purpose self-evident to any new user or agent.

**Cons:**
- "Plan" is somewhat overloaded too (plan = the output document; plan = the run that produces it). However, this is exactly how the rest of PlanExe uses the word, so it is consistent rather than confusing.

---

### Option B — `run_`

`run_create`, `run_status`, `run_stop`, `run_retry`, `run_list`, `run_file_info`, `run_download`

**Pros:**
- Describes the *execution* aspect accurately: each call creates a pipeline run.
- Short, low-noise prefix.
- No conflict with MCP protocol terminology.

**Cons:**
- `run_create` sounds like "create a run" rather than "create a plan", which underemphasizes the output.
- `run_list` could be confused with listing pipeline runs in unrelated tools (Luigi, CI/CD).

---

### Option C — `job_`

`job_create`, `job_status`, `job_stop`, `job_retry`, `job_list`, `job_file_info`, `job_download`

**Pros:**
- Well-established term in async/queue systems (background jobs).
- No conflict with MCP protocol terminology.
- Familiar to developers from job queues (Celery, Bull, Sidekiq).

**Cons:**
- "Job" does not convey that the result is a *plan*; it is generic.
- Less discoverable for end users who see the tool list for the first time.

---

## Decision Point: Should `task_id` also be renamed?

The `task_id` field is present in:
- Response payload of `task_create` (returns `task_id`)
- Input payloads of all other tools (`task_id` is the UUID parameter)
- Response payloads of `task_status`, `task_stop`, `task_retry`, `task_list`

Renaming `task_id` → e.g. `plan_id` would be a **breaking API change** for all callers. The recommendation is to **keep `task_id` as the field name** in this rename, because:

1. The UUID itself is what callers store and forward; the name is secondary.
2. Renaming the field would break every existing client with zero benefit.
3. The MCP tools protocol collision is a *tool name* problem, not a field name problem.

If a future proposal decides to rename `task_id`, it should be addressed in a separate, versioned migration (proposal 74+).

---

## Scope of Changes

### Source files

| File | What changes |
|------|-------------|
| `mcp_local/planexe_mcp_local.py` | Tool definition `name` strings, handler function names, `TOOL_HANDLERS` dict keys, docstrings, inline description strings referencing tool names |
| `mcp_cloud/app.py` | Tool definition `name` strings, handler function names, handler dispatch dict, docstrings, inline description strings |
| `mcp_cloud/tool_models.py` | Docstrings and `description` strings in `Field(...)` calls that mention old tool names |
| `mcp_cloud/http_server.py` | Any inline tool name references |

### Test files

| File | What changes |
|------|-------------|
| `mcp_cloud/tests/test_task_create_tool.py` | Rename file to `test_plan_create_tool.py`; update all tool name strings inside |
| `mcp_cloud/tests/test_task_status_tool.py` | Rename file to `test_plan_status_tool.py`; update all tool name strings inside |
| `mcp_cloud/tests/test_task_stop_tool.py` (if present) | Rename and update |
| `mcp_cloud/tests/test_task_retry_tool.py` | Rename file to `test_plan_retry_tool.py`; update |
| `mcp_cloud/tests/test_task_file_info_tool.py` | Rename file to `test_plan_file_info_tool.py`; update |
| `mcp_cloud/tests/test_task_list_tool.py` (if present) | Rename and update |
| `mcp_cloud/tests/test_tool_surface_consistency.py` | Update expected tool name list |

### Documentation files

| File | What changes |
|------|-------------|
| `docs/mcp/planexe_mcp_interface.md` | All section headings and all occurrences of `task_create`, `task_status`, `task_stop`, `task_retry`, `task_file_info`, `task_download`, `task_list` |
| `docs/mcp/mcp_details.md` | Same |
| `docs/mcp/mcp_welcome.md` | Same |
| `docs/mcp/mcp_setup.md` | Same |
| `docs/mcp/inspector.md` | Same |
| `docs/mcp/codex.md` | Same |
| `docs/mcp/lm_studio.md` | Same |
| `docs/mcp/windsurf.md` | Same |
| `skills/planexe-mcp/SKILL.md` | All tool name occurrences in code blocks and prose |
| `README.md` | All tool name occurrences |
| `public/llms.txt` | All tool name occurrences |
| `docs/proposals/70-mcp-interface-evaluation-and-roadmap.md` | Tool name references |
| Other proposal files referencing `task_create` etc. | Prose references |

---

## Step-by-Step Procedure

### Step 1 — Agree on the prefix

Decide on the prefix (recommendation: `plan_`) and record the decision in this document by updating Status from "Draft" to "Accepted — prefix: `plan_`".

### Step 2 — Create a feature branch

```bash
git checkout main
git pull
git checkout -b rename-mcp-task-prefix
```

### Step 3 — Define the rename mapping

Write down the full mapping before touching any file:

```
task_create    → plan_create
task_status    → plan_status
task_stop      → plan_stop
task_retry     → plan_retry
task_list      → plan_list
task_file_info → plan_file_info
task_download  → plan_download
```

### Step 4 — Update `mcp_cloud/tool_models.py`

Update only the `description` strings and docstrings that reference old tool names. Python class names (`TaskCreateInput`, `TaskStatusOutput`, etc.) are internal and can stay unchanged for now or be renamed in a follow-up.

Search pattern: `grep -rn "task_create\|task_status\|task_stop\|task_retry\|task_list\|task_file_info\|task_download" mcp_cloud/tool_models.py`

Replace all occurrences with the new names.

### Step 5 — Update `mcp_cloud/app.py`

1. Change every `name="task_create"` (and the other names) in `ToolDefinition(...)` blocks to the new prefix.
2. Rename handler functions: `handle_task_create` → `handle_plan_create`, etc.
3. Update the handler dispatch dictionary keys.
4. Update all description strings and docstrings that reference old tool names (e.g. "Returns task_id; use it for task_status, task_stop…" → "…use it for plan_status, plan_stop…").
5. Update `PLANEXE_SERVER_INSTRUCTIONS` string.

### Step 6 — Update `mcp_local/planexe_mcp_local.py`

Same pattern as Step 5:

1. Rename `ToolDefinition` name strings.
2. Rename handler functions: `handle_task_create` → `handle_plan_create`, etc.
3. Update `TOOL_HANDLERS` dict.
4. Update all description strings and the `PLANEXE_SERVER_INSTRUCTIONS` string.
5. Update internal `_call_remote_tool("task_create", …)` calls to pass the new names (since mcp_local forwards to mcp_cloud, both sides must be renamed together).

**Note:** mcp_local and mcp_cloud must be renamed in the same commit because mcp_local forwards tool calls to mcp_cloud by name. If they diverge, calls will fail with `INVALID_TOOL`.

### Step 7 — Update `mcp_cloud/http_server.py`

Search for any inline tool name string references and update them.

### Step 8 — Rename and update test files

For each test file named `test_task_*.py`:
1. Create a new file with the renamed path (`test_plan_*.py`).
2. Update all tool name string literals inside (e.g. `"task_create"` → `"plan_create"`).
3. Delete the old file.

Update `test_tool_surface_consistency.py` to expect the new tool names in the tool list.

### Step 9 — Update documentation

For each file in the documentation scope listed above:
- Search for `task_create`, `task_status`, `task_stop`, `task_retry`, `task_list`, `task_file_info`, `task_download`.
- Replace with the corresponding new name.
- Be careful **not** to rename `task_id` (the UUID field name) — only rename the tool names themselves.

A useful grep to find all documentation occurrences before editing:

```bash
grep -rn "task_create\|task_status\|task_stop\|task_retry\|task_list\|task_file_info\|task_download" \
  docs/ skills/ README.md public/llms.txt
```

### Step 10 — Run the test suite

```bash
python -m pytest mcp_cloud/tests/ -v
python -m pytest mcp_local/tests/ -v   # if tests exist
```

All tests must pass. Fix any failures before proceeding.

### Step 11 — Smoke-test locally with MCP Inspector

Start mcp_cloud locally and open the MCP Inspector:

```bash
# Start mcp_cloud
# Connect Inspector to the local endpoint
# Verify the tool list shows plan_create, plan_status, etc.
# Call plan_create with a short prompt and verify a task_id is returned
# Call plan_status with the returned task_id
```

### Step 12 — Open a pull request

Describe the rename in the PR summary. Include:
- The prefix chosen and why.
- A note that `task_id` (the field name) was intentionally kept unchanged.
- Confirmation that mcp_local and mcp_cloud were updated together.
- Test run results.

### Step 13 — Update deployment configuration (if needed)

If any external configuration files, environment variable values, or client-side configs reference old tool names by string, update those too.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| mcp_local and mcp_cloud renamed at different times → `INVALID_TOOL` errors | Steps 5 and 6 must be committed together in one atomic change. |
| External clients hardcoding `task_create` break | This is a breaking change. Announce in release notes. Consider a temporary alias period if external users exist. |
| Partial rename leaves docs inconsistent | Run the grep command from Step 9 after editing to verify zero remaining occurrences. |
| `task_id` accidentally renamed | Grep for `plan_id` after the rename to confirm it does not appear anywhere in tool schemas or payloads. |

---

## Acceptance Criteria

- [ ] All MCP tool names exposed by mcp_cloud and mcp_local use the new prefix.
- [ ] All prose and code in `docs/` and `skills/` uses the new names.
- [ ] `README.md` and `public/llms.txt` use the new names.
- [ ] The `task_id` field name is unchanged in all request/response schemas.
- [ ] All tests pass.
- [ ] MCP Inspector smoke test shows the new tool names.
