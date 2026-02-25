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

### 2.1 `skills/planexe-mcp/SKILL.md` says "5 tools"

The skill card lists five tools, but the server now exposes **7** (prompt_examples, model_profiles, task_create, task_status, task_stop, task_retry, task_file_info). Any agent or user reading SKILL.md gets a wrong mental model.

**Fix:** Update SKILL.md tool count and add task_retry + model_profiles to the description.

### 2.2 Trailing-slash inconsistency

`mcp_cloud/server.json` registers the URL as `https://mcp.planexe.org/mcp` (no trailing slash).
`docs/mcp/inspector.md` tells users to connect to `https://mcp.planexe.org/mcp/` (trailing slash).

This causes connection failures in clients that do not normalise URLs.

**Fix:** Pick one canonical form (prefer no trailing slash, matching RFC 3986) and use it everywhere.

### 2.3 `speed_vs_detail` is documented but hidden from agents

`docs/mcp/mcp_details.md` documents a `speed_vs_detail` parameter for `task_create`, but it is not present in the published input schema (`TASK_CREATE_INPUT_SCHEMA`). Agents reading only the live schema never see it; agents reading only the docs expect it to work.

**Fix:** Either expose the parameter in the schema, or remove it from the docs.

### 2.4 `task_file_info` returns `{}` on success instead of `isError`

When a task has not finished yet, `task_file_info` returns an empty dict `{}` rather than a structured "not ready" response. Callers cannot distinguish "no files yet" from "something went wrong" without reading `task_status` separately.

**Fix:** Return a typed response, e.g. `{"ready": false, "reason": "processing"}` or set `isError=True` with a message.

### 2.5 Rate limiting covers REST but not the Streamable HTTP `/mcp` endpoint

The slowapi limiter is applied to `/tasks` routes. The MCP `task_create` tool also triggers task creation on the backend but goes through the `/mcp` Starlette sub-app, which has no equivalent rate guard.

**Fix:** Apply rate limiting inside the MCP tool handler itself (e.g. a per-user token bucket stored in Redis / memory) so the protection is transport-agnostic.

### 2.6 No `task_list` tool — lost `task_id` = lost task

There is no way for an agent to list its own tasks. If the agent loses the `task_id` between turns (context truncation, restart), the task is permanently inaccessible.

**Fix:** Add a `task_list` tool that returns recent tasks for the authenticated user (up to the last 20, newest first).

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

### 3.2 Signed, expiring download tokens (security)

`task_file_info` returns a plain `/download?task_id=…` URL. Anyone who intercepts that URL can download the file.
Replace with short-lived signed tokens (HMAC-SHA256, 15-minute TTL) so the URL is only valid for the session.

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
| P0 | Fix SKILL.md tool count (5 → 7) | 5 min |
| P0 | Standardise URL trailing slash across all docs | 10 min |
| P0 | Fix `speed_vs_detail` schema/docs mismatch | 15 min |
| P1 | Add `task_list` tool | 2 h |
| P1 | Fix `task_file_info` empty-dict response | 1 h |
| P1 | Submit to mcp.so + Smithery | 30 min |
| P1 | Write README demo GIF / YouTube link | 1 h |
| P2 | Add rate limiting to MCP tool handlers | 3 h |
| P2 | Add `log_lines` to task_status | 4 h |
| P2 | Refactor app.py into modules | 1 day |
| P3 | Signed download tokens | 4 h |
| P3 | Webhook support | 1 day |
| P3 | GitHub Actions integration | 1 day |

---

## 6. Summary

The MCP surface is functionally solid and ahead of most hobby MCP servers in terms of schema rigour and annotation coverage. The main weaknesses are: small but sharp inconsistencies in docs/schemas that erode trust, a missing `task_list` tool that makes the server feel fragile in long agent sessions, and limited discovery beyond Glama. Fixing the P0/P1 items above takes less than a day and would meaningfully improve both reliability and adoption.
