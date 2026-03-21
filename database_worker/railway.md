# Railway Configuration for `database_worker`

Deploy database_worker (PlanExe database maintenance service) to Railway as an internal HTTP service.

This service provides database backup (via `pg_dump`) and is called by `frontend_multi_user`. It should **not** be exposed publicly.

## Service variables example

```
PLANEXE_POSTGRES_HOST="${{shared.PLANEXE_POSTGRES_HOST}}"
PLANEXE_POSTGRES_PORT="5432"
PLANEXE_POSTGRES_DB="planexe"
PLANEXE_POSTGRES_USER="planexe"
PLANEXE_POSTGRES_PASSWORD="${{shared.PLANEXE_POSTGRES_PASSWORD}}"
PLANEXE_DATABASE_WORKER_API_KEY="${{shared.PLANEXE_DATABASE_WORKER_API_KEY}}"
```

## Required Environment Variables

- `PLANEXE_POSTGRES_HOST` — Postgres host. On Railway, use the internal hostname (e.g. `postgres.railway.internal`). The Docker Compose default `database_postgres` does not resolve on Railway.
- `PLANEXE_POSTGRES_PASSWORD` — Postgres password.

## Optional Environment Variables

- `PLANEXE_DATABASE_WORKER_API_KEY` — If set, the `/backup` endpoint requires this key in the `X-Database-Worker-Key` header. Should match the same variable on `frontend_multi_user`.
- `PLANEXE_DATABASE_WORKER_PORT` — Port to listen on (default: `8002`). On Railway, the auto-injected `PORT` is not used since this is an internal service.

## Networking

This service is **internal only** — do not assign a public domain. The `frontend_multi_user` service calls it via Railway's private networking:

```
PLANEXE_DATABASE_WORKER_URL="http://databaseworker.railway.internal:8002"
```

Set this variable on the `frontend_multi_user` service.

## Endpoints

- `GET /healthcheck` — returns `ok` (used by Railway health checks)
- `GET /backup` — streams a gzipped `pg_dump` of the database. Protected by `PLANEXE_DATABASE_WORKER_API_KEY` if configured.

## Volume — None

The service is stateless. Backups are streamed directly to the caller without writing to disk.
