# Frontend Multi-User Developer Guide

How `frontend_multi_user` works — page structure, authentication states, nav bar behavior, and route map.

## Template Hierarchy

All pages extend `base.html`, which provides the site header (nav bar), main content area, and footer.

```
base.html
├── index.html          Home / dashboard
├── login.html          Sign-in page (admin + OAuth providers)
├── account.html        API keys, credits, billing
├── plan_list.html      "Plans" page — list of user's plans
├── plan_iframe.html    Single plan detail (report viewer)
├── models.html         Model profile browser
├── run_via_database.html  "Start New Plan" form
├── demo_run.html       Quick demo form (no login needed in open-access mode)
├── check_is_working.html  /healthcheck diagnostic
└── ping.html           SSE connectivity test
```

## Authentication States

The app has three user states. Every template receives `current_user_name` and `current_user` via the `inject_current_user_name` context processor (defined in `app.py`).

| State | `current_user_name` | `current_user.is_admin` | How it's set |
|-------|---------------------|------------------------|-------------|
| **Logged out** | `None` | N/A | Not authenticated |
| **Admin** | `"Admin"` | `True` | Username/password login via `PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME/PASSWORD` env vars |
| **OAuth user** | Full name (e.g. `"Simon Strandgaard"`) | `False` | OAuth via Google, GitHub, Discord, or Telegram |

The context processor resolves the display name from the `UserAccount` model in this priority: `name` > `given_name` > `email` > `"Account"`.

## Nav Bar Behavior

The nav bar in `base.html` adapts to the authentication state:

**Admin user:**
```
[PlanExe Home]  Plans  Models  ···spacer···  Account  [Admin Panel]
```
- "Account" links to `/account` (API keys, credits, billing)
- "Admin Panel" is a styled button linking to the Flask-Admin panel

**OAuth user:**
```
[PlanExe Home]  Plans  Models  ···spacer···  Simon Strandgaard
```
- The user's full name links to `/account`
- No admin panel button

**Logged out:**
```
[PlanExe Home]  ···spacer···  About  [Sign In]
```
- "Plans" and "Models" links are hidden
- "About" links to planexe.org
- "Sign In" is a styled button linking to `/login`

The active page is highlighted with an underline (`nav-active` class) using `request.endpoint` checks.

## Key Routes

### Public (no login required)
| Route | Purpose |
|-------|---------|
| `/` | Home page — landing for logged-out users, dashboard for logged-in users |
| `/login` | Sign-in form (admin credentials + OAuth provider buttons) |
| `/login/<provider>` | Initiates OAuth flow for the given provider |
| `/auth/<provider>/callback` | OAuth callback handler |
| `/healthcheck` | Returns JSON status — used by Railway health checks |
| `/llms.txt`, `/llm.txt` | Machine-readable site description |

### Authenticated (login required)
| Route | Purpose |
|-------|---------|
| `/account` | API key management, credit balance, billing actions |
| `/models` | Browse available model profiles |
| `/plan` | Plan list (no `?id=`) or plan detail (with `?id=<uuid>`) |
| `/plan/download/report` | Download HTML report for a plan |
| `/plan/download/zip` | Download zip bundle for a plan |
| `/plan/stop` | POST — stop a running plan |
| `/plan/retry` | POST — retry a failed plan |
| `/create_plan` | POST — start a new plan from the dashboard |
| `/run` | Legacy "Start New Plan" form |
| `/logout` | Ends the session |

### Admin only
| Route | Purpose |
|-------|---------|
| `/admin/...` | Flask-Admin panel (user management, plan inspection) |
| `/admin/reconciliation` | Credit reconciliation report |
| `/admin/task/<id>/report` | Direct report access by task ID |

### Billing
| Route | Purpose |
|-------|---------|
| `/billing/stripe/checkout` | POST — create Stripe checkout session |
| `/billing/stripe/webhook` | POST — Stripe webhook receiver |
| `/billing/telegram/invoice` | POST — create Telegram Stars invoice |
| `/billing/telegram/webhook` | POST — Telegram payment webhook |

## Account Page

The `/account` page shows the full API key management UI for both admin and OAuth users. Admin users see API keys but not billing (credits, payments); OAuth users see everything.

Admin gets a `UserAccount` row via `_get_current_user_account()`, which creates one on first visit using a deterministic UUID (`uuid5` of the admin username). This lets admin own API keys in the same table as OAuth users.

### POST Actions

The `/account` route handles POST actions via a hidden `action` form field:

- `create_api_key` — Create a new API key (with optional name), max 10 active keys
- `rename_api_key` — Update the name on an existing key (click-to-edit UI with Save/Cancel)
- `reset_api_key` — Rotate the secret on an existing key (new hash + prefix, same UUID so name/stats are preserved)
- `revoke_api_key` — Soft-delete an API key by setting `revoked_at`
- `regenerate_api_key` — Legacy action kept for backward compatibility
- `change_name` — Update display name
- `change_email` — Update email
- `delete_data` — Delete all user data (plans, keys, account)

### Key Table UI

Each key row has a three-dot overflow menu with "Reset secret" and "Delete". The name column uses a click-to-edit pattern: plain text with a pencil icon on hover, expanding to an edit form showing the old name, an input, Save, and Cancel (Escape key also cancels).

## Billing and Per-Key Stats

Credits Used and Plans count on the account page come from `CreditHistory` and `PlanItem` rows filtered by `api_key_id`. For these stats to work, both fields must be set when creating a plan:

1. **`PlanItem.user_id`** must be a valid `UserAccount` UUID. The worker billing function (`_charge_usage_credits_once` in `worker_plan_database/app.py`) parses it via `uuid.UUID()` — a plain string like `"admin"` fails and billing is silently skipped.

2. **`PlanItem.api_key_id`** must match an active `UserApiKey.id`. The billing copies this to `CreditHistory.api_key_id`. If NULL, the ledger entry won't appear in per-key stats.

### Plan creation paths

| Path | `user_id` | `api_key_id` | Billing works? |
|------|-----------|-------------|---------------|
| Frontend `/create_plan` | Admin's UserAccount UUID | First active key | Yes |
| Frontend `/run` (legacy) | Admin's UserAccount UUID | Not set | Partial (billing works, per-key stats don't) |
| MCP with `user_api_key` | Resolved from key | Resolved from key | Yes |
| MCP without `user_api_key` | `"admin"` (string) | NULL | No |

For local MCP development, pass `user_api_key` in `plan_create` calls to enable credit tracking.

### Incremental billing

Credits are charged during plan execution, not just at completion. The worker calls `_charge_incremental_usage()` on each progress heartbeat, reading the current `activity_overview.json` and creating `CreditHistory` entries with `source="usage_billing_progress"`. When the plan finishes, `_charge_usage_credits_once()` subtracts what was already charged incrementally and creates a final `source="usage_billing"` entry for the remainder plus the success fee.

This prevents abuse where a user starts many plans and aborts them at the last minute to avoid charges. The account page's Credits Used column sums all `CreditHistory` entries with `delta < 0`, so both incremental and final entries are included.

### Admin backward compatibility

Old plans have `user_id="admin"` (string). The `_admin_user_ids()` helper returns both the old username and the new UUID, so dashboard and plan list queries find all admin plans.

## Database Migrations

Schema migrations run at startup using `ALTER TABLE ADD COLUMN IF NOT EXISTS` statements. This pattern is:
- **Idempotent** — safe to run from multiple services simultaneously
- **Non-blocking** — PostgreSQL `ADD COLUMN` without a default doesn't lock the table
- **Backward compatible** — new columns are always nullable

Index creation uses `CREATE INDEX IF NOT EXISTS`. PostgreSQL has a known race condition where concurrent sessions issuing the same `CREATE INDEX IF NOT EXISTS` can throw a `UniqueViolation` on `pg_class_relname_nsp_index`. Each index creation statement must be wrapped in its own try/except to handle this gracefully when multiple gunicorn workers start simultaneously.

Migration functions are called inside `_create_tables_with_retry()` during app initialization.

## Session and Login

- **Admin login**: Flask-Login with a hardcoded `AdminUser` object. Credentials come from env vars. A `UserAccount` row is lazily created (deterministic UUID) so admin can own API keys.
- **OAuth login**: Flask-Login with UUID-based user IDs from the `UserAccount` table. OAuth state/tokens are stored in Flask's encrypted session cookie.
- **Session secret**: `SECRET_KEY` env var. Must be the same across all replicas for sessions to work in a multi-replica deployment.

## API Key Secret Visibility

Controlled by `PLANEXE_API_KEY_SHOW_ONCE`:

| Value | Behavior |
|-------|----------|
| unset / `false` (default) | The full secret is stored in `key_plaintext` and always visible in the account table with a copy button. |
| `true` / `1` / `yes` | The secret is shown once after creation/reset, then only the prefix is displayed. Suitable for production with many users. |

When show-once is off, both `create_api_key` and `reset_api_key` persist the raw key so users can copy it at any time.

## Open Access Mode

When `PLANEXE_FRONTEND_MULTIUSER_OPEN_ACCESS=true`, certain pages (like `/demo_run`) are accessible without login. The `open_access` flag is injected into all templates by the context processor.
