# Proposal 87: `plan_resume` MCP Tool — Luigi-Aware Pipeline Resume

**Author:** EgonBot  
**Date:** 2026-03-07  
**Status:** Proposal  
**Scope:** New MCP tool `plan_resume` enabling agents and users to resume an interrupted, stuck, or stopped PlanExe pipeline run without discarding completed Luigi task outputs. Grounded in code-level analysis of `worker_plan_database/app.py`, `mcp_cloud/db_queries.py`, `worker_plan/app.py`, and `worker_plan_internal/plan/run_plan_pipeline.py`.

---

## 1. Problem

When a PlanExe run is interrupted mid-pipeline — network drop, timeout, `plan_stop`, process crash, stuck progress — the only current MCP recovery option is `plan_retry`. `plan_retry` is destructive: it resets `progress_percentage` to 0, clears all stored artifacts (report HTML, zip snapshot, activity JSONL), and requeues the plan as a fresh run. **All completed Luigi task outputs are abandoned in the DB**, even though the on-disk run directory and Luigi-completed task files still exist.

The underlying pipeline (`run_plan_pipeline.py`) already supports resume via the `RUN_ID_DIR` environment variable: if pointed at an existing run directory, Luigi detects which tasks have output files and skips them, resuming from the first incomplete task. This capability is used in local CLI workflows but is not exposed via the MCP interface.

**Result:** users and agents running cloud plans that get stuck at 73% (as happened with plan `40ed3a60` during the 2026-03-07 HVT comparison) must choose between waiting indefinitely or triggering a full re-run from scratch.

---

## 2. Proposed Solution

Add a `plan_resume` MCP tool that:

1. Validates the plan is in a resumable state (not `completed`, not currently `processing`)
2. Resets `state → pending` in the DB **without clearing artifacts or progress**
3. Sets a `resume: true` flag in `parameters` so the worker knows to use the existing run directory
4. The worker picks up the pending plan, detects the resume flag, skips directory creation (directory already exists from prior run), and launches `run_plan_pipeline.py` with `RUN_ID_DIR` pointing at the existing dir
5. Luigi resumes from the first incomplete task

---

## 3. Architecture Analysis

### 3.1 Why `plan_retry` is wrong for resume

From `mcp_cloud/db_queries.py`, `_retry_failed_plan_sync()`:

```python
plan.state = PlanState.pending
plan.progress_percentage = 0.0
plan.generated_report_html = None
plan.run_zip_snapshot = None
plan.run_track_activity_jsonl = None
plan.run_activity_overview_json = None
```

This wipes all DB-stored progress. The on-disk run directory is NOT deleted (the worker creates a new dir per `task_id`), but the DB state no longer reflects it.

### 3.2 How `worker_plan_database` dispatches a run

From `worker_plan_database/app.py` line ~1051:

```python
run_id_dir = BASE_DIR_RUN / task_id
run_id_dir.mkdir(parents=True, exist_ok=True)

start_time_file = StartTime.create(local_time=start_time)
start_time_file.save(str(run_id_dir / FilenameEnum.START_TIME.value))

plan_file = PlanFile.create(vague_plan_description=prompt, start_time=start_time)
plan_file.save(str(run_id_dir / FilenameEnum.INITIAL_PLAN.value))
```

The worker always creates a fresh run directory and overwrites `start_time.json` and `initial_plan.json`. For a resume, this is wrong: it would overwrite seed files in an existing directory.

**Fix required in `worker_plan_database/app.py`:** check `parameters.get("resume")` before mkdir/seed-file creation. If `resume: true`, skip directory creation and seed-file writes; the directory and seed files already exist.

### 3.3 `run_plan_pipeline.py` resume mechanics

From the module docstring:

```
In order to resume an unfinished run.
Insert the run_id_dir of the thing you want to resume.
If it's an already finished run, then remove the "999-pipeline_complete.txt" file.
PROMPT> RUN_ID_DIR=/absolute/path/to/PlanExe_20250216_150332 python -m worker_plan_internal.plan.run_plan_pipeline
```

Luigi skips tasks that already have output files. No code changes needed in the pipeline itself — just don't overwrite the existing directory.

### 3.4 `worker_plan` (HTTP worker) resume path

`worker_plan/app.py` already supports this via `submit_or_retry = "retry"`:

```python
if request.submit_or_retry == "retry":
    if not request.run_id:
        raise HTTPException(...)
    run_dir = RUN_BASE_PATH / request.run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, ...)
    return request.run_id, run_dir.resolve()  # no mkdir, no seed files
```

This path is not used by `worker_plan_database` (which runs the pipeline directly, not via HTTP), but confirms the resume pattern is already understood by the codebase.

---

## 4. Resumable States

| Plan State | `plan_resume` allowed? | Reason |
|---|---|---|
| `pending` | ❌ No | Already queued; don't double-queue |
| `processing` | ❌ No | Already running |
| `completed` | ❌ No | Nothing to resume |
| `failed` | ✅ Yes | Terminal state, run dir likely intact |
| `stopped` (via `plan_stop`) | ✅ Yes | Intentionally halted, run dir intact |

**Note:** `plan_stop` now transitions to the dedicated `stopped` state (implemented in Proposal 114-I1, Option A), disambiguating user-initiated halts from error failures.

---

## 5. Implementation Spec

### 5.1 New MCP tool: `plan_resume`

**File:** `mcp_cloud/tool_models.py`

```python
class PlanResumeRequest(BaseModel):
    plan_id: str = Field(description="The plan_id returned by plan_create.")
```

**File:** `mcp_cloud/db_queries.py` — new function:

```python
def _resume_plan_sync(plan_id: str) -> Optional[dict[str, Any]]:
    with app.app_context():
        plan = find_plan_by_id(plan_id)
        if plan is None:
            return None

        if plan.state not in (PlanState.failed,):
            return {
                "error": {
                    "code": "PLAN_NOT_RESUMABLE",
                    "message": f"Plan {plan_id} is in state {plan.state.value!r}; only failed plans can be resumed.",
                }
            }

        parameters = dict(plan.parameters) if isinstance(plan.parameters, dict) else {}
        parameters["resume"] = True
        parameters["trigger_source"] = "mcp plan_resume"

        # Reset state to pending WITHOUT clearing progress or artifacts
        plan.state = PlanState.pending
        plan.stop_requested = False
        plan.stop_requested_timestamp = None
        plan.parameters = parameters
        # Intentionally NOT clearing: progress_percentage, progress_message,
        # generated_report_html, run_zip_snapshot, run_track_activity_jsonl,
        # run_activity_overview_json

        db.session.commit()

        return {
            "plan_id": plan_id,
            "status": "resume_queued",
            "message": "Plan requeued for resume. Luigi will skip completed tasks and continue from first incomplete task.",
        }
```

**File:** `mcp_cloud/handlers.py` — new handler:

```python
async def handle_plan_resume(arguments: dict[str, Any]) -> CallToolResult:
    """Resume an interrupted plan without discarding completed pipeline outputs."""
    req = PlanResumeRequest(**arguments)
    result = await asyncio.to_thread(_resume_plan_sync, req.plan_id)

    if result is None:
        response = {"error": {"code": "PLAN_NOT_FOUND", "message": f"Plan not found: {req.plan_id}"}}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(response))], isError=True)

    if "error" in result:
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))], isError=True)

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result))],
        structuredContent=result,
    )
```

Register in `TOOL_HANDLERS`:
```python
"plan_resume": handle_plan_resume,
```

### 5.2 Worker dispatch change

**File:** `worker_plan_database/app.py` — in the task dispatch function (around line 1051):

```python
# Check if this is a resume (existing run dir, don't overwrite seed files)
is_resume = parameters.get("resume", False)

run_id_dir = BASE_DIR_RUN / task_id
if is_resume:
    if not run_id_dir.exists():
        logger.warning(
            "plan_resume requested for task %s but run_id_dir does not exist at %s; "
            "falling back to fresh run.",
            task_id, run_id_dir
        )
        is_resume = False

if not is_resume:
    run_id_dir.mkdir(parents=True, exist_ok=True)
    start_time_file = StartTime.create(local_time=datetime.now().astimezone())
    start_time_file.save(str(run_id_dir / FilenameEnum.START_TIME.value))
    plan_file = PlanFile.create(vague_plan_description=prompt, start_time=start_time)
    plan_file.save(str(run_id_dir / FilenameEnum.INITIAL_PLAN.value))
else:
    logger.info("Resuming existing run directory: %s", run_id_dir)
```

### 5.3 MCP tool description (for agent discovery)

```
plan_resume(plan_id): Resume an interrupted or failed plan without discarding completed pipeline outputs.
Luigi will skip already-completed tasks and continue from the first incomplete task.
Use this when plan_status shows 'failed' but the run was interrupted mid-pipeline (not a model error).
For model errors (structured output failures), use plan_retry instead.
```

---

## 6. `plan_resume` vs `plan_retry` — When to Use Which

| Scenario | Use |
|---|---|
| Plan stuck mid-pipeline (timeout, network, crash) | `plan_resume` |
| Plan stopped via `plan_stop` | `plan_resume` |
| Model failed structured output validation | `plan_retry` |
| Want to try a different model profile | `plan_retry` |
| planexe.org plan at 73% and not moving | `plan_resume` |

---

## 7. Files Changed

| File | Change | Scope |
|---|---|---|
| `mcp_cloud/tool_models.py` | Add `PlanResumeRequest` | +5 lines |
| `mcp_cloud/db_queries.py` | Add `_resume_plan_sync()` | +35 lines |
| `mcp_cloud/handlers.py` | Add `handle_plan_resume()`, register in `TOOL_HANDLERS` | +20 lines |
| `worker_plan_database/app.py` | Guard seed-file creation with `is_resume` check | +15 lines |
| `docs/mcp/planexe_mcp_interface.md` | Document `plan_resume` tool in section 1.2.1 agent summary | +5 lines |

**Total scope:** ~80 lines across 5 files. No schema migrations required (uses existing `parameters` JSONB column for `resume` flag).

---

## 8. Companion improvement: expose current Luigi task in `plan_status`

During the 2026-03-07 HVT infra stall (plan `40ed3a60`), the UI execution trace showed LLM call timestamps and durations but not which Luigi task the pipeline was executing when the worker dropped. Identifying the stalled task required server-side Railway logs — not available to agents or users.

**Proposed addition to `plan_status` response:**

```json
{
  "plan_id": "...",
  "state": "processing",
  "progress_percentage": 74.0,
  "current_task": "CreateWBSLevel3Task",  // ← new field
  "last_llm_call_at": "2026-03-07T16:21:29Z"  // ← new field
}
```

This requires the worker to write the current task name to a lightweight status file in `run_id_dir` (e.g. `current_task.json`) that the progress polling endpoint reads. Minimal implementation cost; significant diagnostic value. Particularly useful for `plan_resume` decisions — an agent can see exactly what task it stalled on before deciding whether to resume or retry.

---

## 9. Out of Scope

- ~~Introducing a distinct `stopped` state (separate from `failed`)~~ — implemented (Proposal 114-I1)
- Progress scrubbing on resume (reporting accurate % based on remaining tasks) — deferred
- `plan_resume` for `mcp_local` (local HTTP worker via `worker_plan/app.py`) — the HTTP worker already supports this via `submit_or_retry="retry"`; a follow-on can wire it up
- Resume after partial artifact upload failure — deferred

---

## 9. Risks

- **Run dir missing:** If the worker's disk was wiped between stop and resume, `run_id_dir` won't exist. Mitigation: the fallback in §5.2 detects this and falls back to a fresh run with a warning log.
- **Seed file corruption:** If `start_time.json` or `initial_plan.json` in the existing dir is corrupt, the pipeline will fail at validation. Mitigation: existing `_validate_run_dir()` in `ping_llm.py` catches this early.
- **Luigi task cache invalidation:** If upstream pipeline code changed between the original run and resume, Luigi may rerun tasks unnecessarily. This is expected Luigi behaviour and is not a bug.
