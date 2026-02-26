---

## title: MCP Interface — Evaluation and Roadmap
date: 2026-02-26

# MCP Interface — Evaluation and Roadmap

An honest audit of the current MCP surface (`mcp_cloud` + `mcp_local`), followed by concrete improvements and promotion ideas.

**Revision history:**
- **2026-02-26 (rev 1):** Initial version after `task_*` → `plan_*` rename.
- **2026-02-26 (rev 2):** Updated after `app.py` refactor into modules, `plan_list` `user_api_key` made optional in schema (auto-injected by HTTP layer), and re-evaluation of all open issues.
- **2026-02-26 (rev 3):** Updated after completing 4.9 — all stale `task` variable names, request classes, helper functions, and backward-compat aliases renamed/removed across `mcp_cloud` and `mcp_local`. Test files renamed from `test_task_*` to `test_plan_*`.
- **2026-02-26 (rev 4):** Updated after completing 4.2 — added separate download rate limiter with configurable limits (default 10 req/60s).

---

## 1. Current Tool Surface

Nine tools, split across two transports:


| Tool              | Cloud (`mcp_cloud`) | Local (`mcp_local`) | Auth     | Annotations             |
| ----------------- | ------------------- | ------------------- | -------- | ----------------------- |
| `prompt_examples` | yes                 | yes                 | Public   | readOnly, idempotent    |
| `model_profiles`  | yes                 | yes                 | Public   | readOnly, idempotent    |
| `plan_create`     | yes                 | yes                 | Required | openWorld               |
| `plan_status`     | yes                 | yes                 | Required | readOnly, idempotent    |
| `plan_stop`       | yes                 | yes                 | Required | destructive, idempotent |
| `plan_retry`      | yes                 | yes                 | Required | openWorld               |
| `plan_file_info`  | yes                 | —                   | Required | readOnly, idempotent    |
| `plan_download`   | —                   | yes                 | Required | openWorld               |
| `plan_list`       | yes                 | yes                 | Required | readOnly, idempotent    |


`plan_download` is a local-only synthetic tool that internally proxies to `plan_file_info` on the cloud, then downloads and saves the artifact to the user's filesystem. This intentional asymmetry is tested in `test_tool_surface_consistency.py`.

**Auth model for `plan_create` and `plan_list`:** Both tools accept an optional `user_api_key` in the visible MCP input schema. When called over HTTP, the middleware authenticates the caller via the `X-API-Key` header and auto-injects `user_api_key` into handler arguments. This means MCP clients never need to pass `user_api_key` explicitly — the key is invisible in the tool's published schema but enforced at runtime. Both handlers return `USER_API_KEY_REQUIRED` if no key arrives by either path.

---

## 2. What's Working Well

**Dual transport.** `mcp_cloud` (stateless HTTP / Railway) and `mcp_local` (stdio proxy) cover the two major deployment patterns. Most users can pick one without reading source code.

**Clean module structure.** `mcp_cloud/app.py` is now a thin re-export facade (~195 lines). Logic lives in focused modules: `handlers.py` (tool handlers), `schemas.py` (tool definitions), `tool_models.py` (Pydantic models), `db_queries.py` (DB operations), `auth.py` (key hashing/user resolution), `download_tokens.py` (signed tokens), `model_profiles.py`, `worker_fetchers.py`, `zip_utils.py`, `prompt_examples.py`. This makes PRs reviewable and bugs easy to isolate.

**Consistent `plan_*` naming throughout.** The rename from `task_*` to `plan_*` covers the full stack: external tool names, handler functions, request classes (`PlanCreateRequest`, etc.), DB query helpers (`_create_plan_sync`, `get_plan_by_id`, etc.), local variable names, and test file names. No backward-compat aliases remain.

**Layered authentication.** Two distinct auth paths — a server-wide `PLANEXE_MCP_API_KEY` for self-hosters, and per-user `pex_…` keys issued by home.planexe.org — are a good design. The key-normalisation helper (`_normalize_api_key_value` in `http_server.py`) handles common copy-paste artefacts (Bearer prefix, surrounding quotes, full header line pasted as value).

**Auto-injected `user_api_key`.** For `plan_create` and `plan_list`, the HTTP layer reads the authenticated user from the request context and injects `user_api_key` into handler arguments automatically. Callers never see `user_api_key` as a required field in the MCP schema — a clean separation between transport-level auth and tool-level logic.

**Structured output schemas.** Every tool declares an `output_schema`, so MCP clients can validate responses without guessing. `TestAllToolsHaveOutputSchema` enforces this at CI time.

**Tool annotations.** `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` are set on every tool and tested. This is ahead of most MCP servers.

**`plan_retry` with model_profile selection.** Allowing the caller to re-run a failed task with a stronger model (e.g. upgrade from `baseline` to `premium`) at retry time is genuinely useful.

**Signed download tokens.** `plan_file_info` returns download URLs with HMAC-SHA256 signed, time-limited tokens (15-min default TTL) scoped to one artifact (`task_id:filename:expiry`). Tokens work in a browser without an API key header. Defence-in-depth: the download endpoint re-validates even after middleware has passed the token. The secret fallback chain is: `PLANEXE_DOWNLOAD_TOKEN_SECRET` → `PLANEXE_API_KEY_SECRET` → per-process random (with warning).

**Glama + llms.txt.** Being listed in the Glama registry and providing `llms.txt` lowers the discovery barrier for new users.

**Rate limiting on all MCP endpoints.** `_enforce_rate_limit` in `http_server.py` applies to `/mcp`, `/mcp/`, and `/mcp/tools/call`. The default limit (60 req / 60 s per client, keyed by API key or IP) is high enough that normal `plan_status` polling is never affected.

**Prompt guidance in schema.** The `prompt` field description ("300–800 words … objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria") sets user expectations up front.

**`plan_list` for task recovery.** Authenticated users can list their most recent tasks (up to 50, newest-first) to recover a lost `task_id`. Each entry includes `task_id`, `state`, `progress_percentage`, `created_at`, and `prompt_excerpt`.

**Comprehensive test suite.** 12 test files covering tool surface consistency, auth key parsing, CORS config, download tokens, HTTP routing, and individual tool behaviour (`test_plan_create_tool.py`, `test_plan_status_tool.py`, `test_plan_retry_tool.py`, `test_plan_file_info_tool.py`, `test_model_profiles_tool.py`).

---

## 3. What's Been Fixed (Previously Reported)

### 3.1 ~~`skills/planexe-mcp/SKILL.md` says "5 tools"~~ (FIXED)

Updated to nine tools; SKILL.md now lists all tools with example JSON-RPC calls.

### 3.2 ~~Trailing-slash inconsistency~~ (FIXED)

The canonical URL (`https://mcp.planexe.org/mcp`, no trailing slash) is used in all JSON config files and registry entries.

### 3.3 ~~`speed_vs_detail` documented but hidden from agents~~ (FIXED)

Removed entirely from the MCP interface.

### 3.4 ~~`plan_file_info` returns `{}` on success instead of `isError`~~ (FIXED)

Now returns `{"ready": false, "reason": "processing"}` while running and `{"ready": false, "reason": "failed", "error": {...}}` on failure.

### 3.5 ~~Rate limiting covers REST but not Streamable HTTP `/mcp`~~ (FIXED)

`_enforce_rate_limit` now covers `/mcp`, `/mcp/`, and `/mcp/tools/call`.

### 3.6 ~~No `plan_list` tool — lost `task_id` = lost task~~ (FIXED)

Added `plan_list` to both `mcp_cloud` and `mcp_local`. Returns up to 50 tasks newest-first.

### 3.7 ~~Signed, expiring download tokens~~ (FIXED)

HMAC-SHA256 tokens, 15-minute default TTL, scoped per-artifact.

### 3.8 ~~Tools used `task_*` prefix instead of `plan_*`~~ (FIXED)

All external tool names renamed to `plan_*`.

### 3.9 ~~`app.py` is a 76 KB monolith~~ (FIXED)

Refactored into 10+ focused modules (commit 9f1a7db9). `app.py` is now a thin re-export facade.

### 3.10 ~~`plan_list` requires `user_api_key` in visible MCP schema~~ (FIXED)

`user_api_key` is now optional in the `PlanListInput` schema (not in `required` list), matching `plan_create`. The HTTP layer auto-injects it from the `X-API-Key` header via `_get_authenticated_user_api_key()`. The handler still enforces the key at runtime (returns `USER_API_KEY_REQUIRED` if absent).

---

## 4. What's Broken or Inconsistent

### 4.1 Dev-secret fallback in production

`_hash_user_api_key` in `auth.py` falls back to a hardcoded `"dev-api-key-secret"` when `PLANEXE_API_KEY_SECRET` is unset (line 14). A warning is logged, but the server continues. In production this means all user keys hash with a known default, which is a security risk.

Similarly, `_get_download_token_secret` in `download_tokens.py` falls back to a random per-process secret (line 86–93). This means download tokens expire on server restart and are invalid across processes in a distributed setup.

**Fix:** Fail hard at startup if these secrets are not set when `PLANEXE_MCP_REQUIRE_AUTH` is true (i.e. production mode).

### ~~4.2 `/download` endpoint not rate-limited~~ (FIXED)

A separate download rate limiter (`_enforce_download_rate_limit`) now covers `/download` paths with its own bucket and configurable limits: `PLANEXE_MCP_DOWNLOAD_RATE_LIMIT` (default 10 req) and `PLANEXE_MCP_DOWNLOAD_RATE_WINDOW_SECONDS` (default 60s). This is deliberately tighter than the MCP rate limit (60 req/60s) since download responses are 700KB–6MB. The sweep task cleans up download buckets alongside MCP buckets.

### ~~4.3 Body size validation only on REST endpoint~~ (FIXED)

`_enforce_body_size` now checks both `/mcp/tools/call` and `/mcp/` POST requests. The `Content-Length` requirement (411) is only enforced on the REST endpoint since Streamable HTTP may use chunked encoding without `Content-Length`; however, when `Content-Length` is present on either endpoint it is validated against `MAX_BODY_BYTES`.

### ~~4.4 `plan_file_info` silently defaults invalid artifact to `"report"`~~ (FIXED)

Both `handle_plan_file_info` (cloud) and `handle_plan_download` (local) now return `INVALID_ARGUMENT` with a descriptive message when the artifact value is not `"report"` or `"zip"`.

### ~~4.5 No dedicated `plan_list` test~~ (FIXED)

Added `mcp_cloud/tests/test_plan_list_tool.py` with 8 tests covering: tool listed, returns tasks, empty result, limit clamping (both directions), invalid API key, `USER_API_KEY_REQUIRED` when env requires key, no-key passthrough when not required (user_id=None), and default limit.

### 4.6 CORS default is wildcard

`PLANEXE_MCP_CORS_ORIGINS` defaults to `["*"]` when unset (`http_server.py:139–143`). The comment says "API-key auth is the primary access control", but wildcard CORS exposes all endpoints to any origin.

**Fix:** Default to a restrictive origin list (e.g. `["https://mcp.planexe.org", "https://home.planexe.org"]`) and document the `PLANEXE_MCP_CORS_ORIGINS` override in the README.

### ~~4.7 No request logging for successful tool calls~~ (FIXED)

`handle_call_tool` now logs every tool call at INFO level with tool name, result (ok/error/exception), and duration in milliseconds. Unknown tools are logged at WARNING. Format: `tool_call tool=<name> result=<ok|error|exception> duration_ms=<N>`.

### ~~4.8 Prompt excerpt length hardcoded~~ (FIXED)

Extracted to `PROMPT_EXCERPT_MAX_LENGTH = 100` at module level in `db_queries.py`.

### ~~4.9 Stale `task` variable names and backward-compat aliases~~ (FIXED)

All internal naming now uses `plan` consistently. Request classes renamed (`TaskCreateRequest` → `PlanCreateRequest`, etc.), DB query helpers renamed (`_create_task_sync` → `_create_plan_sync`, `get_task_by_id` → `get_plan_by_id`, etc.), local variables renamed (`task_snapshot` → `plan_snapshot`, etc.), all backward-compat aliases removed from `tool_models.py`, `schemas.py`, `handlers.py`, `app.py`, and `mcp_local/planexe_mcp_local.py` (~86 lines deleted). Test files renamed from `test_task_*.py` to `test_plan_*.py` with patch targets updated.

### ~~4.10 `plan_list` auth differs from `plan_create`~~ (FIXED)

`plan_list` now uses the same `PLANEXE_MCP_REQUIRE_USER_KEY` check as `plan_create`. When the key is not required and not provided, `plan_list` returns all tasks (no user scoping). `_list_tasks_sync` accepts `user_id=None` to support this.

---

## 5. Proposed Improvements

### 5.1 SSE progress streaming (UX)

Long-running plans (10–20 minutes) give the user no feedback. A `log_lines` array in the `plan_status` response (last 50 lines of agent output) would dramatically improve perceived responsiveness.

### 5.2 Webhook / push notification (power users)

Add an optional `webhook_url` to `plan_create`. When the task transitions to `completed` or `failed`, POST a JSON summary to that URL. This removes the need for polling and enables CI/CD integrations.

### 5.3 API versioning

All tool names and schemas are currently unversioned. A future breaking change will silently break clients. Add a `server_version` field to the `plan_status` output and document a stability policy.

### 5.4 Startup environment validation

Add an explicit check at server startup that required secrets (`PLANEXE_API_KEY_SECRET`, `PLANEXE_DOWNLOAD_TOKEN_SECRET`) are set when auth is enabled. Fail loudly instead of falling back to dev defaults.

---

## 6. Promotion and Growth Strategies

### 6.1 MCP registries

- **Glama** — already listed
- **mcp.so** — submit `server.json`; high traffic from Claude desktop users
- **Smithery** — another fast-growing directory; supports one-click install
- **awesome-mcp-servers** (GitHub) — submit a PR; maintainers merge quickly
- **OpenTools** — focus on enterprise MCP discovery

### 6.2 Content

- **Blog post: "From prompt to project plan in 60 seconds"** — a short walkthrough showing MCP Inspector → `plan_create` → `plan_status` → download. Publish on dev.to, Hacker News (Show HN), and the PlanExe GitHub Discussions.
- **YouTube demo (2–3 minutes)** — screen recording of Claude Desktop using PlanExe MCP end-to-end. Pin it to the README.
- **Twitter/X thread** — "I built an MCP server that turns a ~500-word prompt into a full project plan. Here's how it works:"

### 6.3 Community integrations

- **Claude Desktop config snippet** — provide a ready-to-paste `claude_desktop_config.json` block in the README.
- **Cursor / Windsurf rule** — provide a `.cursorrules` or `.windsurfrules` snippet that wires PlanExe MCP automatically.
- **GitHub Actions** — a reusable workflow `planexe/create-plan@v1` that runs `plan_create` and uploads the result as a release asset. This is a high-visibility integration channel.

### 6.4 Example prompt gallery

Add 10–15 high-quality example prompts (startup, research paper, home renovation, hiring plan, …) to `prompt_examples`. Agents and users copy-paste these; each successful use is a social proof data point.

### 6.5 Observability / social proof

- Add a public counter to the homepage: "X plans created this week".
- Post a monthly changelog to GitHub Discussions so subscribers see activity.
- Badge in the README: `![Plans created](https://img.shields.io/badge/dynamic/json?url=https://mcp.planexe.org/stats&label=plans+created)`.

---

## 7. Quick-win Checklist


| Priority | Task                                                                   | Effort | Status |
| -------- | ---------------------------------------------------------------------- | ------ | ------ |
| P0       | ~~Fix SKILL.md tool count~~                                            | —      | DONE   |
| P0       | ~~Standardise URL trailing slash~~                                     | —      | DONE   |
| P0       | ~~Fix `speed_vs_detail` schema/docs mismatch~~                         | —      | DONE   |
| P0       | ~~Rename tools from `task_*` to `plan_*`~~                             | —      | DONE   |
| P1       | ~~Add `plan_list` tool~~                                               | —      | DONE   |
| P1       | ~~Fix `plan_file_info` empty-dict response~~                           | —      | DONE   |
| P1       | ~~Add rate limiting to `/mcp` endpoint~~                               | —      | DONE   |
| P1       | ~~Signed download tokens~~                                             | —      | DONE   |
| P1       | ~~Refactor `app.py` into modules~~                                     | —      | DONE   |
| P1       | ~~Remove `user_api_key` from `plan_list` visible schema~~              | —      | DONE   |
| P1       | Fail-hard on missing secrets in production (4.1)                       | 1 h    |        |
| P1       | ~~Rate-limit `/download` endpoint (4.2)~~                              | —      | DONE   |
| P1       | ~~Add `plan_list` handler tests (4.5)~~                                | —      | DONE   |
| P1       | Submit to mcp.so + Smithery                                            | 30 min |        |
| P1       | Write README demo GIF / YouTube link                                   | 1 h    |        |
| P2       | ~~Body size validation on Streamable HTTP (4.3)~~                      | —      | DONE   |
| P2       | ~~Return error for invalid artifact value (4.4)~~                      | —      | DONE   |
| P2       | ~~Add tool-call audit logging (4.7)~~                                  | —      | DONE   |
| P2       | Add `log_lines` to `plan_status` (5.1)                                 | 4 h    |        |
| P2       | ~~Rename internal `task` variables/classes/helpers to `plan` (4.9)~~   | —      | DONE   |
| P2       | ~~Remove backward-compat `Task*`/`handle_task_*`/`TASK_*` aliases (4.9)~~ | —  | DONE   |
| P2       | ~~Rename test files from `test_task_*` to `test_plan_*` (4.9)~~       | —      | DONE   |
| P2       | Tighten default CORS origins (4.6)                                     | 30 min |        |
| P2       | ~~Align `plan_list` auth with `plan_create` (4.10)~~                   | —      | DONE   |
| P3       | Webhook support (5.2)                                                  | 1 day  |        |
| P3       | API versioning (5.3)                                                   | 4 h    |        |
| P3       | GitHub Actions integration (6.3)                                       | 1 day  |        |


---

## 8. Summary

The MCP surface is functionally solid and ahead of most MCP servers in terms of schema rigour, annotation coverage, and security (signed download tokens, layered auth, auto-injected user keys). The codebase has been significantly improved since rev 1: `app.py` was refactored from a 76 KB monolith into 10+ focused modules, `plan_list` now follows the same auth-injection pattern as `plan_create`, and all P0 issues are resolved.

The main remaining weakness is that production deployments can silently fall back to dev-mode secrets (`auth.py`, `download_tokens.py`). This is not blocking, but addressing it (fail-hard on missing secrets when auth is enabled) would meaningfully tighten the security posture.
