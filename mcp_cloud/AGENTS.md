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
  - Task management maps to `PlanItem` records (each task = one PlanItem).
  - Events are queried from `EventItem` database records.
- Use the PlanItem UUID as the MCP `plan_id`.
- Public task state contract:
  - `plan_status.state` must use exactly: `pending`, `processing`, `completed`, `failed`.
  - These values correspond 1:1 with `database_api.model_planitem.PlanState`.
  - Do not use legacy public names like `running`, `stopping`, or `stopped` for `plan_status`.
  - Do not expose internal symbol/class names (for example `PlanState.pending`, `PlanItem.state`) in model-facing tool descriptions; use plain public state strings.
- Download contract:
  - `track_activity.jsonl` is internal-only (`PlanItem.run_track_activity_jsonl`).
  - Downloadable zip artifacts must never include `track_activity.jsonl`.
  - Serve new layout snapshots directly; sanitize only legacy/fallback zips.
- `plan_stop` contract:
  - `plan_stop` does not create a separate lifecycle state.
  - Return current public `state` plus `stop_requested` to acknowledge stop-flag request.
- Forbidden imports: `worker_plan.app`, `worker_plan_internal`, `frontend_*`,
  `open_dir_server`.

## plan_create contract
- Expose `model_profiles` as the discovery tool for profile selection.
- `model_profiles` must report profile guidance and currently available models after class whitelist filtering.
- Keep workflow wording explicit that prompt drafting + user approval is a non-tool step before `plan_create`.
- Keep concurrency wording explicit: each `plan_create` call creates a new `plan_id`; no global per-client concurrency cap is enforced server-side.
- Visible input schema is intentionally limited to:
  - `prompt`
  - `model_profile` (`baseline`, `premium`, `frontier`, `custom`)
  - `user_api_key` (optional)

## MCP Protocol
- The server communicates over stdio (standard input/output) following the MCP protocol.
- Tools are registered via `@mcp_cloud.list_tools()` and handled via `@mcp_cloud.call_tool()`.
- All tool responses must be JSON-serializable and follow the error model in the spec.
- Keep tool error codes/docs aligned with actual runtime payloads (for example `PLAN_NOT_FOUND`, `INVALID_USER_API_KEY`, `USER_API_KEY_REQUIRED`, `INSUFFICIENT_CREDITS`, `generation_failed`, `content_unavailable`, `INTERNAL_ERROR`).
- Event cursors use format `cursor_{event_id}` for incremental polling.
- **Run as task**: We expose MCP **tools** only (plan_create, plan_status, plan_stop, etc.), not the MCP **tasks** protocol (tasks/get, tasks/result, etc.). Do not advertise the tasks capability or add "Run as task" support; the spec and clients (e.g. Cursor) are aligned on tools-only.

## Authentication Policy
- PlanExe MCP cloud authentication is API-key header based.
- Canonical client header is `X-API-Key: pex_...`.
- OAuth is not supported for the MCP API. Do not document, imply, or advertise OAuth support.
- In docs and user-facing error/help text, instruct clients to use `X-API-Key` custom headers.
- Keep the auth split used for connector health checks:
  - Unauthenticated discovery/handshake is allowed for:
    - MCP methods: `initialize`, `notifications/initialized`, `tools/list`, `prompts/list`, `resources/list`, `resources/templates/list`, `ping`
    - Probe compatibility: `GET/HEAD/POST /mcp`, `GET/HEAD /mcp/`, and `GET /mcp/tools`
  - `tools/call` without API key is allowed **only** for free setup tools:
    - `model_profiles`
    - `example_prompts`
    - `example_plans`
  - All other tool invocations (for example `plan_create`) must remain API-key protected.
- Keep auth-denial logging explicit (`Auth rejected: ...`) with method/path/user-agent and parsed JSON-RPC methods to make Railway debugging easier.

## HTTP Compatibility and Crawler Endpoints
- Keep `/mcp` -> `/mcp/` redirect behavior for slashless clients/probers.
- Keep CORS headers on early error responses (401/403/429/etc.) so browser inspectors do not fail with opaque CORS errors.
- Keep `PLANEXE_MCP_CORS_ORIGINS` parsing tolerant to quoted CSV and JSON-array env formats.
- Keep `GET /robots.txt` available (200) for crawler health checks and metadata discovery.
- FastMCP session lifecycle lines like `Terminating session: None` are expected informational logs; do not treat them as application failures solely based on Railway’s log-level labeling.

## Download URL environment behavior
- `plan_file_info.download_url` should be built from `PLANEXE_MCP_PUBLIC_BASE_URL` when set.
- If `PLANEXE_MCP_PUBLIC_BASE_URL` is unset in HTTP mode, use request host/scheme.
- If no public base URL is available, `download_url` may be absent; document this and guide operators to set `PLANEXE_MCP_PUBLIC_BASE_URL`.

## mcp_local integration
- `mcp_local` runs on the user's machine and forwards tool calls to this server over HTTP.
- It targets either:
  - the HTTP wrapper endpoint (`/mcp/tools/call`), or
  - the streamable MCP JSON-RPC endpoint (`/mcp`).
- Tool-surface split must stay explicit:
  - `mcp_cloud` exposes `plan_file_info` (not `plan_download`).
  - `mcp_local` exposes `plan_download` and implements it via cloud `plan_file_info`.
- `plan_file_info` provides download metadata that `mcp_local` uses to download
  artifacts via `/download/{plan_id}/...`.

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

## PlanItem deferred columns
- `PlanItem.generated_report_html`, `run_zip_snapshot`, and `run_track_activity_jsonl`
  are declared with `deferred()` so they are **not** loaded by default ORM queries.
- **column_property and deferred()**: `deferred()` descriptors do not support SQL
  operators (`.isnot()`, etc.) at class-definition time — they return `NotImplemented`.
  The `has_*` column properties are therefore defined **after** the class body using
  `PlanItem.__table__.c` (raw Column objects). Type hints inside the class use
  `TYPE_CHECKING` guards so pyright can see them without confusing SQLAlchemy.
- **Session lifetime**: When accessing a deferred column, the ORM instance must still
  be bound to an active session. `get_plan_by_id()` may open a temporary app context
  that closes before the caller touches the deferred attribute, detaching the instance.
  Use `_load_plan_column()` (in `zip_utils.py`) to load a PlanItem and read a deferred
  attribute inside a single app context.
- **Read-only queries**: Prefer explicit column selection (`db.session.query(Col1, Col2, …)`)
  over loading full ORM objects for read-only endpoints like `plan_status` and `plan_list`.
  This avoids accidentally triggering deferred loads and reduces data transfer.

## Worker HTTP fallback ordering
- When resolving file lists or artifacts, try fast local sources first:
  1. DB zip snapshot (`list_files_from_zip_snapshot` / `fetch_file_from_zip_snapshot`)
  2. Local run directory (`list_files_from_local_run_dir`)
  3. Worker HTTP (`fetch_file_list_from_worker_plan` / `fetch_artifact_from_worker_plan`)
- The worker HTTP call has a 30-second timeout. If it runs first, every poll blocks
  for 30 seconds when the worker is unreachable — even when the data is already in the DB.

## Testing
- Automated tests exist under `mcp_cloud/tests/`.
- If you change MCP tool behavior, state mapping, or tool surface, update/add unit
  tests close to the changed logic.
- Run focused tests from repo root, for example:
  - `python -m unittest mcp_cloud.tests.test_tool_surface_consistency`
  - `python -m unittest mcp_cloud.tests.test_plan_status_tool`
