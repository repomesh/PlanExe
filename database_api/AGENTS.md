# database_api agent instructions

Scope: this package defines shared SQLAlchemy models used by multiple services
(`frontend_multi_user`, `worker_plan_database`). Keep changes compatible across
consumers.

## Guidelines
- Use the shared `db` from `database_api/planexe_db_singleton.py`; do not create
  new `SQLAlchemy()` instances or engine/session objects here.
- Models must subclass `db.Model` and use `db.Column`/`db.Enum`/`db.relationship`
  to stay aligned with Flask-SQLAlchemy expectations.
- Favor backward-compatible schema changes: new columns should be nullable and
  have safe defaults; avoid renames/drops unless all consumers are updated.
- If a new model/column is added, update any dependent service bootstrap or
  migration helpers (e.g. `worker_plan_database/app.py` or
  `frontend_multi_user/src/app.py`) and related docs.
- Allowed imports: stdlib, `sqlalchemy`, `sqlalchemy_utils`, and
  `database_api.planexe_db_singleton`.
- Forbidden imports: `worker_plan*`, `frontend_*`, `worker_plan_database`
  (keep this package service-agnostic).
- Use UTC timestamps for defaults (`datetime.now(UTC)`), matching existing models.
- Foreign keys: current models do not define `ForeignKey` constraints. Confirm
  with the owner before adding any.
- Migrations: there is no Alembic pipeline here. Schema changes are applied via
  `db.create_all()` at service startup plus explicit ALTER helpers in
  `frontend_multi_user/src/app.py` and `worker_plan_database/app.py`. Update
  those helpers when adding columns that need backfill/ALTER.

## Example: adding a column
```python
# correct (backward compatible)
extra_notes = db.Column(db.String(256), nullable=True, default=None)

# incorrect (breaks existing rows)
extra_notes = db.Column(db.String(256), nullable=False)
```

## Shared helpers
- `is_machai_user.py`: determines if a `user_id` belongs to a MachAI iframe
  user (non-UUID, not in `UserAccount`, not the admin username). Used by both
  `frontend_multi_user` and `worker_plan_database` — keep this as the single
  source of truth for MachAI user detection. Must be called inside a Flask app
  context.

## Testing
- No package-level tests currently. If you change models or schema helpers,
  add a unit test under `database_api/tests` that exercises model import and
  `db.create_all()` with SQLite. Run tests in a venv that includes
  `flask-sqlalchemy` (see `frontend_multi_user/README.md`).
