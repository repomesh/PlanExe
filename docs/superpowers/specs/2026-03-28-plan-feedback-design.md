# Design: `plan_feedback` MCP Tool

**Date:** 2026-03-28
**Proposal:** [127-mcp-feedback.md](../../proposals/127-mcp-feedback.md)

## Summary

Add a `plan_feedback` MCP tool that allows LLM consumers to submit structured feedback about the PlanExe MCP interface, plan quality, and workflow experiences. Feedback is stored in PostgreSQL for later analysis. The tool is non-blocking and fire-and-forget: it always returns success to the caller even if storage fails internally.

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | enum | yes | One of: `sse_issue`, `status_staleness`, `queue_delay`, `file_visibility`, `plan_quality`, `tool_description`, `workflow`, `performance`, `error_handling`, `suggestion`, `compliment`, `other` |
| `message` | string | yes | Free-text feedback (concise, actionable) |
| `plan_id` | string\|null | no | UUID to attach feedback to a specific plan |
| `rating` | integer 1-5\|null | no | Satisfaction score |
| `severity` | enum\|null | no | `low`, `medium`, or `high` (for issue reports) |

## Response

### Success (always returned to caller)

```json
{
  "feedback_id": "uuid",
  "received_at": "2026-03-28T14:30:00Z",
  "message": "Feedback received. Thank you."
}
```

### Validation Errors

```json
{
  "error": {
    "code": "INVALID_FEEDBACK",
    "message": "Human-readable validation error"
  }
}
```

```json
{
  "error": {
    "code": "PLAN_NOT_FOUND",
    "message": "Plan not found: <plan_id>"
  }
}
```

## Database Table: `feedback_item`

| Column | Type | Notes |
|--------|------|-------|
| `id` | VARCHAR(36) | PK, UUID generated server-side |
| `received_at` | TIMESTAMP | UTC, indexed, default now() |
| `category` | VARCHAR(32) | One of 12 enum values |
| `message` | TEXT | Free-text feedback |
| `plan_id` | VARCHAR(36) | Nullable, references task_item(id) |
| `rating` | INTEGER | Nullable, 1-5 |
| `severity` | VARCHAR(8) | Nullable: low/medium/high |
| `user_id` | VARCHAR(36) | Nullable, resolved from auth context |
| `plan_progress_pct` | FLOAT | Nullable, snapshot at feedback time |
| `plan_state` | VARCHAR(16) | Nullable, snapshot at feedback time |
| `plan_current_step` | VARCHAR(128) | Nullable, snapshot at feedback time |

No foreign key constraint on `plan_id` to keep writes simple and avoid blocking on plan table locks.

## Files to Create/Modify

### New File
- `database_api/model_feedback.py` — SQLAlchemy model `FeedbackItem`

### Modified Files
- `mcp_cloud/tool_models.py` — Add `PlanFeedbackInput`, `PlanFeedbackOutput` Pydantic models
- `mcp_cloud/schemas.py` — Add schema constants and `ToolDefinition` entry
- `mcp_cloud/handlers.py` — Add `handle_plan_feedback()`, register in `TOOL_HANDLERS`
- `mcp_cloud/db_setup.py` — Import model, add `PlanFeedbackRequest`, update `PLANEXE_SERVER_INSTRUCTIONS`
- `mcp_cloud/db_queries.py` — Add `_create_feedback_sync()` and `_get_plan_snapshot_for_feedback_sync()`

## Handler Logic

1. Parse and validate input via `PlanFeedbackRequest` (Pydantic BaseModel)
2. If `plan_id` provided:
   - Look up plan via `_get_plan_snapshot_for_feedback_sync()`
   - If not found, return `PLAN_NOT_FOUND` error (this is the only error visible to caller)
   - If found, capture snapshot: `progress_percentage`, `state`, `current_step`
3. Generate `feedback_id` (UUID4) and `received_at` (UTC now)
4. Write to DB in try/except:
   - On success: return `{feedback_id, received_at, message}`
   - On failure: **log the error**, still return success response (fire-and-forget)
5. Response is always `isError=False` except for `PLAN_NOT_FOUND` and `INVALID_FEEDBACK`

## Tool Annotations

```python
annotations={
    "readOnlyHint": False,   # writes to DB
    "destructiveHint": False, # no destructive side effects
    "idempotentHint": True,   # duplicate submissions are safe
    "openWorldHint": False,   # no external calls
}
```

## Server Instructions Update

Add to `PLANEXE_SERVER_INSTRUCTIONS`:
> "Use plan_feedback to report issues or share observations about plan quality, workflow friction, or the MCP interface. Feedback is fire-and-forget and never blocks the workflow."

## Behavioral Guarantees

- Non-blocking: handler returns in <1 second
- Fire-and-forget: never gates workflow
- No rate limiting on LLM consumers
- Always returns success to caller (except validation/plan-not-found errors)
- Internal storage failures are logged but not surfaced to caller

## Testing

Follow existing test patterns (e.g., `test_plan_create_tool.py`):
- Valid feedback with all fields
- Valid feedback with only required fields
- Invalid category returns INVALID_FEEDBACK
- Invalid plan_id returns PLAN_NOT_FOUND
- Rating out of range returns INVALID_FEEDBACK
- Invalid severity returns INVALID_FEEDBACK
- DB write failure still returns success (fire-and-forget)
