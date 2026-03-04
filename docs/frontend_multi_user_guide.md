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

## Account Page Actions

The `/account` route handles several POST actions via a hidden `action` form field:

- `create_api_key` — Create a new API key (with optional label), max 10 active keys
- `revoke_api_key` — Soft-delete an API key by setting `revoked_at`
- `regenerate_api_key` — Legacy action kept for backward compatibility
- `change_name` — Update display name
- `change_email` — Update email
- `delete_data` — Delete all user data (plans, keys, account)

## Database Migrations

Schema migrations run at startup using `ALTER TABLE ADD COLUMN IF NOT EXISTS` statements. This pattern is:
- **Idempotent** — safe to run from multiple services simultaneously
- **Non-blocking** — PostgreSQL `ADD COLUMN` without a default doesn't lock the table
- **Backward compatible** — new columns are always nullable

Migration functions are called inside `_create_tables_with_retry()` during app initialization.

## Session and Login

- **Admin login**: Flask-Login with a hardcoded `AdminUser` object (not stored in DB). Credentials come from env vars.
- **OAuth login**: Flask-Login with UUID-based user IDs from the `UserAccount` table. OAuth state/tokens are stored in Flask's encrypted session cookie.
- **Session secret**: `SECRET_KEY` env var. Must be the same across all replicas for sessions to work in a multi-replica deployment.

## Open Access Mode

When `PLANEXE_FRONTEND_MULTIUSER_OPEN_ACCESS=true`, certain pages (like `/demo_run`) are accessible without login. The `open_access` flag is injected into all templates by the context processor.
