# Proposal: Address PGRES_TUPLES_OK Connection Corruption on Railway

**Author:** Simon Strandgaard + Claude
**Date:** 15 April 2026
**Status:** Draft
**Topic:** Database reliability, connection pool management

## 1. Problem

The `worker_plan_database` service on Railway intermittently encounters
`psycopg2.DatabaseError: error with status PGRES_TUPLES_OK and no message from the libpq`
errors. This is a psycopg2-level protocol corruption where the underlying TCP connection
is alive but the PostgreSQL wire protocol state is broken.

### Symptoms

- LLM calls complete successfully, but the subsequent `db.session.commit()` (for
  token metrics, progress updates, or heartbeat upserts) fails with `PGRES_TUPLES_OK`.
- The corrupted connection is returned to SQLAlchemy's connection pool.
- Other Luigi worker threads check out the bad connection; `pool_pre_ping` (`SELECT 1`)
  hangs on it because the protocol is broken but the TCP socket is still open.
- All 4 Luigi worker threads deadlock. The pipeline appears stuck at ~3% forever.
- `stop_requested` is ignored because the callback that checks it never fires.
- The worker replica is completely stuck until restarted.

### Affected code paths (patched so far)

| Location | Error handler |
|----------|--------------|
| `worker_plan_internal/llm_util/token_metrics_store.py` | `record_token_usage()` |
| `worker_plan_database/app.py` | `_handle_task_completion()` callback retries |
| `worker_plan_database/app.py` | `update_task_state_with_retry()` |
| `worker_plan_database/app.py` | `update_task_progress_with_retry()` |
| `worker_plan_database/app.py` | `_update_failure_diagnostics()` |
| `database_api/model_worker.py` | `upsert_heartbeat()` |

Each was patched with the same pattern: `db.session.rollback()` → `db.engine.dispose()`
→ `db.session.remove()`. This destroys the pool so the corrupted connection is closed
outright instead of being recycled.

### Current mitigation

```python
except Exception as e:
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        db.engine.dispose()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass
```

This works — the pipeline recovers and continues. But it is reactive (we add the
pattern each time a new code path surfaces) and `db.engine.dispose()` is heavy-handed
(closes all pooled connections, not just the bad one).

## 2. Root cause hypotheses

1. **Railway's TCP proxy** — Railway routes Postgres traffic through an internal proxy.
   The proxy may drop/corrupt packets under load or during container migrations without
   cleanly closing the TCP connection.

2. **Idle connection timeout** — Railway or the Postgres instance may silently close
   idle connections after a timeout. psycopg2 doesn't notice until the next operation,
   and the resulting error is `PGRES_TUPLES_OK` instead of a clean disconnect.

3. **Concurrent session/connection sharing** — Luigi runs 4 worker threads. If
   Flask-SQLAlchemy's scoped session or the connection pool has a threading edge case,
   two threads could interleave operations on the same raw connection, corrupting the
   protocol state.

4. **psycopg2 bug** — There are known issues with `PGRES_TUPLES_OK` in psycopg2 when
   the connection is in an unexpected state. psycopg3 (aka `psycopg`) has a different
   connection architecture that may not be affected.

## 3. Proposed solutions

### Option A: Global SQLAlchemy error handler (recommended short-term)

Register an engine-level event that intercepts all `PGRES_TUPLES_OK` errors and
invalidates the specific connection, preventing it from re-entering the pool. This
replaces all per-site patches with a single handler.

```python
from sqlalchemy import event

@event.listens_for(db.engine, "handle_error")
def _handle_pgres_error(context):
    """Invalidate connections corrupted by PGRES_TUPLES_OK."""
    orig = getattr(context, "original_exception", None)
    if orig and "PGRES_TUPLES_OK" in str(orig):
        context.invalidate_pool_on_disconnect = True
        logger.warning("PGRES_TUPLES_OK detected — invalidating connection.")
```

**Pros:** Single point of fix, no per-site patching, only invalidates the bad
connection (not the entire pool).
**Cons:** Requires testing that `invalidate_pool_on_disconnect` works correctly
for this error type (it was designed for disconnect errors).

### Option B: Migrate to psycopg3

Replace `psycopg2` with `psycopg` (psycopg3). The newer driver has:
- Native async support
- Better connection state tracking
- Automatic connection recovery
- No `PGRES_TUPLES_OK` corruption issues (different C binding)

**Pros:** Eliminates the root cause at the driver level.
**Cons:** Requires dependency changes, potential API differences, testing across
all services.

### Option C: Connection pooler (PgBouncer)

Deploy PgBouncer between the worker and PostgreSQL. PgBouncer manages connections
at the protocol level, handles reconnection transparently, and isolates the
application from transport-layer issues.

**Pros:** Handles all connection lifecycle issues, reduces connection count to
Postgres, industry standard.
**Cons:** Additional infrastructure to deploy and maintain on Railway, adds
latency, transaction-mode pooling requires careful session management.

### Option D: Aggressive pool configuration

Tune SQLAlchemy pool settings to reduce exposure to stale connections:

```python
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 60,        # recycle connections every 60s (currently 280)
    'pool_pre_ping': True,     # already enabled
    'pool_size': 5,
    'max_overflow': 2,
    'pool_timeout': 10,        # fail fast instead of waiting
}
```

**Pros:** Simple configuration change, no code changes.
**Cons:** Doesn't prevent the corruption — just reduces the window. More
frequent reconnections add overhead.

## 4. Recommendation

**Short-term (now):** Implement Option A (global error handler). This replaces
the scattered per-site patches with a single, centralized handler and is the
lowest-risk change.

**Medium-term:** Investigate Option B (psycopg3 migration). If PGRES_TUPLES_OK
continues to occur frequently, the driver-level fix is the most robust solution.

**Long-term:** Consider Option C (PgBouncer) if the Railway Postgres proxy
continues to be unreliable, especially as the service scales to more worker
replicas.

## 5. References

- [psycopg2 PGRES_TUPLES_OK issue](https://github.com/psycopg/psycopg2/issues)
- [SQLAlchemy handle_error event](https://docs.sqlalchemy.org/en/20/core/events.html#sqlalchemy.events.ConnectionEvents.handle_error)
- [SQLAlchemy dealing with disconnects](https://docs.sqlalchemy.org/en/20/core/pooling.html#dealing-with-disconnects)
- PRs: #573, #574, #578
