# PlanExe MCP Feedback Tool — Specification

## Status

**Implemented** as `send_feedback` (renamed from `plan_feedback` during implementation).

- PR #401: initial implementation
- PR #402: rename to `send_feedback`, add auth, simplify categories (mcp/plan/code/docs/other), remove severity, update descriptions
- PR #403: docs fix (auth via header, not parameter)
- PR #404: update llms.txt, planexe_mcp_interface.md, plan.md

Key differences from original proposal:
- Tool name: `send_feedback` (not `plan_feedback`)
- Categories simplified to 5: `mcp`, `plan`, `code`, `docs`, `other`
- `severity` parameter removed — callers express severity in the message
- `rating` renamed to sentiment: 1=strong negative, 2=weak negative, 3=neutral, 4=weak positive, 5=strong positive
- Auth uses same pattern as `plan_create` (X-API-Key header)
- Visible in Flask admin UI as "Feedback"

---

## Original Proposal

### Overview

A new MCP tool (`plan_feedback`) that allows LLM consumers to submit structured feedback about the PlanExe MCP interface. Feedback can be tied to a specific plan or be general. The tool is non-blocking, fire-and-forget, and never gates the workflow.

### Tool Name

`plan_feedback`

## Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category` | enum | yes | — | Feedback category (see enum below) |
| `message` | string | yes | — | Free-text observation. Should be concise and actionable. |
| `plan_id` | string \| null | no | null | Plan UUID to attach feedback to. Omit for general/workflow feedback. |
| `rating` | integer \| null | no | null | Satisfaction score 1–5. 1 = poor, 3 = acceptable, 5 = excellent. Omit if not applicable (e.g., bug reports). |
| `severity` | enum \| null | no | null | For issue reports: `low`, `medium`, `high`. Omit for non-issue feedback (compliments, suggestions). |

### `category` Enum

| Value | When to use |
|-------|-------------|
| `sse_issue` | SSE stream closed before plan reached terminal state, or SSE behaved unexpectedly. |
| `status_staleness` | `plan_status` returned stale or inconsistent data (e.g., showing `processing` when plan was actually completed). |
| `queue_delay` | Plan stayed at 0% with `last_progress_at: null` for an unusually long time before a worker picked it up. |
| `file_visibility` | Intermediate files not appearing in `plan_status` during processing when they should be. |
| `plan_quality` | Feedback on the quality of the generated plan output (report content, depth, accuracy, relevance). |
| `tool_description` | Feedback on the tool descriptions themselves (clarity, accuracy, missing info). |
| `workflow` | Feedback on the overall workflow (call order, enforced steps, friction points). |
| `performance` | Feedback on speed, latency, or resource usage (slow steps, timeouts, long processing). |
| `error_handling` | Feedback on error messages, error codes, or recovery paths (clarity, actionability). |
| `suggestion` | Feature request or improvement idea. |
| `compliment` | Something that works particularly well — positive signal is as valuable as bug reports. |
| `other` | Anything that doesn't fit the above categories. |

## Tool Description (for MCP registration)

```
Submit feedback about the PlanExe MCP interface. Use this to report issues
(SSE problems, status inconsistencies, queue delays), comment on plan output
quality, or suggest improvements. Feedback can optionally be tied to a
specific plan_id. This tool is non-blocking and does not affect the planning
workflow — call it whenever you observe something noteworthy, whether
positive or negative. You do not need to call this tool for every plan;
use it when something is surprising, broken, or exceptionally good.
LLM consumers are encouraged to report: SSE streams that close before
plan completion (category=sse_issue), plan_status returning stale data
(category=status_staleness), unusually long queue waits
(category=queue_delay), and impressions of plan output quality after
reviewing reports (category=plan_quality). Include specific details
(timestamps, percentages, plan_id) when reporting issues.
```

## Request Schema (JSON Schema)

```json
{
  "type": "object",
  "title": "plan_feedbackArguments",
  "required": ["category", "message"],
  "properties": {
    "plan_id": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "default": null,
      "title": "Plan Id",
      "description": "Plan UUID to attach feedback to. Omit for general feedback not tied to a specific plan."
    },
    "category": {
      "type": "string",
      "enum": [
        "sse_issue",
        "status_staleness",
        "queue_delay",
        "file_visibility",
        "plan_quality",
        "tool_description",
        "workflow",
        "performance",
        "suggestion",
        "error_handling",
        "compliment",
        "other"
      ],
      "title": "Category",
      "description": "Feedback category. Use sse_issue for SSE reliability problems, status_staleness for plan_status returning stale data, queue_delay for slow worker pickup, file_visibility for missing intermediate files, plan_quality for output quality impressions, tool_description for feedback on tool docs, workflow for call-order or process friction, performance for speed issues, error_handling for error message quality, suggestion for feature requests, compliment for positive feedback, other for anything else."
    },
    "message": {
      "type": "string",
      "title": "Message",
      "description": "Free-text feedback. Be specific: include timestamps, percentages, step names, or other details when reporting issues. For quality feedback, note what was good or lacking in the output."
    },
    "rating": {
      "anyOf": [{"type": "integer", "minimum": 1, "maximum": 5}, {"type": "null"}],
      "default": null,
      "title": "Rating",
      "description": "Optional satisfaction score: 1=poor, 2=below expectations, 3=acceptable, 4=good, 5=excellent. Omit for bug reports or suggestions where a score doesn't apply."
    },
    "severity": {
      "anyOf": [
        {"type": "string", "enum": ["low", "medium", "high"]},
        {"type": "null"}
      ],
      "default": null,
      "title": "Severity",
      "description": "Optional severity for issue reports. low=minor inconvenience (workaround exists), medium=significant friction (degrades workflow), high=blocks workflow or produces wrong results. Omit for non-issue feedback."
    }
  }
}
```

## Response Schema

### Success

```json
{
  "feedback_id": "uuid",
  "received_at": "2026-03-28T14:30:00Z",
  "message": "Feedback received. Thank you."
}
```

### Validation Error

```json
{
  "error": {
    "code": "INVALID_FEEDBACK",
    "message": "Human-readable validation error (e.g., 'category is required', 'rating must be 1-5')."
  }
}
```

### Plan Not Found (when plan_id is provided but invalid)

```json
{
  "error": {
    "code": "PLAN_NOT_FOUND",
    "message": "The provided plan_id does not exist."
  }
}
```

## Storage Recommendations

Each feedback entry should be stored with:

| Field | Source |
|-------|--------|
| `feedback_id` | Server-generated UUID |
| `received_at` | Server timestamp (ISO 8601) |
| `plan_id` | From request (nullable) |
| `category` | From request |
| `message` | From request |
| `rating` | From request (nullable) |
| `severity` | From request (nullable) |
| `user_id` | From auth context (if available) |
| `client_type` | Inferred from request context (e.g., `claude-code`, `cursor`, `api-direct`) |
| `server_instance` | Which server received it (`planexelocal`, `planexeremote`) |

If `plan_id` is provided and valid, also snapshot and store alongside the feedback:
- `plan_state` at time of feedback
- `plan_progress_percentage` at time of feedback
- `plan_model_profile`
- `plan_elapsed_sec`

This allows correlating subjective feedback with objective plan telemetry.

## Behavioral Contract

- **Non-blocking.** The tool should respond quickly (< 1 second). Do not validate plan_id against a slow database synchronously if it would add latency — accept the feedback and validate asynchronously.
- **Fire-and-forget.** Feedback submission should never fail in a way that disrupts the caller's workflow. If storage fails internally, return success anyway and log the failure server-side.
- **No rate limiting on LLM consumers.** LLMs will typically submit 0–5 feedback items per session. If abuse is a concern, rate-limit per user_id, not per session.
- **Idempotent-safe.** Duplicate submissions (same plan_id + category + message within a short window) can be deduplicated server-side, but should still return success to the caller.

## Example Calls

### SSE early close (plan-attached, high severity)
```json
{
  "plan_id": "f7bd019f-ad73-4285-ba79-267614d7e7fb",
  "category": "sse_issue",
  "message": "SSE stream closed twice within seconds of starting (exit code 0). Plan was at 7.3% (8/110 steps). Had to fall back to polling entirely. Restarted SSE monitor, which also closed immediately.",
  "severity": "high"
}
```

### Queue delay (plan-attached, medium severity)
```json
{
  "plan_id": "73c76797-8ecb-4978-afff-35f94915b2cd",
  "category": "queue_delay",
  "message": "Plan sat at 0% with last_progress_at: null for approximately 15 minutes before a worker picked it up. Processing itself took ~12 minutes once started.",
  "severity": "medium"
}
```

### Plan quality (plan-attached, with rating)
```json
{
  "plan_id": "8ed556ef-346c-4a50-8c43-5dae5c2c13cc",
  "category": "plan_quality",
  "message": "Dual-budget prompt (overt + covert financial paths) produced the richest output of the session: 855 KB report, 206 pipeline files. The adversarial sections (premortem, premise attacks) engaged meaningfully with the political opacity constraints in the prompt.",
  "rating": 5
}
```

### Workflow feedback (general, no plan_id)
```json
{
  "category": "workflow",
  "message": "The enforced example_prompts -> draft -> approve -> plan_create flow is effective for first plans in a session. For subsequent plans, having to call example_prompts again adds friction without value since the prompt style is already calibrated.",
  "rating": 4
}
```

### Suggestion (general)
```json
{
  "category": "suggestion",
  "message": "A credit_balance or account_status tool would allow proactive credit checking before plan submission, preventing wasted prompt-drafting effort when credits are depleted."
}
```

### Compliment (general)
```json
{
  "category": "compliment",
  "message": "Tool descriptions are the best-documented MCP interface I've worked with. They function as a complete operational manual — call order, field semantics, error codes, timing expectations, and state contracts are all inline. Enables fully autonomous operation.",
  "rating": 5
}
```

### Intermediate file visibility fixed (general, positive)
```json
{
  "category": "file_visibility",
  "message": "Remote server is now showing intermediate files during processing (observed 29 files at 22.7% on plan 97b17f66). This was previously broken — files only appeared at completion. The fix is confirmed and appreciated.",
  "rating": 4
}
```

## Integration Notes

- Add `plan_feedback` to the MCP server instructions block so LLM consumers know it exists. Suggested line: *"Use plan_feedback to report issues or share observations about the interface, plan quality, or workflow. Non-blocking and optional."*
- The tool should be callable at any point in the workflow — before, during, or after plan creation.
- Consider a lightweight dashboard or periodic digest that aggregates feedback by category, severity, and plan_id for developer review.
