# mcp_cloud agent instructions

Scope: Model Context Protocol (MCP) server that provides a standardized interface
for AI agents and developer tools to interact with PlanExe. Communicates with
`worker_plan_database` via the shared Postgres database (`database_api` models).

## Guidelines
- Keep database access wired through `database_api.planexe_db_singleton.db`;
  do not create new engine/session instances here.
- Preserve the startup sequence in `mcp_cloud/app.py`:
  `.env` loading, logging setup, Flask app config, then `db.init_app(app)`.
- Maintain the DB connection logic:
  - Prefer `SQLALCHEMY_DATABASE_URI` when set.
  - Otherwise build from `PLANEXE_POSTGRES_*` (see root `AGENTS.md` for keys).
- MCP tools must follow the specification in `docs/mcp/planexe_mcp_interface.md`:
  - Task management maps to `TaskItem` records (each task = one TaskItem).
  - Events are queried from `EventItem` database records.
- Use the TaskItem UUID as the MCP `task_id`.
- Public task state contract:
  - `task_status.state` must use exactly: `pending`, `processing`, `completed`, `failed`.
  - These values correspond 1:1 with `database_api.model_taskitem.TaskState`.
  - Do not use legacy public names like `running`, `stopping`, or `stopped` for `task_status`.
  - Do not expose internal symbol/class names (for example `TaskState.pending`, `TaskItem.state`) in model-facing tool descriptions; use plain public state strings.
- Download contract:
  - `track_activity.jsonl` is internal-only (`TaskItem.run_track_activity_jsonl`).
  - Downloadable zip artifacts must never include `track_activity.jsonl`.
  - Serve new layout snapshots directly; sanitize only legacy/fallback zips.
- `task_stop` contract:
  - `task_stop` does not create a separate lifecycle state.
  - Return current public `state` plus `stop_requested` to acknowledge stop-flag request.
- Forbidden imports: `worker_plan.app`, `worker_plan_internal`, `frontend_*`,
  `open_dir_server`.

## task_create contract
- Expose `model_profiles` as the discovery tool for profile selection.
- `model_profiles` must report profile guidance and currently available models after class whitelist filtering.
- Keep workflow wording explicit that prompt drafting + user approval is a non-tool step before `task_create`.
- Visible input schema is intentionally limited to:
  - `prompt`
  - `model_profile` (`baseline`, `premium`, `frontier`, `custom`)
  - `user_api_key` (optional)
- Keep `speed_vs_detail` out of model-visible input schema.
- Runtime override for `speed_vs_detail` is metadata-only (tool-specific metadata),
  read from hidden containers (`tool_metadata`, `metadata`, `_meta`) and nested
  namespaces (`task_create`, `planexe_task_create`, `planexe`).
- Preserve compatibility aliases for metadata speed values:
  - `ping` -> `ping_llm`
  - `fast` -> `fast_but_skip_details`
  - `all` -> `all_details_but_slow`

## MCP Protocol
- The server communicates over stdio (standard input/output) following the MCP protocol.
- Tools are registered via `@mcp_cloud.list_tools()` and handled via `@mcp_cloud.call_tool()`.
- All tool responses must be JSON-serializable and follow the error model in the spec.
- Keep tool error codes/docs aligned with actual runtime payloads (for example `TASK_NOT_FOUND`, `INVALID_USER_API_KEY`, `USER_API_KEY_REQUIRED`, `INSUFFICIENT_CREDITS`, `generation_failed`, `content_unavailable`, `INTERNAL_ERROR`).
- Event cursors use format `cursor_{event_id}` for incremental polling.
- **Run as task**: We expose MCP **tools** only (task_create, task_status, task_stop, etc.), not the MCP **tasks** protocol (tasks/get, tasks/result, etc.). Do not advertise the tasks capability or add "Run as task" support; the spec and clients (e.g. Cursor) are aligned on tools-only.

## Authentication Policy
- PlanExe MCP cloud authentication is API-key header based.
- Canonical client header is `X-API-Key: pex_...`.
- OAuth is not supported for the MCP API. Do not document, imply, or advertise OAuth support.
- In docs and user-facing error/help text, instruct clients to use `X-API-Key` custom headers.

## Download URL environment behavior
- `task_file_info.download_url` should be built from `PLANEXE_MCP_PUBLIC_BASE_URL` when set.
- If `PLANEXE_MCP_PUBLIC_BASE_URL` is unset in HTTP mode, use request host/scheme.
- If no public base URL is available, `download_url` may be absent; document this and guide operators to set `PLANEXE_MCP_PUBLIC_BASE_URL`.

## mcp_local integration
- `mcp_local` runs on the user's machine and forwards tool calls to this server over HTTP.
- It targets either:
  - the HTTP wrapper endpoint (`/mcp/tools/call`), or
  - the streamable MCP JSON-RPC endpoint (`/mcp`).
- Tool-surface split must stay explicit:
  - `mcp_cloud` exposes `task_file_info` (not `task_download`).
  - `mcp_local` exposes `task_download` and implements it via cloud `task_file_info`.
- `task_file_info` provides download metadata that `mcp_local` uses to download
  artifacts via `/download/{task_id}/...`.

## Troubleshooting guidance (caller-facing text)
- Keep guidance aligned across server instructions and tool descriptions:
  - `pending` for longer than 5 minutes usually means queued but not picked up by worker.
  - `processing` with no output-file changes for longer than 20 minutes usually means stalled/failed execution.
  - In both cases, direct users to report issues at `https://github.com/PlanExeOrg/PlanExe/issues`.

## MCP Registry metadata
- Registry metadata for this server lives at `mcp_cloud/server.json`.
- Keep `server.json` aligned with deployed behavior:
  - `remotes[].url` must point at the production MCP endpoint.
  - required auth headers must match the server auth policy (`X-API-Key`).
- Publish with `mcp-publisher` from the `mcp_cloud/` directory so it picks up this file.

## Testing
- Automated tests exist under `mcp_cloud/tests/`.
- If you change MCP tool behavior, state mapping, or tool surface, update/add unit
  tests close to the changed logic.
- Run focused tests from repo root, for example:
  - `python -m unittest mcp_cloud.tests.test_tool_surface_consistency`
  - `python -m unittest mcp_cloud.tests.test_task_status_tool`
