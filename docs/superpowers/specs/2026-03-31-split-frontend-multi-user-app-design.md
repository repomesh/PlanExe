# Design: Split frontend_multi_user/src/app.py into Blueprint modules

**Date:** 2026-03-31
**Status:** Proposed
**Implements:** Proposal 131, Phase 2, Step 1

## Goal

Split the 3,857-line monolithic `MyFlaskApp` class in `frontend_multi_user/src/app.py` into focused Flask Blueprint modules. Preserve all behavior, routes, and the AGENTS.md constraints.

## Module layout

```
frontend_multi_user/src/
  app.py              # Assembly: Flask app creation, config, db init, schema migrations, middleware, blueprints
  auth.py             # Blueprint "auth": OAuth, login/logout, session
  billing.py          # Blueprint "billing": Stripe & Telegram payments, credit helpers
  admin_routes.py     # Blueprint "admin_routes": admin panel, database utils, reconciliation, demo_run
  plan_routes.py      # Blueprint "plan_routes": /run, /plan/*, progress, telemetry, stop/retry/resume
  downloads.py        # Blueprint "downloads": /plan/download/*, /admin/task/<id>/* file serving
  utils.py            # Pure helpers shared across blueprints
```

## Per-module contents

### app.py (assembly, ~700 lines target)

Keeps:
- All imports, module-level constants (`RUN_DIR`, `SHOW_DEMO_PLAN`, `CREDIT_SCALE`, `DEMO_FORM_RUN_PROMPT_UUIDS`, `AUTH_PROVIDER_LABELS`)
- `MyFlaskApp` class with `__init__` (Flask creation, config, dotenv, db init, schema migrations, Flask-Admin registration, OAuth setup)
- Middleware: `_auto_login_open_access`, `_admin_full_width`, `inject_current_user_name`
- App-level routes: `/` (dashboard), `/models`, `/healthcheck`, `/llms.txt`, `/llm.txt`, `/ping`
- Startup helpers: `_track_flask_app_started`, `_start_check`, `_fetch_worker_plan_llm_info`, `_looks_like_production_url`, `_register_oauth_providers`, `_determine_open_access`
- Schema migration helpers (`_ensure_*`, `_create_tables_with_retry`, `_seed_initial_records`)
- Flask-Admin setup and `MyAdminIndexView`
- `User` class (Flask-Login), `login_manager.user_loader`
- `_profile_model_rows_map()`, `_model_profile_options()` (used by dashboard and models route)
- Blueprint registration: imports and registers all blueprints
- `__main__` block
- `nocache` decorator, `admin_required` decorator
- `_new_model`, `build_postgres_uri_from_env`

Stashes into `app.config` during init:
- `PLANEXE_RUN_DIR` (path)
- `WORKER_PLAN_URL` (string)
- `PLANEXE_PROJECT_ROOT` (path)
- `PATH_TO_PYTHON` (path)
- `PROMPT_CATALOG` (PromptCatalog instance)
- `PLANEXE_CONFIG` (PlanExeConfig instance)
- `PLANEXE_DOTENV` (PlanExeDotEnv instance)
- `OPEN_ACCESS` (bool)
- `API_KEY_SHOW_ONCE` (bool)
- `PLAN_TELEMETRY_CACHE` (dict reference)

### utils.py (~120 lines)

Pure functions with no Flask or db dependency:
- `_safe_float(value)`
- `_safe_int(value)`
- `_clean_text(value)`
- `_extract_exception_type(message)`
- `_extract_nested_value(payload, key_names)`
- `_extract_provider_model_from_activity_key(model_key)`
- `_to_credit_decimal(value)` (uses CREDIT_SCALE constant, passed or imported)
- `_format_credit_display(value)`
- `_format_relative_time(value)`
- `_normalize_plan_view_mode(value)`
- `_coerce_json_dict(value)`

Also exports `CREDIT_SCALE` constant.

### auth.py (~200 lines)

Blueprint name: `auth`, no url_prefix.

Routes:
- `/login` (GET, POST)
- `/api/oauth-redirect-uri` (GET)
- `/login/<provider>` (GET)
- `/auth/<provider>/callback` (GET)
- `/logout` (GET)

Helpers (moved from MyFlaskApp):
- `_oauth_redirect_url(provider)` — reads `current_app.config['PUBLIC_BASE_URL']`
- `_auth_provider_label(provider)`
- `_get_user_from_provider(provider, token)`
- `_avatar_url_from_profile(provider, profile)`
- `_upsert_user_from_oauth(provider, profile)`
- `_update_user_from_profile(user, provider, profile)`
- `_get_or_create_api_key(user, name)`

Accesses: `current_app.config`, `current_app.extensions['authlib.integrations.flask_client']` (OAuth), `database_api` db singleton, Flask-Login `login_user`/`logout_user`.

### billing.py (~250 lines)

Blueprint name: `billing`, url_prefix `/billing`.

Routes:
- `/stripe/checkout` (POST)
- `/stripe/webhook` (POST)
- `/telegram/invoice` (POST)
- `/telegram/webhook` (POST)

Helpers:
- `_apply_credit_delta(user, delta, reason, source, external_id)`
- `_apply_payment_credits(user_id, provider, provider_payment_id, credits, amount, currency, raw_payload)`
- `_record_event(event_type, message, context)`
- `_finalize_stripe_checkout_session(user, checkout_session_id)`

Accesses: `current_app.config`, `stripe` library, db singleton, CreditHistory/PaymentRecord/EventItem models.

### admin_routes.py (~300 lines)

Blueprint name: `admin_routes`, no url_prefix.

Routes:
- `/admin/reconciliation` (GET)
- `/admin/database` (GET, POST)
- `/admin/database/backup` (GET)
- `/ping/stream` (GET)
- `/demo_run` (GET)

Helpers:
- `_get_database_size_info()`
- `_get_purge_activity_info()`
- `_purge_activity_data(keep_n)`
- `_vacuum_task_item()`
- `_proxy_backup_response()`
- `_build_reconciliation_report(max_tasks, tolerance_usd)`

Uses `admin_required` decorator imported from `app.py`.

### plan_routes.py (~800 lines)

Blueprint name: `plan_routes`, no url_prefix.

Routes:
- `/run` (GET, POST)
- `/create_plan` (POST)
- `/run_status` (GET)
- `/progress` (GET)
- `/viewplan` (GET)
- `/plan` (GET)
- `/plan/stop` (POST)
- `/plan/retry` (POST)
- `/plan/resume` (POST)
- `/plan/meta` (GET)
- `/plan/view-mode` (POST)
- `/plan/telemetry` (GET)

Helpers:
- `_get_current_user_account()` — shared with account, but primary user is plan_routes; import from here or utils
- `_get_plan_view_mode_preference()`, `_set_plan_view_mode_preference(mode)`
- `_admin_user_ids()` — used by plan list filtering; shared with admin
- `_load_prompt_preview_safe(task_id, max_chars)`
- `_build_plan_failure_trace(task)`
- `_build_plan_telemetry_cache_key(task, include_raw)`
- `_build_plan_telemetry(task, include_raw, expose_raw_usage_data)`
- `_read_activity_overview_from_task(task)`
- `_read_inference_cost_from_task(task)`
- `_find_latest_task_event(task_id, event_type, max_events_to_scan)`
- `_read_activity_overview_from_run_zip(run_zip_snapshot)`
- `_read_inference_cost_from_run_zip(run_zip_snapshot)`

`_get_current_user_account()` and `_admin_user_ids()` are also needed by `app.py` (dashboard) and `account.py`. These go in `utils.py` or a small `user_helpers.py` — but to keep module count low, put them in `plan_routes.py` and import from there where needed.

### downloads.py (~150 lines)

Blueprint name: `downloads`, no url_prefix.

Routes:
- `/plan/download/report` (GET)
- `/plan/download/zip` (GET)
- `/admin/task/<uuid:task_id>/report` (GET)
- `/admin/task/<uuid:task_id>/run_zip` (GET)
- `/admin/task/<uuid:task_id>/track_activity` (GET)

Helpers:
- `_sanitize_legacy_run_zip_for_download(run_zip_snapshot)`

Uses `admin_required` from `app.py`, `nocache` from `app.py`.

## Shared state strategy

The `MyFlaskApp.__init__` stashes all instance state that blueprints need into `app.config`:

```python
self.app.config['WORKER_PLAN_URL'] = self.worker_plan_url
self.app.config['PLANEXE_RUN_DIR'] = self.planexe_run_dir
# etc.
```

Blueprint code accesses via `current_app.config['WORKER_PLAN_URL']`.

The telemetry cache dict is stashed the same way: `self.app.config['PLAN_TELEMETRY_CACHE'] = self._plan_telemetry_cache`.

## Blueprint registration

In `MyFlaskApp.__init__`, after all setup:

```python
from frontend_multi_user.src.auth import auth_bp
from frontend_multi_user.src.billing import billing_bp
from frontend_multi_user.src.admin_routes import admin_routes_bp
from frontend_multi_user.src.plan_routes import plan_routes_bp
from frontend_multi_user.src.downloads import downloads_bp

self.app.register_blueprint(auth_bp)
self.app.register_blueprint(billing_bp)
self.app.register_blueprint(admin_routes_bp)
self.app.register_blueprint(plan_routes_bp)
self.app.register_blueprint(downloads_bp)
```

## Constraints preserved

- Single `db` singleton from `database_api.planexe_db_singleton` (AGENTS.md rule)
- No imports from `worker_plan_internal`, `worker_plan.app`
- Admin identity via Flask-Login username string + deterministic UUID
- Schema migration helpers stay in `app.py` (run once at startup)
- Flask-Admin registration stays in `app.py`
- No new dependencies

## Testing strategy

- No automated tests exist currently for this frontend
- Verification: start the app, confirm all routes respond (manual smoke test)
- Run `python test.py` from repo root to confirm no regressions in other packages

## Success criteria

- `app.py` reduced from ~3,857 lines to ~700 lines
- Each new module under ~800 lines
- All existing routes return identical responses
- No new files beyond the 6 listed above
