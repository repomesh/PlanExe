---
title: MCP Interface — Evaluation and Roadmap
date: 2026-02-25
---

# MCP Interface — Evaluation and Roadmap

An honest audit of the current MCP surface (mcp_cloud + mcp_local), followed by concrete improvements and promotion ideas.

---

## 1. What's Working Well

**Dual transport.** `mcp_cloud` (stateless HTTP / Railway) and `mcp_local` (stdio proxy) cover the two major deployment patterns. Most users can pick one without reading source code.

**Layered authentication.** Two distinct auth paths — a server-wide `PLANEXE_MCP_API_KEY` for self-hosters, and per-user `pex_…` keys issued by home.planexe.org — are a good design. The key-normalisation fix (`_normalize_api_key_value`) makes the second path robust against copy-paste artefacts.

**Structured output schemas.** Every tool declares an `output_schema`, so MCP clients can validate responses without guessing. The `TestAllToolsHaveOutputSchema` test enforces this at CI time.

**Tool annotations.** `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` are set on every tool and tested. This is ahead of most MCP servers.

**task_retry with model_profile selection.** Allowing the caller to re-run a failed task with a stronger model (e.g. upgrade from `baseline` to `thorough`) at retry time is genuinely useful.

**Glama + llms.txt.** Being listed in the Glama registry and providing `llms.txt` lowers the discovery barrier for new users.

**Rate limiting on REST endpoints.** `slowapi` limits `/tasks` create/retry endpoints, protecting the backend from burst abuse.

**Prompt guidance in schema.** The `prompt` field description ("300–800 words … objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria") sets user expectations up front.

---

## 2. What's Broken or Inconsistent

### 2.1 ~~`skills/planexe-mcp/SKILL.md` says "5 tools"~~ (FIXED)

Updated to "seven core tools"; added Tool 5 (`model_profiles`) and Tool 7 (`task_retry`) sections; updated the typical workflow to reference both. Note: with `task_list` now added the total is eight — SKILL.md updated accordingly.

### 2.2 ~~Trailing-slash inconsistency~~ (FIXED)

The canonical URL (`https://mcp.planexe.org/mcp`, no trailing slash) is used in all JSON config files and registry entries. The MCP Inspector CLI command in `docs/mcp/inspector.md` intentionally keeps the trailing slash (the inspector appends sub-paths; without `/` it sends requests to the wrong path). A note clarifying this distinction was added to `inspector.md`.

### 2.3 ~~`speed_vs_detail` is documented but hidden from agents~~ (FIXED)

The `speed_vs_detail` parameter was a developer-only hidden override that was rarely used and created a docs/schema mismatch. It has been removed from the MCP interface entirely: the dead code was deleted from `mcp_cloud/app.py` and `mcp_cloud/http_server.py`, the legacy backward-compat forwarding block was removed from `mcp_local/planexe_mcp_local.py`, and all references were purged from docs.

### 2.4 ~~`task_file_info` returns `{}` on success instead of `isError`~~ (FIXED)

`task_file_info` now returns `{"ready": false, "reason": "processing"}` when the task is still running, and `{"ready": false, "reason": "failed", "error": {...}}` when it has failed. The output schema was updated (replaced the empty-dict variant with `TaskFileInfoNotReadyOutput`), and both `PLANEXE_SERVER_INSTRUCTIONS` and the tool description were updated accordingly.

### 2.5 ~~Rate limiting covers REST but not the Streamable HTTP `/mcp` endpoint~~ (FIXED)

`_enforce_rate_limit` in `mcp_cloud/http_server.py` now applies to `/mcp` and `/mcp/` in addition to `/mcp/tools/call`. The default limit (60 req/60 s per client) is high enough that normal polling of `task_status` is never affected.

### 2.6 ~~No `task_list` tool — lost `task_id` = lost task~~ (FIXED)

Added `task_list` to both `mcp_cloud` and `mcp_local`. Requires `user_api_key`; returns up to 50 tasks newest-first with `task_id`, `state`, `progress_percentage`, `created_at`, and `prompt_excerpt`. The `task_create` description was updated to say "call task_list to recover a lost task_id" instead of "no task_list, lost task_id = lost task".

### 2.7 `app.py` is an 81 KB monolith

All tool handlers, auth logic, DB calls, and schema definitions live in one file. This makes onboarding slow, PRs hard to review, and bugs harder to isolate.

**Fix:** Refactor into modules: `auth.py`, `tools/task.py`, `tools/meta.py`, `schemas.py`.

---

## 3. Proposed Improvements

### 3.1 `task_list` tool (high value, low effort)

```json
{
  "name": "task_list",
  "description": "List the most recent tasks for the authenticated user.",
  "inputSchema": {
    "properties": {
      "limit": {"type": "integer", "default": 10, "maximum": 50}
    }
  }
}
```

Recovers lost task IDs, enables dashboards, and is the single most-requested missing feature in similar task-runner MCP servers.

### 3.2 ~~Signed, expiring download tokens~~ (FIXED)

`task_file_info` now returns download URLs that include a signed, short-lived token:
`/download/{task_id}/{filename}?token={expiry}.{hmac_sha256}`.

- Token is HMAC-SHA256 over `task_id:filename:expiry`, scoped to one artifact.
- Default TTL: 15 minutes (configurable via `PLANEXE_DOWNLOAD_TOKEN_TTL`).
- Secret priority: `PLANEXE_DOWNLOAD_TOKEN_SECRET` → `PLANEXE_API_KEY_SECRET` → random per-process (with warning).
- Tokenised URLs work in a browser without an API key header; the middleware validates the token and skips the API-key check.
- Defence-in-depth: the download endpoint re-validates the token even after the middleware has passed it.
- Backward compatible: requests without a token still require a valid API key header (existing behaviour).

### 3.3 SSE progress streaming (UX)

Long-running plans (10–20 minutes) give the user no feedback. A `task_progress` SSE endpoint (or a `progress` field in `task_status`) returning incremental log lines would dramatically improve perceived responsiveness.

Minimum viable version: a `log_lines` array in the `task_status` response (last 50 lines of agent output).

### 3.4 Webhook / push notification (power users)

Add an optional `webhook_url` to `task_create`. When the task transitions to `completed` or `failed`, POST a JSON summary to that URL. This removes the need for polling and enables CI/CD integrations.

### 3.5 API versioning

All tool names and schemas are currently unversioned. A future breaking change (e.g. renaming `task_file_info` to `task_files`) will silently break clients.
Add a `server_version` field to the `task_status` output and document a stability policy.

### 3.6 Refactor `app.py` into modules

```
mcp_cloud/
  auth.py          # _resolve_user_from_api_key, _hash_user_api_key
  schemas.py       # TASK_CREATE_INPUT_SCHEMA, TOOL_DEFINITIONS, …
  tools/
    task.py        # task_create, task_status, task_stop, task_retry, task_list
    meta.py        # prompt_examples, model_profiles
  http_server.py   # ASGI wiring only
  app.py           # thin entry-point, imports from above
```

### 3.7 Remove or deprecate legacy REST endpoints

The `/tasks` REST routes duplicate functionality now available through MCP tools. Keeping both surfaces means bugs can exist in one but not the other (as happened with the auth issue). Deprecate `/tasks` in favour of the MCP tool surface, with a sunset date in the changelog.

---

## 4. Promotion and Growth Strategies

### 4.1 MCP registries

- **Glama** — already listed ✓
- **mcp.so** — submit `server.json`; high traffic from Claude desktop users
- **Smithery** — another fast-growing directory; supports one-click install
- **awesome-mcp-servers** (GitHub) — submit a PR; maintainers merge quickly
- **OpenTools** — focus on enterprise MCP discovery

### 4.2 Content

- **Blog post: "From prompt to project plan in 60 seconds"** — a short walkthrough showing MCP Inspector → task_create → task_status → download. Publish on dev.to, Hacker News (Show HN), and the PlanExe GitHub Discussions.
- **YouTube demo (2–3 minutes)** — screen recording of Claude Desktop using PlanExe MCP end-to-end. Pin it to the README.
- **Twitter/X thread** — "I built an MCP server that turns a ~500-word prompt into a full project plan. Here's how it works: 🧵"

### 4.3 Community integrations

- **Claude Desktop config snippet** — provide a ready-to-paste `claude_desktop_config.json` block in the README.
- **Cursor / Windsurf rule** — provide a `.cursorrules` or `.windsurfrules` snippet that wires PlanExe MCP automatically.
- **GitHub Actions** — a reusable workflow `planexe/create-plan@v1` that runs `task_create` and uploads the result as a release asset. This is a high-visibility integration channel.

### 4.4 Example prompt gallery

Add 10–15 high-quality example prompts (startup, research paper, home renovation, hiring plan, …) to `prompt_examples`. Agents and users copy-paste these; each successful use is a social proof data point.

### 4.5 Observability / social proof

- Add a public counter to the homepage: "X plans created this week".
- Post a monthly changelog to GitHub Discussions so subscribers see activity.
- Badge in the README: `![Plans created](https://img.shields.io/badge/dynamic/json?url=https://mcp.planexe.org/stats&label=plans+created)`.

---

## 5. Quick-win Checklist

| Priority | Task | Effort |
|----------|------|--------|
| P0 | ~~Fix SKILL.md tool count~~ (DONE) | — |
| P0 | ~~Standardise URL trailing slash~~ (DONE) | — |
| P0 | ~~Fix `speed_vs_detail` schema/docs mismatch~~ (DONE) | — |
| P1 | ~~Add `task_list` tool~~ (DONE) | — |
| P1 | ~~Fix `task_file_info` empty-dict response~~ (DONE) | — |
| P1 | ~~Add rate limiting to `/mcp` endpoint~~ (DONE) | — |
| P1 | Submit to mcp.so + Smithery | 30 min |
| P1 | Write README demo GIF / YouTube link | 1 h |
| P2 | Add `log_lines` to task_status | 4 h |
| P2 | Refactor app.py into modules | 1 day |
| P3 | ~~Signed download tokens~~ (DONE) | — |
| P3 | Webhook support | 1 day |
| P3 | GitHub Actions integration | 1 day |

---

## 6. Summary

The MCP surface is functionally solid and ahead of most hobby MCP servers in terms of schema rigour and annotation coverage. The main weaknesses are: small but sharp inconsistencies in docs/schemas that erode trust, a missing `task_list` tool that makes the server feel fragile in long agent sessions, and limited discovery beyond Glama. Fixing the P0/P1 items above takes less than a day and would meaningfully improve both reliability and adoption.
