---

## title: MCP Interface — Evaluation and Roadmap
date: 2026-02-26

# MCP Interface — Evaluation and Roadmap

An honest audit of the current MCP surface (`mcp_cloud` + `mcp_local`), followed by concrete improvements and promotion ideas.

**Revision note (2026-02-26):** All MCP tools have been renamed from the `task_`* prefix to `plan_*` (commits c3acf06d, 6573ef25). This revision updates the document to reflect the current naming and implementation state.

---

## 1. Current Tool Surface

Eight tools, split across two transports:


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

---

## 2. What's Working Well

**Dual transport.** `mcp_cloud` (stateless HTTP / Railway) and `mcp_local` (stdio proxy) cover the two major deployment patterns. Most users can pick one without reading source code.

**Consistent `plan_`* naming.** The rename from `task_`* to `plan_*` aligns tool names with the product domain.

**Layered authentication.** Two distinct auth paths — a server-wide `PLANEXE_MCP_API_KEY` for self-hosters, and per-user `pex_…` keys issued by home.planexe.org — are a good design. The key-normalisation fix (`_normalize_api_key_value`) makes the second path robust against copy-paste artefacts.

**Structured output schemas.** Every tool declares an `output_schema`, so MCP clients can validate responses without guessing. `TestAllToolsHaveOutputSchema` enforces this at CI time.

**Tool annotations.** `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` are set on every tool and tested. This is ahead of most MCP servers.

`**plan_retry` with model_profile selection.** Allowing the caller to re-run a failed task with a stronger model (e.g. upgrade from `baseline` to `premium`) at retry time is genuinely useful.

**Signed download tokens.** `plan_file_info` returns download URLs with HMAC-SHA256 signed, time-limited tokens scoped to one artifact. Tokens work in a browser without an API key header. Defence-in-depth: the download endpoint re-validates even after middleware has passed the token.

**Glama + llms.txt.** Being listed in the Glama registry and providing `llms.txt` lowers the discovery barrier for new users.

**Rate limiting on all MCP endpoints.** `_enforce_rate_limit` in `http_server.py` applies to `/mcp`, `/mcp/`, and `/mcp/tools/call`. The default limit (60 req / 60 s per client) is high enough that normal `plan_status` polling is never affected.

**Prompt guidance in schema.** The `prompt` field description ("300–800 words … objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria") sets user expectations up front.

`**plan_list` for task recovery.** Authenticated users can list their most recent tasks (up to 50, newest-first) to recover a lost `task_id`. Each entry includes `task_id`, `state`, `progress_percentage`, `created_at`, and `prompt_excerpt`.

**Comprehensive test suite.** 12 test files covering tool surface consistency, auth key parsing, CORS config, download tokens, HTTP routing, and individual tool behaviour.

---

## 3. What's Been Fixed (Previously Reported)

### 3.1 ~~`skills/planexe-mcp/SKILL.md` says "5 tools"~~ (FIXED)

Updated to eight core tools; SKILL.md now lists all tools with example JSON-RPC calls.

### 3.2 ~~Trailing-slash inconsistency~~ (FIXED)

The canonical URL (`https://mcp.planexe.org/mcp`, no trailing slash) is used in all JSON config files and registry entries. The MCP Inspector CLI command in `docs/mcp/inspector.md` intentionally keeps the trailing slash (the inspector appends sub-paths).

### 3.3 ~~`speed_vs_detail` documented but hidden from agents~~ (FIXED)

Removed entirely from the MCP interface. Dead code deleted from `mcp_cloud/app.py`, `mcp_cloud/http_server.py`, and `mcp_local/planexe_mcp_local.py`.

### 3.4 ~~`plan_file_info` returns `{}` on success instead of `isError~~` (FIXED)

Now returns `{"ready": false, "reason": "processing"}` while running and `{"ready": false, "reason": "failed", "error": {...}}` on failure. Output schema updated with `PlanFileInfoNotReadyOutput`.

### 3.5 ~~Rate limiting covers REST but not Streamable HTTP `/mcp~~` (FIXED)

`_enforce_rate_limit` now covers `/mcp`, `/mcp/`, and `/mcp/tools/call`.

### 3.6 ~~No `plan_list` tool — lost `task_id` = lost task~~ (FIXED)

Added `plan_list` to both `mcp_cloud` and `mcp_local`. Requires `user_api_key`; returns up to 50 tasks newest-first. The `plan_create` description was updated to reference `plan_list` for recovery.

### 3.7 ~~Signed, expiring download tokens~~ (FIXED)

HMAC-SHA256 tokens, 15-minute default TTL, scoped per-artifact. See section 2 for details.

### 3.8 ~~Tools used `task_`* prefix instead of `plan_*~~` (FIXED)

All external tool names renamed to `plan_*` (commits c3acf06d, 6573ef25). Internal variable names, request classes, and helper functions still use the old `task` naming — see 4.10.

---

## 4. What's Broken or Inconsistent

### 4.1 `app.py` is a 76 KB monolith

All tool handlers, auth logic, DB calls, schema definitions, file-fetch utilities, download-token logic, model-profile management, and example-prompt loading live in one file (~1843 lines). This makes onboarding slow, PRs hard to review, and bugs harder to isolate.

**Fix:** Refactor into modules (see section 5.4).

### 4.2 Dev-secret fallback in production

`_hash_user_api_key` falls back to a hardcoded `"dev-api-key-secret"` when `PLANEXE_API_KEY_SECRET` is unset (`app.py:281`). A warning is logged once, but the server continues. In production this means all user keys hash with a known default, which is a security risk.

Similarly, `PLANEXE_DOWNLOAD_TOKEN_SECRET` falls back to a random per-process secret (`app.py:1000-1011`). This means download tokens expire on server restart and are invalid across processes in a distributed setup.

**Fix:** Fail hard at startup if these secrets are not set when `PLANEXE_MCP_REQUIRE_AUTH` is true (i.e. production mode).

### 4.3 `/download` endpoint not rate-limited

`_enforce_rate_limit` only covers `/mcp/tools/call`, `/mcp`, and `/mcp/`. The `/download/{task_id}/{filename}` endpoint has no rate limit, allowing repeated large-file downloads that could overload the server.

**Fix:** Add `/download` to the rate-limited paths in `http_server.py`.

### 4.4 Body size validation only on REST endpoint

`MAX_BODY_BYTES` is only enforced on `/mcp/tools/call` POST (`http_server.py:469`). The Streamable HTTP `/mcp/` endpoint (mounted as a sub-app) bypasses this check, allowing arbitrarily large payloads.

**Fix:** Apply size validation to the `/mcp/` endpoint as well, or add it as middleware.

### 4.5 `plan_file_info` silently defaults invalid artifact to `"report"`

If a caller passes `artifact="invalid"`, the handler silently falls back to `"report"` (`app.py:1674-1676`) instead of returning a validation error.

**Fix:** Return an `INVALID_ARGUMENT` error for unrecognised artifact values.

### 4.6 No dedicated `plan_list` test

`plan_list` is validated for schema presence and annotation correctness in `test_tool_surface_consistency.py`, but there is no dedicated test file exercising the handler logic (limit clamping, auth validation, empty-result behaviour, ordering).

**Fix:** Add `mcp_cloud/tests/test_plan_list_tool.py`.

### 4.7 CORS default is wildcard

`PLANEXE_MCP_CORS_ORIGINS` defaults to `["*"]` when unset (`http_server.py:139-143`). The comment says "API-key auth is the primary access control", but wildcard CORS exposes all endpoints to any origin.

**Fix:** Default to a restrictive origin list (e.g. `["https://mcp.planexe.org", "https://home.planexe.org"]`) and document the `PLANEXE_MCP_CORS_ORIGINS` override in the README.

### 4.8 No request logging for successful tool calls

`_log_auth_rejection()` logs failed auth attempts, but successful tool calls are not logged. This makes it impossible to audit which tools were called by whom.

**Fix:** Add INFO-level logging in `handle_call_tool` on successful dispatch (tool name, user ID if authenticated, duration).

### 4.9 Prompt excerpt length hardcoded

`_list_tasks_sync` truncates prompts to 100 characters (`app.py:474`). This matches the tool description ("first 100 chars") but is a magic number buried in the function body.

**Fix:** Define as a module constant `PROMPT_EXCERPT_MAX_LENGTH = 100`.

### 4.10 Stale `task` variable names and backward-compat aliases throughout the codebase

The tool rename from `task_`* to `plan_*` only covered the external-facing tool names and handler function names. Internally, the code still uses `task` naming pervasively:

- **Request classes** in `app.py` are still named `TaskCreateRequest`, `TaskStatusRequest`, `TaskStopRequest`, `TaskRetryRequest`, `TaskFileInfoRequest`, `TaskListRequest` (lines 205–227).
- **Local variables** storing `PlanItem` instances are still named `task` throughout `app.py` (e.g. `task = find_plan_by_task_id(task_id)` at lines 235, 353, 366, 385, 443, 517, 524, 531, 538, 735).
- **Helper functions** still use the old naming: `get_task_by_id`, `find_plan_by_task_id`, `resolve_task_for_task_id`, `_create_task_sync`, `_get_task_status_snapshot_sync`, `_request_task_stop_sync`, `_retry_failed_task_sync`, `_get_task_for_report_sync`, `_list_tasks_sync`.
- **Backward-compat aliases** in `app.py` (lines 1162–1173, 1819–1825): `TASK_*_SCHEMA = PLAN_*_SCHEMA` and `handle_task_* = handle_plan_`*.
- **Backward-compat aliases** in `tool_models.py` (lines 303–320): `TaskCreateInput = PlanCreateInput`, `TaskListOutput = PlanListOutput`, etc. (18 aliases).
- **Backward-compat aliases** in `mcp_local/planexe_mcp_local.py` (lines 422–426, 616–622, 1055–1060): schema and handler aliases.

This creates a confusing split where the external API says `plan_`* but reading the implementation requires mentally translating `task` back to `plan`. The backward-compat aliases add ~50 lines of dead weight across three files.

**Fix:** Rename internal request classes to `PlanCreateRequest`, etc. Rename local variables from `task` to `plan` (or `plan_item`). Rename helper functions from `*_task_`* to `*_plan_*`. Remove the backward-compat aliases — nothing external imports them (they were only added as a safety net during the rename).

---

## 5. Proposed Improvements

### 5.1 SSE progress streaming (UX)

Long-running plans (10–20 minutes) give the user no feedback. A `log_lines` array in the `plan_status` response (last 50 lines of agent output) would dramatically improve perceived responsiveness.

### 5.2 Webhook / push notification (power users)

Add an optional `webhook_url` to `plan_create`. When the task transitions to `completed` or `failed`, POST a JSON summary to that URL. This removes the need for polling and enables CI/CD integrations.

### 5.3 API versioning

All tool names and schemas are currently unversioned. A future breaking change will silently break clients. Add a `server_version` field to the `plan_status` output and document a stability policy.

### 5.4 Refactor `app.py` into modules

```
mcp_cloud/
  auth.py          # _resolve_user_from_api_key, _hash_user_api_key
  schemas.py       # PLAN_CREATE_INPUT_SCHEMA, TOOL_DEFINITIONS, …
  tools/
    plan.py        # plan_create, plan_status, plan_stop, plan_retry, plan_list
    meta.py        # prompt_examples, model_profiles
    download.py    # plan_file_info, download token logic
  http_server.py   # ASGI wiring only
  app.py           # thin entry-point, imports from above
```

### 5.5 Startup environment validation

Add an explicit check at server startup that required secrets (`PLANEXE_API_KEY_SECRET`, `PLANEXE_DOWNLOAD_TOKEN_SECRET`) are set when auth is enabled. Fail loudly instead of falling back to dev defaults.

### 5.6 Remove or deprecate legacy REST endpoints

The `/tasks` REST routes duplicate functionality now available through MCP tools. Keeping both surfaces means bugs can exist in one but not the other. Deprecate `/tasks` in favour of the MCP tool surface, with a sunset date in the changelog.

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
| P0       | ~~Rename tools from `task_`* to `plan_*~~`                             | —      | DONE   |
| P1       | ~~Add `plan_list` tool~~                                               | —      | DONE   |
| P1       | ~~Fix `plan_file_info` empty-dict response~~                           | —      | DONE   |
| P1       | ~~Add rate limiting to `/mcp` endpoint~~                               | —      | DONE   |
| P1       | ~~Signed download tokens~~                                             | —      | DONE   |
| P1       | Fail-hard on missing secrets in production (4.2)                       | 1 h    |        |
| P1       | Rate-limit `/download` endpoint (4.3)                                  | 30 min |        |
| P1       | Add `plan_list` handler tests (4.6)                                    | 2 h    |        |
| P1       | Submit to mcp.so + Smithery                                            | 30 min |        |
| P1       | Write README demo GIF / YouTube link                                   | 1 h    |        |
| P2       | Body size validation on Streamable HTTP (4.4)                          | 1 h    |        |
| P2       | Return error for invalid artifact value (4.5)                          | 30 min |        |
| P2       | Add tool-call audit logging (4.8)                                      | 1 h    |        |
| P2       | Add `log_lines` to `plan_status` (5.1)                                 | 4 h    |        |
| P2       | Rename internal `task` variables/classes/helpers to `plan` (4.10)      | 4 h    |        |
| P2       | Remove backward-compat `Task*`/`handle_task_*`/`TASK_*` aliases (4.10) | 1 h    |        |
| P2       | Refactor `app.py` into modules (5.4)                                   | 1 day  |        |
| P2       | Tighten default CORS origins (4.7)                                     | 30 min |        |
| P3       | Webhook support (5.2)                                                  | 1 day  |        |
| P3       | API versioning (5.3)                                                   | 4 h    |        |
| P3       | GitHub Actions integration (6.3)                                       | 1 day  |        |


---

## 8. Summary

The MCP surface is functionally solid and ahead of most MCP servers in terms of schema rigour, annotation coverage, and security (signed download tokens, layered auth). The rename from `task_*` to `plan_*` is complete, `plan_list` is implemented across both transports, and all previously-reported P0/P1 issues are resolved.

The remaining weaknesses are: `app.py` is still a large monolith that resists easy review; production deployments can silently fall back to dev-mode secrets; the `/download` endpoint lacks rate limiting; and there is no audit trail for successful tool calls. None of these are blocking, but addressing the P1 items (secret validation, download rate limiting, `plan_list` tests) would meaningfully tighten the security and reliability posture.