# mcp_local agent instructions

Scope: local MCP proxy script that runs on the user's machine and forwards tool calls
to mcp_cloud, a MCP server running in the cloud, over HTTP.

## Interaction model
- The local proxy exposes MCP tools over stdio and forwards requests to mcp_cloud
  using `PLANEXE_URL` (defaults to the hosted `/mcp` endpoint).
- Supported tools: `prompt_examples`, `model_profiles`, `task_create`, `task_status`, `task_stop`, `task_download`.
- `task_download` calls the remote `task_file_info` tool to obtain a download URL,
  then downloads the artifact to `PLANEXE_PATH` on the local machine.
- `task_create` visible input schema includes `prompt`, optional `model_profile`, and optional `user_api_key`.
- Use `model_profiles` to help agents select `task_create.model_profile` without relying on internal file knowledge.
- Keep workflow wording explicit that prompt drafting + user approval is a non-tool step before `task_create`.
- Keep concurrency wording explicit: each `task_create` call creates a new `task_id`; no global per-client concurrency cap is enforced server-side.
- Runtime override `speed_vs_detail` is metadata-only (hidden from visible schema);
  when callers still pass legacy top-level `speed_vs_detail`/`speed`, forward those
  into `metadata.task_create` for backward compatibility.

## Public state contract
- `task_status.state` must use exactly: `pending`, `processing`, `completed`, `failed`.
- Caller contract:
  - `pending`/`processing`: keep polling.
  - `completed`: download is ready.
  - `failed`: terminal error.
- Do not use legacy public names such as `running`, `stopping`, or `stopped`.
- Do not expose internal implementation symbols (for example `TaskState.pending`) in
  model-facing text; use plain public strings.
- Troubleshooting guidance to keep aligned with cloud docs/instructions:
  - `pending` for longer than 5 minutes likely means queued but not picked up by worker.
  - `processing` with no output-file changes for longer than 20 minutes likely means stalled/failed execution.
  - Report both cases at `https://github.com/PlanExeOrg/PlanExe/issues`.

## task_stop semantics
- `task_stop` is a stop request/acknowledgement, not a separate lifecycle state.
- Return payload should include current public `state` plus `stop_requested`.

## Constraints
- Do not add dependencies outside the existing runtime (stdlib + `mcp`).
- Keep remote requests compatible with both:
  - HTTP wrapper (`/mcp/tools/call`)
  - Streamable MCP JSON-RPC (`/mcp`)
- Ensure all tool responses include structured content when an output schema is defined.
- Keep local proxy error semantics documented and stable (`REMOTE_ERROR`, `DOWNLOAD_FAILED`) and pass through cloud error payloads unchanged when possible.
- Tool-surface split must remain explicit:
  - local exposes `task_download`.
  - cloud exposes `task_file_info`.
  - do not expose `task_file_info` as a local tool name.
- **Run as task**: Do not advertise the MCP **tasks** protocol (tasks/get, tasks/result, tasks/cancel, tasks/list) or add tool-level "Run as task" support. PlanExe’s interface is tool-based only (task_create → task_status → task_download). The MCP tasks protocol is a different, client-driven feature; Cursor and the Python MCP SDK do not support it properly, so we keep tools-only for compatibility.

## Env vars
- `PLANEXE_URL`: Base URL for mcp_cloud (e.g., `http://localhost:8001/mcp`).
- `PLANEXE_MCP_API_KEY`: API key forwarded to remote as custom header `X-API-Key`.
- `PLANEXE_PATH`: Local directory where downloads are saved.
  - Must be a directory.
  - Created automatically when missing.
  - Defaults to current working directory when unset.
  - Saved filename pattern: `<task_id>-<artifact_basename>` with numeric suffixes on collisions.
