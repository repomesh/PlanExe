# frontend_multi_user agent instructions

Scope: Flask-based multi-user UI with Postgres backing, admin UI, and queue
logic. Talks to `worker_plan` for execution and uses shared `database_api`
models. Keep interfaces stable across services.

## Guidelines
- Preserve the `worker_plan` API contract defined in `worker_plan/app.py`;
  update the UI calls if routes or response shapes change.
- Keep Postgres wiring and env defaults stable (see root `AGENTS.md` for keys);
  prefer `SQLALCHEMY_DATABASE_URI`, otherwise fall back to
  `PLANEXE_FRONTEND_MULTIUSER_DB_*` and `PLANEXE_POSTGRES_*`.
- Maintain required admin auth (`PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME`
  / `PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD`) and Flask login flow.
- Continue using `database_api.planexe_db_singleton.db`; do not create new
  SQLAlchemy engines or sessions here.
- Keep `.env` loading via `PlanExeDotEnv` and `update_os_environ()` early so
  local/debug behavior is consistent.
- If schema usage changes (e.g., new PlanItem columns), update the
  `_ensure_planitem_artifact_columns()` helper and keep changes backward
  compatible.
- Artifact storage model:
  - Use `PlanItem.run_activity_overview_json` as primary UI cost/usage source.
  - Keep `PlanItem.run_track_activity_jsonl` internal/admin-only.
  - User zip downloads should serve layout-versioned snapshots directly for
    new tasks; sanitize legacy snapshots only.
- Admin navbar UX invariant:
  - Keep the top-right corner behavior as a location-based toggle.
  - On `/`, users see `Admin Panel` in the top-right corner.
  - On `/admin`, keep `Dashboard` in that same top-right corner location, with
    `Logout` immediately to its left (`Logout`, then `Dashboard`).
- Do not store run state in module-level globals; fetch state from Postgres or
  `worker_plan` per request.
- Forbidden imports: `worker_plan_internal`, `worker_plan.app`,
  `frontend_single_user`, `open_dir_server`.

## Testing
- No automated tests currently. If you change UI or DB flow, add a unit test
  close to the logic when feasible and run `python test.py` from repo root.
