# Proposal 114: MCP Interface Issues from 10-Plan Agent Stress Test

**Date:** 2026-03-11
**Status:** Proposal
**Source:** Feedback from Claude (Opus 4.6) after a 10-plan stress-testing session operated through Claude Code CLI.
**Scope:** MCP interface design, observability, and lifecycle management. Does not cover plan content quality or pipeline output improvements.

---

## 1. Context

A 10-plan stress test was conducted through Claude Code CLI using the PlanExe MCP interface.

The testing surfaced concrete MCP interface friction points that affect agent operators — issues with state management, observability, lifecycle hygiene, and workflow ergonomics. This proposal catalogues the MCP-specific issues and maps them against existing proposals.

---

## 2. Issues

### I1 — `failed` state conflates user-stop and actual failure

**Status:** Implemented (Option A — dedicated `PlanState.stopped` DB state). Supersedes PR #244's Option B (`stop_reason` field).

**Problem:** When `plan_stop` is called, the plan transitions to `failed`. When a worker crashes, it also transitions to `failed`. The agent operator cannot distinguish between:
- User-initiated stop (nothing went wrong)
- Actual failure (network drop, model error, worker crash)

This matters because the correct response differs: user stop suggests `plan_resume`; actual failure may need `plan_retry` or investigation.

**Overlap:** Proposal 87 (plan_resume) acknowledged this in §4 — now updated to reflect the implementation.

**Options:**

| Option | Description | Breaking change? |
|--------|-------------|-----------------|
| A. New `stopped` state | `plan_stop` → `stopped`, worker crash → `failed` | Yes (new enum value in API responses) |
| B. `stop_reason` field | Keep `failed` but add `stop_reason`: `"user_requested"`, `"worker_crash"`, `"timeout"`, `"model_error"`, `null` | No |

Option B is less disruptive and can be added to `plan_status` without changing state enum values.

**Implemented approach:** Option A — a dedicated `PlanState.stopped` enum value (value 5). `plan_stop` now transitions plans to the `stopped` state instead of `failed`. The `stop_reason` field introduced in PR #244 (Option B) has been removed — the state itself communicates intent. `plan_retry` and `plan_resume` accept both `failed` and `stopped` states. DB migration adds `'stopped'` to the PostgreSQL enum type (both `taskstate` for pre-rename databases and `planstate` for fresh databases — the Python class was renamed from `TaskState` to `PlanState` in proposal 74 but the PostgreSQL type name was not changed). The worker's post-pipeline finalization also transitions to `stopped` (not `failed`) when `stop_requested` is true.

**Affected files:** `database_api/model_planitem.py`, `mcp_cloud/db_setup.py`, `worker_plan_database/app.py`, `mcp_cloud/db_queries.py`, `mcp_cloud/handlers.py`, `mcp_cloud/sse.py`, `mcp_cloud/tool_models.py`, `mcp_cloud/schemas.py`, `mcp_local/planexe_mcp_local.py`, `frontend_multi_user/src/app.py`, `frontend_multi_user/src/planexe_modelviews.py`, `frontend_multi_user/templates/plan_iframe.html`, `frontend_multi_user/templates/run_via_database.html`, `frontend_multi_user/templates/index.html`, `frontend_multi_user/templates/account.html`, `mcp_cloud/tests/test_plan_status_tool.py`, `docs/mcp/planexe_mcp_interface.md`, `docs/mcp/autonomous_agent_guide.md`, `docs/proposals/87-plan-resume-mcp-tool.md`, `docs/proposals/111-promising-directions.md`.

---

### I2 — No failure diagnostics in `plan_status`

**Priority: High — identified as the single biggest observability gap.**

**Problem:** When a plan fails, `plan_status` returns `state: "failed"` with no `failure_reason`, `last_error`, or `failed_step` field. The agent can only tell the user "it failed" without explaining why.

During the stress test, Plan 1 (20f1cfac) stalled at 5.5% with zero diagnostic information. The operator had no way to determine if it was a content refusal, a model error, or a worker crash.

**Overlap:** Proposal 113 (LLM Error Traceability) preserves errors in usage metrics logs but does not surface them in `plan_status` responses to the MCP consumer.

**Proposed addition to `plan_status` response (on failure):**

```json
{
  "state": "failed",
  "failure_reason": "model_error",
  "failed_step": "016-expert_criticism",
  "last_error": "openrouter-gemini-2.0-flash-001 returned invalid_json"
}
```

**Implementation path:** The worker already logs errors internally. When transitioning to `failed`, write `failure_reason`, `failed_step`, and `last_error` to the plan's DB record (e.g. in the `parameters` JSONB column or new dedicated columns). `plan_status` handler surfaces these fields when `state == "failed"`.

**Affected files:** `worker_plan_database/app.py` (error capture on failure), `mcp_cloud/db_queries.py` (store failure info), `mcp_cloud/handlers.py` (include in plan_status response).

---

### I3 — No plan deletion or cleanup

**Problem:** Stopped and failed plans persist in `plan_list` indefinitely. After 10 plans, the list becomes noisy. There is no way to clean up test runs, abandoned plans, or experiments.

**Proposed solutions (pick one or both):**

| Tool | Behavior |
|------|----------|
| `plan_delete` | Permanently remove a plan from the user's list. Only allowed for terminal states (`completed`, `failed`, `stopped`). |
| `plan_archive` | Soft-delete: plan is hidden from `plan_list` but remains in DB for auditing. |

`plan_archive` is safer for a billing system where plan records may need to be retained.

**Affected files:** `mcp_cloud/db_queries.py`, `mcp_cloud/handlers.py`, `mcp_cloud/schemas.py`, `mcp_cloud/tool_models.py`.

---

### I4 — No idempotency guard on `plan_create`

**Status:** Implemented (PR #242).

**Problem:** If the user double-clicks or the agent accidentally submits twice, two identical plans are created. Each `plan_create` call generates a new `plan_id` with no server-side deduplication.

**Original proposal:** Add an optional `request_id` (client-generated UUID) parameter to `plan_create`. The server checks if a plan with the same `request_id` already exists for this user. This is a standard idempotency pattern (Stripe, AWS, etc.).

**Why `request_id` was not adopted:** The primary MCP consumers are LLM agents. LLMs cannot generate UUIDs natively — they would need an extra tool call just to produce the idempotency key, adding friction to the exact workflow it's meant to protect. A mechanism that requires client cooperation is a poor fit when the clients are language models.

**Implemented approach:** Automatic server-side dedup. Before inserting a new plan, `_create_plan_sync` queries for an existing `pending`/`processing` plan matching `(user_id, prompt, model_profile)` created within a configurable time window (default 10 minutes, env `PLANEXE_DEDUP_WINDOW_SECONDS`). If found, the existing plan is returned with `deduplicated: true` instead of creating a new one. No schema migration needed — uses existing columns. Set `PLANEXE_DEDUP_WINDOW_SECONDS=0` to disable.

**Known limitation:** There is a TOCTOU race — if two identical requests arrive concurrently and both pass the dedup check before either commits, a duplicate plan is created. This is accepted; the cost is wasted tokens for one extra plan, which is not worth the complexity of a database-level lock or migration to fix.

**Affected files:** `mcp_cloud/db_queries.py` (`_find_recent_duplicate_plan`, `_create_plan_sync`), `mcp_cloud/tool_models.py` (`deduplicated` field on `PlanCreateOutput`), `mcp_cloud/schemas.py` (description and `idempotentHint`), `mcp_cloud/app.py` (re-export).

---

### I5 — SSE events carry no structured progress data

**Problem:** The SSE stream works as a completion detector but events are opaque — no `step_name` or `progress_percentage` in event payloads. To get progress, the agent must poll `plan_status` separately, making SSE useful only as a "done" signal.

**Overlap:** Proposal 70 §5.1 (SSE progress streaming) is implemented but events only trigger on state/progress changes without rich payload.

**Proposed enrichment of SSE `status` events:**

```
event: status
data: {"state":"processing","progress_percentage":42.0,"current_step":"016-expert_criticism","steps_completed":16,"steps_total":38}
```

This would eliminate the need for `plan_status` polling entirely when SSE is available.

**Affected files:** `mcp_cloud/sse.py` (enrich event payloads).

---

### I6 — Download URL expiry (15 minutes) is too short

**Problem:** When a user takes time reviewing results before downloading, the signed download URL expires silently. Calling `plan_file_info` again works, but the 15-minute window creates unnecessary friction.

**Proposed fix:** Extend default TTL from 15 to 30–60 minutes. Make it configurable via `PLANEXE_DOWNLOAD_TOKEN_TTL_SECONDS` environment variable.

**Affected files:** `mcp_cloud/download_tokens.py` (change default TTL constant, add env var override).

---

### I7 — No stalled-plan detection

**Problem:** Plan 1 (20f1cfac) stayed at 5.5% for multiple status checks with no indication of whether it was still working, stuck, or had silently failed. There is no `stalled_since` timestamp or heartbeat indicator in `plan_status`.

**Overlap:** Proposal 87 §8 proposes `current_task` and `last_llm_call_at` fields — these would partially address this, but there is no explicit stall detection.

**Proposed additions to `plan_status`:**

| Field | Description |
|-------|-------------|
| `last_progress_at` | ISO 8601 timestamp of the last progress update. Enables the agent to compute time-since-last-progress and decide whether to wait, resume, or retry. |
| `last_llm_call_at` | ISO 8601 timestamp of the most recent LLM call. A gap > 5 minutes with no progress change is a strong stall signal. |

**Affected files:** `worker_plan_database/app.py` (write timestamps on progress), DB model (new timestamp columns), `mcp_cloud/handlers.py` (include in response).

---

### I8 — No `plan_wait` tool for agents without shell access

**Problem:** The recommended SSE monitoring pattern (`curl -N <sse_url>`) requires Bash tool access. Agents running in pure MCP client environments (no shell) can only poll `plan_status`. A blocking `plan_wait` tool would let these agents simply wait for completion.

**Proposed tool:**

```
plan_wait(plan_id, timeout_seconds=1200): Blocks until the plan reaches a terminal state
(completed, failed, stopped) or the timeout expires. Returns the final plan_status response.
```

**Implementation:** Server-side long-poll using the existing SSE infrastructure. The handler subscribes to the plan's state changes and returns when terminal or timeout.

**Consideration:** Long-running HTTP requests may conflict with proxy/load-balancer timeouts. Default timeout should be ≤ 20 minutes. May need to be implemented as repeated short polls on the server side with a single response.

**Affected files:** `mcp_cloud/handlers.py`, `mcp_cloud/schemas.py`, `mcp_cloud/tool_models.py`.

---

### I9 — Prompt iteration has no memory

**Problem:** Each `plan_create` is independent. When iterating on a prompt (e.g. refining "The Game" movie remake across 4 variations), there is no way to link plans or diff their prompts. The agent must manually track the relationship between plans.

**Proposed fix:** Add an optional `parent_plan_id` parameter to `plan_create`. When set:
- The new plan is linked to its parent in the DB
- `plan_list` can optionally filter by lineage
- `plan_status` includes `parent_plan_id` in the response

This enables prompt iteration tracking without changing existing behavior for plans created without a parent.

**Affected files:** `mcp_cloud/tool_models.py` (new optional field), `mcp_cloud/db_queries.py` (store parent reference), DB model (new nullable column).

---

## 3. Cross-Reference with Existing Proposals

| Issue | Existing Proposal | Gap |
|-------|-------------------|-----|
| I1 (stopped vs failed) | 87 §4 (deferred) | **Implemented** (Option A — dedicated `PlanState.stopped`) |
| I2 (failure diagnostics) | 113 (logs only) | Not surfaced to MCP consumer |
| I3 (plan_delete) | None | New |
| I4 (idempotency) | None | **Implemented** (PR #242) |
| I5 (rich SSE events) | 70 §5.1 (basic SSE done) | Events lack structured data |
| I6 (download TTL) | 70 §4 (tokens done) | TTL too short, not configurable |
| I7 (stall detection) | 87 §8 (partial) | No explicit stall timestamps |
| I8 (plan_wait) | None | New |
| I9 (prompt iteration) | None | New |

---

## 4. Overlap with Proposal 70 (MCP Interface Evaluation and Roadmap)

Several items here refine or extend issues already tracked in Proposal 70's checklist:

| This Proposal | Proposal 70 Item | Relationship |
|---------------|-------------------|-------------|
| I2 (failure diagnostics) | 70 §5.6 (pipeline stage names) | Complementary — 70 focuses on progress UX, I2 focuses on failure UX |
| I5 (rich SSE) | 70 §5.1 (SSE implemented) | Extension — SSE works but events are thin |
| I6 (download TTL) | 70 (signed tokens done) | Refinement — increase TTL |

If accepted, I1–I4 and I7–I9 should be added to Proposal 70's quick-win checklist as new line items.

---

## 5. Suggested Priority

| Priority | Issues | Rationale |
|----------|--------|-----------|
| P1 | I2 (failure diagnostics) | Biggest observability gap. Agent cannot help users debug failures without this. |
| ~~P1~~ | ~~I1 (stopped vs failed)~~ | **Implemented** (Option A). Dedicated `PlanState.stopped` enum value — `plan_stop` transitions to `stopped`, not `failed`. |
| P2 | I7 (stall detection) | Prevents agents from waiting indefinitely on stuck plans. |
| P2 | I6 (download TTL) | Low effort, reduces friction. |
| P2 | I5 (rich SSE events) | Eliminates polling for SSE-capable clients. |
| P2 | I3 (plan_delete) | Hygiene for multi-plan sessions. |
| ~~P3~~ | ~~I4 (idempotency)~~ | **Implemented** (PR #242). Server-side auto-dedup on `(user_id, prompt, model_profile)` within a time window. |
| P3 | I8 (plan_wait) | Nice-to-have for shell-less agents. |
| P3 | I9 (prompt iteration) | Nice-to-have for iteration workflows. |
