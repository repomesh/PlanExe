# Split mcp_cloud/http_server.py — Design Spec

**Date:** 2026-04-02
**Status:** Approved
**Tags:** `mcp_cloud`, `refactor`, `maintainability`

---

## Goal

Split `mcp_cloud/http_server.py` (1,439 lines) into four focused modules plus a thin re-export shim, following the same pattern used for the `frontend_multi_user/src/app.py` split (PR #476).

## Problem

`http_server.py` mixes four distinct concerns in one file: middleware (auth, CORS, rate limiting, body size), tool-to-HTTP bridging (request/response models, result normalization, FastMCP tool wrappers), route registration (all FastAPI endpoints + FastMCP tool registration + MCP prompts), and server bootstrapping (env vars, FastMCP/FastAPI creation, lifespan, `__main__`). This makes the file hard to review, test, and modify safely.

## Approach

Extract code into four new modules. `http_server.py` becomes a thin re-export file (~30 lines) that imports and re-exports all public symbols from the new modules, preserving backward compatibility for tests and the Dockerfile entry point (`python -m mcp_cloud.http_server`).

## New Module Layout

### 1. `middleware.py` (~550 lines)

All request-processing middleware and its supporting utilities:

- **CORS**: `_split_csv_env`, `CORS_ORIGINS`, `_allowed_cors_origin`, `_append_cors_headers`
- **Auth policy**: `PUBLIC_JSONRPC_METHODS_NO_AUTH`, `PUBLIC_TOOL_CALLS_NO_AUTH`, `_is_public_mcp_request_without_auth`
- **Request inspection**: `_extract_jsonrpc_methods_from_payload`, `_extract_jsonrpc_methods_from_request`, `_extract_jsonrpc_tools_call_names`, `_extract_rest_tools_call_name`
- **Auth errors/logging**: `_make_jsonrpc_auth_error`, `_log_auth_rejection`
- **API key handling**: `_normalize_api_key_value`, `_extract_api_key`, `_validate_api_key`, `_get_authenticated_user_api_key`, `_authenticated_user_api_key_ctx`, `_client_identifier`
- **Rate limiting**: `_rate_lock`, `_rate_buckets`, `_download_rate_buckets`, `_enforce_rate_limit`, `_enforce_download_rate_limit`, `_sweep_rate_buckets`, rate limit constants
- **Body size**: `_enforce_body_size`, `MAX_BODY_BYTES`
- **Download token check**: `_has_valid_download_token`
- **Request origin**: `_request_origin`
- **Main middleware function**: `enforce_api_key`
- **ASGI middleware**: `_NormalizeMcpPath`

Imports from `server_boot.py`: `AUTH_REQUIRED`, `REQUIRED_API_KEY`.

### 2. `tool_http_bridge.py` (~230 lines)

MCP tool wrappers and result normalization:

- **Request/response models**: `MCPToolCallRequest`, `MCPToolCallResponse`
- **Content helpers**: `extract_text_content`, `_parse_error_from_text`, `_normalize_tool_result`
- **Type aliases**: `ModelProfileInput`, `ResultArtifactInput`
- **Tool wrapper functions**: `plan_create`, `plan_status`, `plan_stop`, `plan_retry`, `plan_resume`, `plan_file_info`, `example_prompts`, `model_profiles`, `example_plans`, `plan_list`, `send_feedback`
- **Registry caller**: `call_tool_via_registry`

Imports `_get_authenticated_user_api_key` from `middleware.py`.

### 3. `route_registration.py` (~350 lines)

FastMCP tool registration, MCP prompts, and all FastAPI route handlers:

- **Tool registration**: `_register_tools`
- **MCP prompts**: `getting_started`, `plan_a_project`
- **CORS/HEAD handlers**: `options_mcp`, `head_mcp_trailing_slash`
- **REST tool endpoint**: `call_tool` (POST `/mcp/tools/call`)
- **Tools list endpoint**: `list_tools` (GET `/mcp/tools`)
- **Download endpoint**: `download_report`
- **SSE endpoint**: `sse_plan_progress`
- **Health/metadata**: `healthcheck`, `root`, `mcp_server_card`, `glama_connector_metadata`, `llms_txt`, `llm_txt`, `robots_txt`, `_llms_txt_path`

Accepts the FastAPI `app` and `fastmcp_server` instances as parameters via a `register_routes(app, fastmcp_server)` function, rather than importing globals.

### 4. `server_boot.py` (~120 lines)

Configuration, server object creation, and lifespan:

- **Startup logging**: `_startup_log`, `_DEBUG_STARTUP`
- **Imports and .env loading**
- **All env var constants**: `SERVER_VERSION`, `HTTP_HOST`, `HTTP_PORT`, `REQUIRED_API_KEY`, `GLAMA_MAINTAINER_EMAIL`, `AUTH_REQUIRED`
- **Auth secret validation**: calls to `validate_api_key_secret`, `validate_download_token_secret`
- **FastMCP server creation**: `fastmcp_server` instance + `_register_tools` call
- **FastAPI app creation**: `app` instance with lifespan, CORS middleware, `_NormalizeMcpPath`
- **Lifespan**: `_lifespan` context manager
- **FastAPI dependency**: `_get_fastmcp`
- **Route registration**: calls `register_routes(app, fastmcp_server)`
- **FastMCP mount**: `app.mount("/mcp", fastmcp_http_app)`
- **`__main__` block**: uvicorn startup

### 5. `http_server.py` (~30 lines, re-export shim)

Thin backward-compatibility module:

- Imports and re-exports all public symbols from the four new modules
- Preserves `python -m mcp_cloud.http_server` entry point (delegates to `server_boot`)
- Preserves `import mcp_cloud.http_server as http_server` in tests

## Backward Compatibility

### Test imports preserved

Tests use `import mcp_cloud.http_server as http_server` and then access symbols like `http_server._normalize_api_key_value`, `http_server._split_csv_env`, `http_server.fastmcp_server`, `http_server.app`, etc. The re-export shim ensures all these continue to work without test changes.

### Dockerfile entry point preserved

`CMD ["python", "-m", "mcp_cloud.http_server"]` continues to work because `http_server.py` imports `app` from `server_boot` and the `__main__` block is preserved.

### AGENTS.md update

The module map in `mcp_cloud/AGENTS.md` will be updated to reflect the new files and their responsibilities.

## What does NOT change

- No new dependencies
- No behavioral changes — identical middleware stack, identical routes, identical tool registration
- No test modifications needed (re-export shim handles it)
- No changes to any other `mcp_cloud/*.py` files
- The import graph from `AGENTS.md` stays the same at the boundary level

## Risks

1. **Module-level side effects during import**: `http_server.py` currently runs env parsing, .env loading, logging setup, and secret validation at import time. These must happen in `server_boot.py` and execute before any other module tries to use the values. Mitigation: `middleware.py` and `route_registration.py` import constants from `server_boot.py`.
2. **Circular imports**: `middleware.py` needs `AUTH_REQUIRED` from `server_boot.py`, and `server_boot.py` needs `enforce_api_key` from `middleware.py`. Mitigation: `server_boot.py` imports from `middleware.py` after defining constants, and `middleware.py` imports only constants (not app/server objects) from `server_boot.py`.
3. **Test fragility**: Tests access private symbols via `http_server._foo`. Mitigation: re-export shim forwards everything.
