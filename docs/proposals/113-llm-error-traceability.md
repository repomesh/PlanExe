# Proposal: LLM Error Traceability via Error UUIDs

**Author:** neoneye
**Date:** 2026-03-10
**Status:** Draft

---

## Problem

When an LLM call fails inside a pipeline task, the exception is caught and re-raised as a generic `ValueError`:

```python
except Exception as e:
    logger.debug(f"LLM chat interaction failed: {e}")
    logger.error("LLM chat interaction failed.", exc_info=True)
    raise ValueError("LLM chat interaction failed.") from e
```

This pattern appears in **36 files** across the codebase. By the time `LLMExecutor` catches the re-raised `ValueError`, `str(e)` is the fixed string `"LLM chat interaction failed."` — the root cause (timeout, auth error, invalid JSON, etc.) is lost.

PR #236 added `classify_error()` to categorize error strings into short labels for `usage_metrics.jsonl`. But because the original exception is masked, these errors all classify as `"unknown"` with `error_detail: "LLM chat interaction failed."` — defeating the purpose of classification.

The root cause *is* logged via `logger.error(..., exc_info=True)`, but there is no way to correlate a log line with a specific row in `usage_metrics.jsonl`.

---

## Goals

1. **Preserve the root cause** so `classify_error()` can categorize it correctly.
2. **Correlate metrics with logs** so a user can look up the full traceback for any failed metric row.
3. **Keep the change mechanical** — the 36 call sites should all follow the same pattern.
4. **No behaviour change** — callers that catch `ValueError` must continue to work.

---

## Design

### 1. Introduce `LLMChatError` exception

Replace the generic `ValueError` with a dedicated exception that carries structured context:

```python
# worker_plan/worker_plan_internal/llm_util/llm_errors.py

import uuid

class LLMChatError(Exception):
    """Raised when an LLM chat interaction fails.

    Carries the root-cause exception and a unique error_id for
    cross-referencing log entries with usage_metrics.jsonl rows.
    """
    def __init__(self, cause: Exception, error_id: str | None = None):
        self.cause = cause
        self.error_id = error_id or uuid.uuid4().hex[:12]
        super().__init__(f"LLM chat interaction failed [{self.error_id}]: {cause}")
```

Key properties:
- `str(LLMChatError)` now includes the root cause, so `classify_error()` works correctly.
- `error_id` is a short UUID (12 hex chars) printed in both the log and the metric row.
- Subclasses `Exception` (not `ValueError`), but see migration notes below.

### 2. Update the 36 call sites

Each call site changes from:

```python
except Exception as e:
    logger.debug(f"LLM chat interaction failed: {e}")
    logger.error("LLM chat interaction failed.", exc_info=True)
    raise ValueError("LLM chat interaction failed.") from e
```

To:

```python
from worker_plan_internal.llm_util.llm_errors import LLMChatError

except Exception as e:
    llm_error = LLMChatError(cause=e)
    logger.debug(f"LLM chat interaction failed [{llm_error.error_id}]: {e}")
    logger.error(f"LLM chat interaction failed [{llm_error.error_id}]", exc_info=True)
    raise llm_error from e
```

This is mechanical — every site follows the same 4-line pattern.

### 3. Record `error_id` in `usage_metrics.jsonl`

In `record_usage_metric()`, accept an optional `error_id` parameter:

```python
def record_usage_metric(
    ...
    error_message: Optional[str] = None,
    error_id: Optional[str] = None,
    ...
) -> None:
    ...
    if error_message:
        category = classify_error(error_message)
        record["error"] = category
        if category == "unknown":
            record["error_detail"] = error_message[:200]
        if error_id:
            record["error_id"] = error_id
```

In `LLMExecutor._record_attempt_token_metrics()`, extract the `error_id` from the exception when available:

```python
if not success:
    error_id = getattr(exc, "error_id", None) if exc else None
    record_usage_metric(
        model=llm_model_name,
        duration_seconds=duration,
        success=False,
        error_message=error_message,
        error_id=error_id,
    )
```

### 4. Example output

**Log output:**
```
ERROR LLM chat interaction failed [a3f1b9c2d4e5]: 1 validation error for ...
Traceback (most recent call last):
  ...
```

**usage_metrics.jsonl row:**
```json
{
  "timestamp": "2026-03-10T17:16:17",
  "success": false,
  "model": "openrouter-gemini-2.0-flash-001",
  "duration_seconds": 24.839,
  "error": "invalid_json",
  "error_id": "a3f1b9c2d4e5"
}
```

A user can now `grep a3f1b9c2d4e5` in the logs to find the full traceback.

---

## Migration: `ValueError` to `LLMChatError`

`LLMChatError` extends `Exception`, not `ValueError`. Any code that catches `ValueError` from LLM calls would break. There are two migration strategies:

**Option A: Temporary dual inheritance (recommended)**

```python
class LLMChatError(ValueError):
    ...
```

This keeps backward compatibility. A follow-up PR can grep for `except ValueError` near LLM calls and migrate them to `except LLMChatError`, then remove the `ValueError` base class.

**Option B: Big-bang migration**

Change `LLMChatError` to extend `Exception` and update all `except ValueError` catch sites in the same PR. Riskier but cleaner.

---

## Files to modify

| File | Change |
|---|---|
| `worker_plan/worker_plan_internal/llm_util/llm_errors.py` | **New file.** `LLMChatError` exception class. |
| `worker_plan/worker_plan_internal/llm_util/usage_metrics.py` | Add `error_id` parameter to `record_usage_metric()`. |
| `worker_plan/worker_plan_internal/llm_util/llm_executor.py` | Extract `error_id` from exception, pass to `record_usage_metric()`. |
| 36 files with `raise ValueError("LLM chat interaction failed.")` | Mechanical replacement with `LLMChatError`. |
| `worker_plan/tests/test_usage_metrics.py` | Add tests for `error_id` field. |
| `worker_plan/tests/test_llm_errors.py` | **New file.** Tests for `LLMChatError`. |

---

## Verification

1. Run existing tests — nothing should break if Option A (dual inheritance) is used.
2. Run a plan with a model that triggers errors — verify `error_id` appears in both log and JSONL.
3. Grep for `error_id` in the log — confirm it matches the JSONL row.
4. Verify `classify_error()` now correctly categorizes errors that were previously `"unknown"`.

---

## Out of scope

- Structured logging (JSON log format) — useful but a separate concern.
- Retry-level error tracking — `LLMExecutor` already tracks per-attempt results.
- Persisting error IDs to the database for cloud runs — can be added later via `TrackActivity`.
