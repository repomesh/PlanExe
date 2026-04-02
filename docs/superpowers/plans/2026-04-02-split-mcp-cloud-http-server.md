# Split mcp_cloud/http_server.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 1,439-line `mcp_cloud/http_server.py` into four focused modules plus a thin re-export shim, preserving all behavior and backward compatibility.

**Architecture:** Extract by concern into `middleware.py` (auth, CORS, rate limiting, body size), `tool_http_bridge.py` (request/response models, result normalization, tool wrappers), `route_registration.py` (all FastAPI/FastMCP route handlers), and `server_boot.py` (config, server creation, lifespan, entry point). `http_server.py` becomes a re-export shim so existing tests and the Dockerfile entry point continue to work unchanged.

**Tech Stack:** Python, FastAPI, FastMCP, Pydantic

**Spec:** `docs/superpowers/specs/2026-04-02-split-mcp-cloud-http-server-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `mcp_cloud/server_boot.py` | Create | Config constants, env parsing, FastMCP/FastAPI creation, lifespan, middleware wiring, route registration, `__main__` |
| `mcp_cloud/middleware.py` | Create | CORS, auth, rate limiting, body size, request inspection, download token check, `enforce_api_key`, `_NormalizeMcpPath` |
| `mcp_cloud/tool_http_bridge.py` | Create | Request/response models, content extraction, result normalization, tool wrapper functions, `call_tool_via_registry` |
| `mcp_cloud/route_registration.py` | Create | `register_routes()` function containing all FastAPI route handlers, FastMCP tool registration, MCP prompts |
| `mcp_cloud/http_server.py` | Rewrite | Thin re-export shim (~30 lines) |
| `mcp_cloud/AGENTS.md` | Modify | Update module map and import graph |
| `docs/proposals/131-codebase-cleanliness-remediation-roadmap.md` | Modify | Mark http_server.py split as done |

---

### Task 1: Create feature branch

- [ ] **Step 1: Create and switch to new branch**

Run: `git checkout -b split-mcp-cloud-http-server`

- [ ] **Step 2: Verify clean state**

Run: `git status`
Expected: clean working tree on `split-mcp-cloud-http-server`

---

### Task 2: Create `server_boot.py`

This is the foundation module. It owns all configuration constants, env var parsing, server object creation, and the application lifespan. Other modules import constants from here.

**Files:**
- Create: `mcp_cloud/server_boot.py`

- [ ] **Step 1: Create `server_boot.py`**

Write the file with the following content. This is lines 1-120 and 873-972 and 1427-1439 of the original `http_server.py`, plus the assembly logic that currently lives at module level.

```python
"""
PlanExe MCP Cloud — server bootstrap

Configuration constants, FastMCP / FastAPI creation, and application lifespan.
This module is the canonical source for all env-var-derived settings.
"""
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager, suppress
from typing import Any, Optional

# Early startup logging — gated behind PLANEXE_DEBUG_STARTUP so Railway
# deployments stay quiet unless explicitly opted in.
_DEBUG_STARTUP = os.environ.get("PLANEXE_DEBUG_STARTUP", "").strip().lower() in ("1", "true", "yes")


def _startup_log(msg: str) -> None:
    """Emit a startup breadcrumb to stderr when PLANEXE_DEBUG_STARTUP is set."""
    if _DEBUG_STARTUP:
        print(f"[startup] {msg}", file=sys.stderr, flush=True)


_startup_log("server_boot.py: begin imports")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

_startup_log("server_boot.py: 3rd-party imports done")

from mcp_cloud.dotenv_utils import load_planexe_dotenv
_dotenv_loaded, _dotenv_paths = load_planexe_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
if not _dotenv_loaded:
    logger.warning(
        "No .env file found; searched: %s",
        ", ".join(str(path) for path in _dotenv_paths),
    )

_startup_log("server_boot.py: about to import mcp_cloud.app (triggers db_setup)")
from mcp_cloud.app import (
    PLANEXE_SERVER_INSTRUCTIONS,
    TOOL_DEFINITIONS,
)
_startup_log("server_boot.py: mcp_cloud.app imported OK")
from mcp_cloud.auth import validate_api_key_secret
from mcp_cloud.download_tokens import validate_download_token_secret
_startup_log("server_boot.py: auth + download_tokens imported OK")

# ---------------------------------------------------------------------------
# Configuration constants (all derived from environment variables)
# ---------------------------------------------------------------------------
SERVER_VERSION = "1.0.1"

REQUIRED_API_KEY = os.environ.get("PLANEXE_MCP_API_KEY")

HTTP_HOST = os.environ.get("PLANEXE_MCP_HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("PORT") or os.environ.get("PLANEXE_MCP_HTTP_PORT", "8001"))
MAX_BODY_BYTES = int(os.environ.get("PLANEXE_MCP_MAX_BODY_BYTES", "1048576"))
RATE_LIMIT_REQUESTS = int(os.environ.get("PLANEXE_MCP_RATE_LIMIT", "60"))
RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("PLANEXE_MCP_RATE_WINDOW_SECONDS", "60"))
DOWNLOAD_RATE_LIMIT_REQUESTS = int(os.environ.get("PLANEXE_MCP_DOWNLOAD_RATE_LIMIT", "10"))
DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("PLANEXE_MCP_DOWNLOAD_RATE_WINDOW_SECONDS", "60"))
GLAMA_MAINTAINER_EMAIL = os.environ.get(
    "PLANEXE_MCP_GLAMA_MAINTAINER_EMAIL",
    "neoneye@gmail.com",
).strip()


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid boolean for %s=%r. Using default=%s", name, raw_value, default)
    return default


AUTH_REQUIRED = _parse_bool_env("PLANEXE_MCP_REQUIRE_AUTH", default=True)

if AUTH_REQUIRED:
    validate_api_key_secret()
    validate_download_token_secret()


def _split_csv_env(value: Optional[str]) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    if not raw:
        return []

    values: list[str]
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            values = [str(item) for item in parsed]
        else:
            values = raw.split(",")
    else:
        values = raw.split(",")

    origins: list[str] = []
    for item in values:
        normalized = str(item).strip()
        if not normalized:
            continue
        if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
            normalized = normalized[1:-1].strip()
        if normalized:
            origins.append(normalized)
    return origins


CORS_ORIGINS = _split_csv_env(os.environ.get("PLANEXE_MCP_CORS_ORIGINS"))
if not CORS_ORIGINS:
    if AUTH_REQUIRED:
        CORS_ORIGINS = [
            "https://mcp.planexe.org",
            "https://home.planexe.org",
        ]
    else:
        CORS_ORIGINS = ["*"]
        logger.info("CORS wildcard enabled (PLANEXE_MCP_REQUIRE_AUTH=false)")


# ---------------------------------------------------------------------------
# FastMCP server creation
# ---------------------------------------------------------------------------
_startup_log("server_boot.py: creating FastMCP server")

fastmcp_server = FastMCP(
    name="planexe-mcp-server",
    instructions=PLANEXE_SERVER_INSTRUCTIONS,
    host=HTTP_HOST,
    port=HTTP_PORT,
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
)

# Tool registration and MCP prompts are applied by route_registration.
from mcp_cloud.route_registration import register_routes, register_tools_and_prompts
register_tools_and_prompts(fastmcp_server)

fastmcp_http_app = fastmcp_server.streamable_http_app()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def _get_fastmcp(request: Request) -> FastMCP:
    fastmcp_server = getattr(request.app.state, "fastmcp_server", None)
    if fastmcp_server is None:
        raise HTTPException(status_code=503, detail="mcp_cloud not initialized")
    return fastmcp_server


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def _lifespan(app: FastAPI):
    from mcp_cloud.middleware import _sweep_rate_buckets
    app.state.fastmcp_server = fastmcp_server
    stop_event = asyncio.Event()
    sweeper_task = asyncio.create_task(_sweep_rate_buckets(stop_event))
    try:
        async with fastmcp_server.session_manager.run():
            yield
    finally:
        stop_event.set()
        sweeper_task.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper_task


# ---------------------------------------------------------------------------
# FastAPI app creation + middleware wiring
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PlanExe – AI Project Planning",
    description="MCP server that generates strategic project-plan drafts from a natural-language prompt",
    version=SERVER_VERSION,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "HEAD", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Register all routes (must happen before mounting FastMCP sub-app).
register_routes(app, fastmcp_server, _get_fastmcp)

# Mount the Streamable HTTP MCP endpoint AFTER the explicit /mcp/tools and
# /mcp/tools/call routes so that those routes take priority.
app.mount("/mcp", fastmcp_http_app)

# Apply middleware from middleware.py.
from mcp_cloud.middleware import apply_middleware
apply_middleware(app)

_startup_log("server_boot.py: app assembled OK")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting PlanExe MCP Cloud server on {HTTP_HOST}:{HTTP_PORT}")
    if AUTH_REQUIRED:
        logger.info(
            "Authentication required: UserApiKey (from home.planexe.org) or PLANEXE_MCP_API_KEY"
        )
    else:
        logger.warning("Authentication disabled via PLANEXE_MCP_REQUIRE_AUTH=false")

    uvicorn.run("mcp_cloud.server_boot:app", host=HTTP_HOST, port=HTTP_PORT, reload=False)
```

- [ ] **Step 2: Verify file was created**

Run: `wc -l mcp_cloud/server_boot.py`
Expected: approximately 190 lines

---

### Task 3: Create `middleware.py`

All request-processing middleware: CORS helpers, auth, rate limiting, body size, and the main `enforce_api_key` middleware function.

**Files:**
- Create: `mcp_cloud/middleware.py`

- [ ] **Step 1: Create `middleware.py`**

Write the file with the following content. This is lines 172-611, 975-1092, and 1137-1152 of the original `http_server.py`.

```python
"""
PlanExe MCP Cloud — HTTP middleware

CORS helpers, API-key authentication, rate limiting, body-size enforcement,
and the main ``enforce_api_key`` middleware function.
"""
import asyncio
import contextvars
import json
import logging
from collections import deque
from time import monotonic
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from mcp_cloud.http_utils import strip_redundant_content
from mcp_cloud.app import (
    clear_download_base_url,
    set_download_base_url,
    validate_download_token,
    _resolve_user_from_api_key,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Import configuration from server_boot (constants only — no app/server objects)
# ---------------------------------------------------------------------------
from mcp_cloud.server_boot import (
    AUTH_REQUIRED,
    CORS_ORIGINS,
    DOWNLOAD_RATE_LIMIT_REQUESTS,
    DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS,
    MAX_BODY_BYTES,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    REQUIRED_API_KEY,
)


# ---------------------------------------------------------------------------
# Auth policy sets
# ---------------------------------------------------------------------------
PUBLIC_JSONRPC_METHODS_NO_AUTH = {
    "initialize",
    "notifications/initialized",
    "tools/list",
    "prompts/list",
    "prompts/get",
    "resources/list",
    "resources/templates/list",
    "ping",
}
PUBLIC_TOOL_CALLS_NO_AUTH = {
    "example_plans",
    "example_prompts",
    "model_profiles",
}


# ---------------------------------------------------------------------------
# CORS helpers
# ---------------------------------------------------------------------------
def _allowed_cors_origin(request: Request) -> Optional[str]:
    origin = request.headers.get("origin")
    if not origin:
        return None
    if "*" in CORS_ORIGINS:
        return "*"
    if origin in CORS_ORIGINS:
        return origin
    return None


def _append_cors_headers(request: Request, response: Response) -> Response:
    """Ensure browser clients receive CORS headers even on early error responses."""
    allow_origin = _allowed_cors_origin(request)
    if not allow_origin:
        return response

    headers = response.headers
    headers.setdefault("Access-Control-Allow-Origin", allow_origin)
    headers.setdefault("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")

    request_headers = request.headers.get("access-control-request-headers")
    if request_headers:
        headers.setdefault("Access-Control-Allow-Headers", request_headers)
    else:
        headers.setdefault("Access-Control-Allow-Headers", "*")

    if allow_origin != "*":
        existing_vary = headers.get("Vary")
        if existing_vary:
            vary_values = [item.strip() for item in existing_vary.split(",") if item.strip()]
            if "Origin" not in vary_values:
                vary_values.append("Origin")
            headers["Vary"] = ", ".join(vary_values)
        else:
            headers["Vary"] = "Origin"

    return response


# ---------------------------------------------------------------------------
# JSON-RPC request inspection
# ---------------------------------------------------------------------------
def _extract_jsonrpc_methods_from_payload(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        method = payload.get("method")
        return [method] if isinstance(method, str) else []
    if isinstance(payload, list):
        methods: list[str] = []
        for item in payload:
            if isinstance(item, dict):
                method = item.get("method")
                if isinstance(method, str):
                    methods.append(method)
        return methods
    return []


async def _extract_jsonrpc_methods_from_request(request: Request) -> list[str]:
    try:
        body = await request.body()
        if not body:
            return []
        payload = json.loads(body)
    except Exception:
        return []
    return _extract_jsonrpc_methods_from_payload(payload)


def _extract_jsonrpc_tools_call_names(payload: Any) -> list[str]:
    items = payload if isinstance(payload, list) else [payload]
    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        method = item.get("method")
        if method != "tools/call":
            continue
        params = item.get("params")
        if isinstance(params, dict):
            name = params.get("name")
            if isinstance(name, str):
                names.append(name)
    return names


def _extract_rest_tools_call_name(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        name = payload.get("tool")
        return name if isinstance(name, str) else None
    return None


# ---------------------------------------------------------------------------
# Public request detection
# ---------------------------------------------------------------------------
async def _is_public_mcp_request_without_auth(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()

    if path == "/mcp" and method in ("GET", "HEAD", "POST"):
        return True
    if path == "/mcp/" and method in ("GET", "HEAD"):
        return True

    if path == "/mcp/tools" and method == "GET":
        return True

    if path == "/mcp/tools/call" and method == "POST":
        try:
            body = await request.body()
            payload = json.loads(body) if body else {}
        except Exception:
            return False
        tool_name = _extract_rest_tools_call_name(payload)
        return tool_name in PUBLIC_TOOL_CALLS_NO_AUTH

    if path in ("/mcp", "/mcp/") and method == "POST":
        methods = await _extract_jsonrpc_methods_from_request(request)
        if not methods:
            return False
        for m in methods:
            if m in PUBLIC_JSONRPC_METHODS_NO_AUTH:
                continue
            if m == "tools/call":
                try:
                    body = await request.body()
                    payload = json.loads(body) if body else {}
                except Exception:
                    return False
                tool_names = _extract_jsonrpc_tools_call_names(payload)
                if all(tn in PUBLIC_TOOL_CALLS_NO_AUTH for tn in tool_names):
                    continue
                return False
            return False
        return True

    return False


# ---------------------------------------------------------------------------
# Auth error handling & logging
# ---------------------------------------------------------------------------
async def _make_jsonrpc_auth_error(request: Request, detail: str) -> JSONResponse:
    request_id = None
    try:
        body = await request.body()
        if body:
            payload = json.loads(body)
            if isinstance(payload, dict):
                request_id = payload.get("id")
            elif isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict) and "id" in item:
                        request_id = item["id"]
                        break
    except Exception:
        pass

    return JSONResponse(
        status_code=200,
        content={
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": detail},
            "id": request_id,
        },
    )


async def _log_auth_rejection(request: Request, reason: str) -> None:
    methods_info = ""
    try:
        methods = await _extract_jsonrpc_methods_from_request(request)
        if methods:
            methods_info = f", jsonrpc_methods={methods}"
    except Exception:
        pass
    logger.warning(
        "Auth rejected: %s (method=%s path=%s ip=%s ua=%s%s)",
        reason, request.method, request.url.path,
        request.client.host if request.client else "?",
        request.headers.get("user-agent", "?"),
        methods_info,
    )


# ---------------------------------------------------------------------------
# API key extraction & validation
# ---------------------------------------------------------------------------
_rate_lock = asyncio.Lock()
_rate_buckets: dict[str, deque[float]] = {}
_download_rate_buckets: dict[str, deque[float]] = {}
_authenticated_user_api_key_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_authenticated_user_api_key_ctx", default=None,
)


def _normalize_api_key_value(raw_value: Optional[str]) -> Optional[str]:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None

    header_prefixes = (
        "x-api-key:",
        "api-key:",
        "api_key:",
        "authorization:",
    )
    lower_val = value.lower()
    for prefix in header_prefixes:
        if lower_val.startswith(prefix):
            value = value[len(prefix):].strip()
            break

    scheme_prefixes = ("bearer ", "token ")
    lower_val = value.lower()
    for prefix in scheme_prefixes:
        if lower_val.startswith(prefix):
            value = value[len(prefix):].strip()
            break

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()

    return value if value else None


def _extract_api_key(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return _normalize_api_key_value(parts[1])

    for header_name in ("x-api-key", "api-key", "api_key", "x_api_key"):
        key_value = request.headers.get(header_name)
        if key_value:
            return _normalize_api_key_value(key_value)

    for param_name in ("X-API-Key", "api_key", "api-key"):
        key_value = request.query_params.get(param_name)
        if key_value:
            return _normalize_api_key_value(key_value)

    return None


async def _validate_api_key(request: Request) -> Optional[JSONResponse]:
    api_key = _extract_api_key(request)

    if not AUTH_REQUIRED:
        if api_key:
            user = await asyncio.to_thread(_resolve_user_from_api_key, api_key)
            if user is None:
                await _log_auth_rejection(request, "Invalid API key (auth not required, but provided key is invalid)")
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
            _authenticated_user_api_key_ctx.set(api_key)
        return None

    if not api_key:
        await _log_auth_rejection(request, "Missing API key")
        return JSONResponse(
            status_code=401,
            content={
                "detail": "API key required. Set the X-API-Key header to your API key. Obtain an api key at home.planexe.org"
            },
        )

    if REQUIRED_API_KEY and api_key == REQUIRED_API_KEY:
        _authenticated_user_api_key_ctx.set(api_key)
        return None

    user = await asyncio.to_thread(_resolve_user_from_api_key, api_key)
    if user is None:
        await _log_auth_rejection(request, "Invalid API key")
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

    _authenticated_user_api_key_ctx.set(api_key)
    return None


def _get_authenticated_user_api_key() -> Optional[str]:
    return _authenticated_user_api_key_ctx.get()


def _client_identifier(request: Request) -> str:
    api_key = _get_authenticated_user_api_key()
    if api_key:
        return f"key:{api_key}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
async def _enforce_rate_limit(request: Request) -> Optional[JSONResponse]:
    if RATE_LIMIT_REQUESTS <= 0:
        return None
    path = request.url.path
    if path not in ("/mcp/tools/call", "/mcp", "/mcp/"):
        return None

    client_id = _client_identifier(request)
    now = monotonic()
    async with _rate_lock:
        bucket = _rate_buckets.setdefault(client_id, deque())
        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        bucket.append(now)
    return None


async def _enforce_download_rate_limit(request: Request) -> Optional[JSONResponse]:
    if DOWNLOAD_RATE_LIMIT_REQUESTS <= 0:
        return None
    if not request.url.path.startswith("/download"):
        return None

    client_id = _client_identifier(request)
    now = monotonic()
    async with _rate_lock:
        bucket = _download_rate_buckets.setdefault(client_id, deque())
        while bucket and now - bucket[0] > DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= DOWNLOAD_RATE_LIMIT_REQUESTS:
            return JSONResponse(status_code=429, content={"detail": "Download rate limit exceeded"})
        bucket.append(now)
    return None


async def _sweep_rate_buckets(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RATE_LIMIT_WINDOW_SECONDS)
            break
        except asyncio.TimeoutError:
            pass
        now = monotonic()
        async with _rate_lock:
            for buckets in (_rate_buckets, _download_rate_buckets):
                stale_keys = [k for k, v in buckets.items() if not v or now - v[-1] > RATE_LIMIT_WINDOW_SECONDS]
                for k in stale_keys:
                    del buckets[k]


# ---------------------------------------------------------------------------
# Body size enforcement
# ---------------------------------------------------------------------------
async def _enforce_body_size(request: Request) -> Optional[JSONResponse]:
    if request.method != "POST":
        return None
    path = request.url.path
    if path not in ("/mcp/tools/call", "/mcp", "/mcp/"):
        return None

    content_length_str = request.headers.get("content-length")
    if content_length_str is not None:
        try:
            content_length = int(content_length_str)
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        if content_length > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large (max {MAX_BODY_BYTES} bytes)"},
            )
    elif path == "/mcp/tools/call":
        return JSONResponse(
            status_code=411,
            content={"detail": "Content-Length header required"},
        )

    return None


# ---------------------------------------------------------------------------
# Download token & request origin helpers
# ---------------------------------------------------------------------------
def _request_origin(request: Request) -> str:
    """Return externally visible scheme+host, honoring reverse-proxy headers."""
    parsed = urlparse(str(request.base_url))
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    forwarded_host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else parsed.scheme
    netloc = forwarded_host or request.headers.get("Host") or parsed.netloc
    return f"{scheme}://{netloc}"


def _has_valid_download_token(request: Request) -> bool:
    """Return True when the request carries a valid signed download token."""
    token = request.query_params.get("token")
    if not token:
        return False
    parts = request.url.path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "download":
        return False
    plan_id, filename = parts[1], parts[2]
    return validate_download_token(token, plan_id, filename)


# ---------------------------------------------------------------------------
# ASGI path normalization middleware
# ---------------------------------------------------------------------------
class _NormalizeMcpPath:
    """ASGI middleware: rewrite ``/mcp`` → ``/mcp/`` at the scope level.

    Smithery (and possibly other registries) POST to ``/mcp`` but refuse to
    follow 307 redirects.  By rewriting the path *before* routing, the mounted
    FastMCP sub-app receives the request directly — no HTTP redirect needed.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Main HTTP middleware
# ---------------------------------------------------------------------------
async def enforce_api_key(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.method != "OPTIONS" and (
        request.url.path.startswith("/mcp") or request.url.path.startswith("/download")
    ):
        is_public = await _is_public_mcp_request_without_auth(request)

        is_mcp_streamable = request.url.path in ("/mcp", "/mcp/")

        async def _check_auth() -> Optional[Response]:
            """Validate API key; wrap errors as JSON-RPC for Streamable HTTP."""
            err = await _validate_api_key(request)
            if not err:
                return None
            if is_mcp_streamable:
                detail = (err.body or b"").decode(errors="replace")
                try:
                    detail = json.loads(detail).get("detail", detail)
                except Exception:
                    pass
                err = await _make_jsonrpc_auth_error(request, detail)
            return _append_cors_headers(request, err)

        if is_public and _extract_api_key(request):
            blocked = await _check_auth()
            if blocked:
                return blocked

        if not is_public:
            is_tokenized_download = (
                request.url.path.startswith("/download")
                and _has_valid_download_token(request)
            )
            if not is_tokenized_download:
                blocked = await _check_auth()
                if blocked:
                    return blocked

    error_response = await _enforce_body_size(request)
    if error_response:
        return _append_cors_headers(request, error_response)

    error_response = await _enforce_rate_limit(request)
    if error_response:
        return _append_cors_headers(request, error_response)

    error_response = await _enforce_download_rate_limit(request)
    if error_response:
        return _append_cors_headers(request, error_response)

    if request.url.path.startswith("/mcp"):
        set_download_base_url(_request_origin(request))
    try:
        response = await call_next(request)
    finally:
        _authenticated_user_api_key_ctx.set(None)
        if request.url.path.startswith("/mcp"):
            clear_download_base_url()
    if request.url.path.startswith("/mcp"):
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            body = getattr(response, "body", None)
            if body:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    return response
                stripped_payload, changed = strip_redundant_content(payload)
                if changed:
                    headers = dict(response.headers)
                    headers.pop("content-length", None)
                    return JSONResponse(
                        status_code=response.status_code,
                        content=stripped_payload,
                        headers=headers,
                        background=response.background,
                    )
    return _append_cors_headers(request, response)


# ---------------------------------------------------------------------------
# Public API: called by server_boot to wire middleware into the FastAPI app
# ---------------------------------------------------------------------------
def apply_middleware(app: Any) -> None:
    """Register middleware on the FastAPI app. Called by server_boot after routes are mounted."""
    app.middleware("http")(enforce_api_key)
    # Rewrite /mcp → /mcp/ at the ASGI level so clients that refuse to follow
    # 307 redirects (e.g. Smithery) still reach the mounted FastMCP app.
    # Added last so it becomes the outermost middleware (runs first).
    app.add_middleware(_NormalizeMcpPath)
```

- [ ] **Step 2: Verify file was created**

Run: `wc -l mcp_cloud/middleware.py`
Expected: approximately 430 lines

---

### Task 4: Create `tool_http_bridge.py`

Request/response models, result normalization, and all FastMCP tool wrapper functions.

**Files:**
- Create: `mcp_cloud/tool_http_bridge.py`

- [ ] **Step 1: Create `tool_http_bridge.py`**

Write the file with the following content. This is lines 613-821 and 1094-1113 of the original `http_server.py`.

```python
"""
PlanExe MCP Cloud — tool HTTP bridge

Pydantic request/response models, MCP result normalization, and thin
async wrapper functions that connect FastMCP tool registrations to the
handler implementations in ``mcp_cloud.app``.
"""
import json
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ContentBlock, TextContent

from mcp_cloud.app import (
    handle_plan_create,
    handle_plan_list,
    handle_model_profiles,
    handle_plan_status,
    handle_plan_retry,
    handle_plan_resume,
    handle_plan_stop,
    handle_plan_file_info,
    handle_example_prompts,
    handle_example_plans,
    handle_send_feedback,
)
from mcp_cloud.middleware import _get_authenticated_user_api_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class MCPToolCallRequest(BaseModel):
    tool: str
    arguments: dict[str, Any]
    metadata: Optional[dict[str, Any]] = Field(default=None)


class MCPToolCallResponse(BaseModel):
    content: list[dict[str, Any]]
    error: Optional[dict[str, Any]] = Field(default=None)


# ---------------------------------------------------------------------------
# Content extraction & error parsing
# ---------------------------------------------------------------------------
def extract_text_content(text_contents: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    items = text_contents if isinstance(text_contents, list) else [text_contents]
    for item in items:
        if hasattr(item, "text"):
            results.append({"type": "text", "text": item.text})
        elif isinstance(item, dict):
            results.append(item)
        else:
            results.append({"type": "text", "text": str(item)})
    return results


def _parse_error_from_text(text: str) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        if "error" in data:
            return data["error"] if isinstance(data["error"], dict) else {"message": str(data["error"])}
        if "message" in data and any(
            k in data for k in ("code", "status", "status_code")
        ):
            return data
    return None


def _normalize_tool_result(result: Any) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    content: list[dict[str, Any]] = []
    error: Optional[dict[str, Any]] = None

    if isinstance(result, CallToolResult):
        for block in result.content or []:
            if isinstance(block, TextContent):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ContentBlock):
                content.append({"type": "text", "text": str(block)})
            elif isinstance(block, dict):
                content.append(block)
            else:
                content.append({"type": "text", "text": str(block)})
        if result.isError:
            for item in content:
                if item.get("type") == "text":
                    parsed = _parse_error_from_text(item.get("text", ""))
                    if parsed:
                        error = parsed
                        break
            if not error:
                error = {"message": "Tool returned an error"}
    elif isinstance(result, ContentBlock):
        content = extract_text_content(result)
    elif isinstance(result, list):
        content = extract_text_content(result)
    elif isinstance(result, dict):
        content = [result]
    else:
        content = [{"type": "text", "text": str(result)}]

    if not error:
        for item in content:
            if item.get("type") == "text":
                text_value = item.get("text", "")
                if isinstance(text_value, str):
                    parsed = _parse_error_from_text(text_value)
                    if parsed:
                        error = parsed
                        break

    return content, error


# ---------------------------------------------------------------------------
# Type aliases for tool parameters
# ---------------------------------------------------------------------------
ModelProfileInput = Literal["baseline", "premium", "frontier", "custom"]
ResultArtifactInput = Literal["report", "zip"]


# ---------------------------------------------------------------------------
# FastMCP tool wrapper functions
# ---------------------------------------------------------------------------
async def plan_create(
    prompt: str,
    model_profile: ModelProfileInput = "baseline",
    start_date: Optional[str] = None,
) -> CallToolResult:
    arguments: dict[str, Any] = {
        "prompt": prompt,
        "model_profile": model_profile,
    }
    if start_date:
        arguments["start_date"] = start_date
    authenticated_user_api_key = _get_authenticated_user_api_key()
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_plan_create(arguments)


async def plan_status(plan_id: str) -> CallToolResult:
    return await handle_plan_status({"plan_id": plan_id})


async def plan_stop(plan_id: str) -> CallToolResult:
    return await handle_plan_stop({"plan_id": plan_id})


async def plan_retry(
    plan_id: str,
    model_profile: ModelProfileInput = "baseline",
) -> CallToolResult:
    arguments: dict[str, Any] = {
        "plan_id": plan_id,
        "model_profile": model_profile,
    }
    authenticated_user_api_key = _get_authenticated_user_api_key()
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_plan_retry(arguments)


async def plan_resume(
    plan_id: str,
    model_profile: ModelProfileInput = "baseline",
) -> CallToolResult:
    arguments: dict[str, Any] = {
        "plan_id": plan_id,
        "model_profile": model_profile,
    }
    authenticated_user_api_key = _get_authenticated_user_api_key()
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_plan_resume(arguments)


async def plan_file_info(
    plan_id: str,
    artifact: ResultArtifactInput = "report",
) -> CallToolResult:
    return await handle_plan_file_info({
        "plan_id": plan_id,
        "artifact": artifact,
    })


async def example_prompts() -> CallToolResult:
    return await handle_example_prompts({})


async def model_profiles() -> CallToolResult:
    return await handle_model_profiles({})


async def example_plans() -> CallToolResult:
    return await handle_example_plans({})


async def plan_list(limit: int = 10) -> CallToolResult:
    arguments: dict[str, Any] = {"limit": limit}
    authenticated_user_api_key = _get_authenticated_user_api_key()
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_plan_list(arguments)


async def send_feedback(
    category: str,
    message: str,
    plan_id: Optional[str] = None,
    rating: Optional[int] = None,
) -> CallToolResult:
    arguments: dict[str, Any] = {
        "category": category,
        "message": message,
    }
    if plan_id is not None:
        arguments["plan_id"] = plan_id
    if rating is not None:
        arguments["rating"] = rating
    authenticated_user_api_key = _get_authenticated_user_api_key()
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_send_feedback(arguments)


# ---------------------------------------------------------------------------
# Registry-based tool call (used by REST endpoint)
# ---------------------------------------------------------------------------
async def call_tool_via_registry(
    server: FastMCP,
    tool_name: str,
    arguments: dict[str, Any],
) -> MCPToolCallResponse:
    """Call tools via the FastMCP registry."""
    try:
        result = await server.call_tool(tool_name, arguments)
    except Exception as e:
        logger.error(f"Error calling tool {tool_name}: {e}", exc_info=True)
        return MCPToolCallResponse(
            content=[],
            error={
                "code": "INTERNAL_ERROR",
                "message": str(e)
            }
        )

    content, error = _normalize_tool_result(result)
    return MCPToolCallResponse(content=content, error=error)
```

- [ ] **Step 2: Verify file was created**

Run: `wc -l mcp_cloud/tool_http_bridge.py`
Expected: approximately 250 lines

---

### Task 5: Create `route_registration.py`

All FastAPI route handlers and FastMCP tool/prompt registration, exposed via `register_routes()` and `register_tools_and_prompts()`.

**Files:**
- Create: `mcp_cloud/route_registration.py`

- [ ] **Step 1: Create `route_registration.py`**

Write the file with the following content. This is lines 823-871, 890-931, 1116-1135, 1155-1202, 1215-1424 of the original `http_server.py`.

```python
"""
PlanExe MCP Cloud — route registration

FastMCP tool registration, MCP prompts, and all FastAPI route handlers.
Called by ``server_boot.py`` during application assembly.
"""
import asyncio
import logging
import os
from typing import Any, Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from mcp_cloud.app import (
    REPORT_CONTENT_TYPE,
    REPORT_FILENAME,
    TOOL_DEFINITIONS,
    ZIP_CONTENT_TYPE,
    ZIP_FILENAME,
    fetch_artifact_from_worker_plan,
    fetch_user_downloadable_zip,
    handle_plan_create,
    resolve_plan_by_id,
    validate_download_token,
)
from mcp_cloud.tool_http_bridge import (
    MCPToolCallRequest,
    MCPToolCallResponse,
    _normalize_tool_result,
    call_tool_via_registry,
    example_plans,
    example_prompts,
    model_profiles,
    plan_create,
    plan_file_info,
    plan_list,
    plan_resume,
    plan_retry,
    plan_status,
    plan_stop,
    send_feedback,
)
from mcp_cloud.middleware import _get_authenticated_user_api_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FastMCP tool registration
# ---------------------------------------------------------------------------
def _register_tools(server: FastMCP) -> None:
    handler_map = {
        "example_plans": example_plans,
        "example_prompts": example_prompts,
        "model_profiles": model_profiles,
        "plan_create": plan_create,
        "plan_status": plan_status,
        "plan_stop": plan_stop,
        "plan_retry": plan_retry,
        "plan_resume": plan_resume,
        "plan_file_info": plan_file_info,
        "plan_list": plan_list,
        "send_feedback": send_feedback,
    }
    for tool_def in TOOL_DEFINITIONS:
        handler = handler_map.get(tool_def.name)
        if handler is None:
            logger.warning("No HTTP handler registered for tool %s", tool_def.name)
            continue
        server.tool(
            name=tool_def.name,
            description=tool_def.description,
            annotations=ToolAnnotations(**tool_def.annotations) if tool_def.annotations else None,
        )(handler)

    # Inject the canonical outputSchema from TOOL_DEFINITIONS into each
    # FastMCP tool so that list_tools advertises the schema we control.
    for tool_def in TOOL_DEFINITIONS:
        schema = tool_def.output_schema
        if schema is None:
            continue
        if "oneOf" in schema:
            continue
        fastmcp_tool = server._tool_manager.get_tool(tool_def.name)
        if fastmcp_tool is None:
            continue
        fastmcp_tool.__dict__["output_schema"] = schema


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------
def _register_prompts(server: FastMCP) -> None:
    @server.prompt()
    def getting_started() -> str:
        """Quick-start guide for using PlanExe to create a project plan."""
        return (
            "You have access to PlanExe, an MCP server that generates strategic "
            "project-plan drafts from a natural-language prompt.\n\n"
            "To get started:\n"
            "1. Call the example_prompts tool to see what good prompts look like.\n"
            "2. Optionally call model_profiles to see available quality tiers.\n"
            "3. Draft a detailed prompt (300-800 words) covering: objective, scope, "
            "constraints, timeline, stakeholders, budget, and success criteria. "
            "Write it as flowing prose, not bullet lists.\n"
            "4. Show the draft to the user for approval. Iterate — the user may "
            "want to refine scope, add constraints, or adjust priorities. "
            "A few rounds of feedback typically produce the best plans.\n"
            "5. Once the user is satisfied, call plan_create with the approved prompt.\n"
            "6. Poll plan_status every 5 minutes until state is completed.\n"
            "7. Call plan_file_info to get the download URL for the HTML report.\n\n"
            "The report contains 20+ sections including executive summary, Gantt charts, "
            "risk analysis, SWOT, governance, investor pitch, and adversarial stress-tests."
        )

    @server.prompt()
    def plan_a_project(topic: str, location: str = "") -> str:
        """Draft a project plan for a given topic. Guides the agent through the full PlanExe workflow."""
        location_line = f"\nLocation/region: {location}\n" if location else ""
        return (
            f"The user wants to create a project plan about: {topic}\n"
            f"{location_line}\n"
            "Follow these steps:\n"
            "1. Call example_prompts to see baseline prompt quality and structure.\n"
            "2. Using those examples as inspiration, expand the user's topic into a "
            "detailed prompt of 300-800 words. Include: objective, scope, constraints, "
            "timeline, stakeholders, budget/resources, and success criteria. Write as "
            "flowing prose — weave specs and targets naturally into sentences.\n"
            "3. Present the draft prompt to the user and ask for approval or changes.\n"
            "4. Once approved, call plan_create with the prompt.\n"
            "5. Poll plan_status every 5 minutes (plan generation takes 10-20 minutes).\n"
            "6. When state is completed, call plan_file_info with artifact='report' "
            "and share the download URL with the user."
        )


def register_tools_and_prompts(server: FastMCP) -> None:
    """Register all MCP tools and prompts on the FastMCP server."""
    _register_tools(server)
    _register_prompts(server)


# ---------------------------------------------------------------------------
# FastAPI route handlers
# ---------------------------------------------------------------------------
def register_routes(
    app: FastAPI,
    fastmcp_server: FastMCP,
    get_fastmcp: Callable[..., FastMCP],
) -> None:
    """Register all HTTP route handlers on the FastAPI app.

    Must be called before ``app.mount("/mcp", ...)`` so that explicit routes
    like ``/mcp/tools`` and ``/mcp/tools/call`` take priority over the mounted
    FastMCP sub-app.
    """
    from mcp_cloud.server_boot import (
        AUTH_REQUIRED,
        GLAMA_MAINTAINER_EMAIL,
        REPORT_FILENAME,
        SERVER_VERSION,
    )

    # -- CORS / HEAD handlers for /mcp ------------------------------------

    @app.options("/mcp")
    @app.options("/mcp/")
    async def options_mcp() -> Response:
        """Handle CORS preflight for /mcp so browser-based tools (e.g. MCP Inspector) succeed."""
        return Response(status_code=200)

    @app.head("/mcp/")
    async def head_mcp_trailing_slash() -> Response:
        """Handle HEAD /mcp/ for health-check probes (e.g. Smithery scanner)."""
        return Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

    # -- REST tool call endpoint -------------------------------------------

    @app.post("/mcp/tools/call", response_model=MCPToolCallResponse)
    async def call_tool(
        payload: MCPToolCallRequest,
        fastmcp_server: FastMCP = Depends(get_fastmcp),
    ) -> MCPToolCallResponse:
        """Call an MCP tool by name with arguments."""
        arguments = dict(payload.arguments or {})
        if payload.tool in ("plan_create", "plan_list"):
            authenticated_user_api_key = _get_authenticated_user_api_key()
            if authenticated_user_api_key and not arguments.get("user_api_key"):
                arguments["user_api_key"] = authenticated_user_api_key

        if payload.tool == "plan_create":
            if isinstance(payload.metadata, dict):
                arguments["metadata"] = dict(payload.metadata)

            result = await handle_plan_create(arguments)
            content, error = _normalize_tool_result(result)
            return MCPToolCallResponse(content=content, error=error)

        return await call_tool_via_registry(fastmcp_server, payload.tool, arguments)

    # -- Tools list endpoint -----------------------------------------------

    @app.get("/mcp/tools")
    async def list_tools(fastmcp_server: FastMCP = Depends(get_fastmcp)) -> dict[str, Any]:
        """List all available MCP tools."""
        tools = await fastmcp_server.list_tools()
        sanitized = []
        for tool in tools:
            tool_entry = {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            if tool.title:
                tool_entry["title"] = tool.title
            if tool.outputSchema:
                tool_entry["outputSchema"] = tool.outputSchema
            if tool.annotations:
                tool_entry["annotations"] = tool.annotations
            if tool.icons:
                tool_entry["icons"] = tool.icons
            sanitized.append(tool_entry)
        return {"tools": sanitized}

    # -- Download endpoint -------------------------------------------------

    @app.get("/download/{plan_id}/{filename}")
    async def download_report(
        plan_id: str,
        filename: str,
        token: Optional[str] = None,
    ) -> Response:
        """Download the generated report HTML or zip for a plan."""
        if filename not in (REPORT_FILENAME, ZIP_FILENAME):
            raise HTTPException(status_code=404, detail="Report not found")
        if token is not None and not validate_download_token(token, plan_id, filename):
            raise HTTPException(status_code=401, detail="Invalid or expired download token")
        plan = await asyncio.to_thread(resolve_plan_by_id, plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        if filename == ZIP_FILENAME:
            content_bytes = await fetch_user_downloadable_zip(str(plan.id))
            if content_bytes is None:
                raise HTTPException(status_code=404, detail="Report not found")
            headers = {"Content-Disposition": f'attachment; filename="{plan_id}.zip"'}
            return Response(content=content_bytes, media_type=ZIP_CONTENT_TYPE, headers=headers)

        content_bytes = await fetch_artifact_from_worker_plan(str(plan.id), REPORT_FILENAME)
        if content_bytes is None:
            raise HTTPException(status_code=404, detail="Report not found")
        headers = {"Content-Disposition": f'inline; filename="{REPORT_FILENAME}"'}
        return Response(content=content_bytes, media_type=REPORT_CONTENT_TYPE, headers=headers)

    # -- SSE endpoint ------------------------------------------------------

    @app.get("/sse/plan/{plan_id}")
    async def sse_plan_progress(plan_id: str, request: Request) -> Response:
        """SSE endpoint that streams real-time plan progress updates."""
        from mcp_cloud.sse import (
            SSEConnectionLimitError,
            _track_sse_connection,
            plan_progress_stream,
        )

        client_ip = request.client.host if request.client else "unknown"

        try:
            async def event_generator():
                async with _track_sse_connection(client_ip):
                    disconnect_event = asyncio.Event()
                    async for event in plan_progress_stream(plan_id, disconnect_event):
                        if await request.is_disconnected():
                            disconnect_event.set()
                            break
                        yield event

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except SSEConnectionLimitError as exc:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "SSE_CONNECTION_LIMIT", "message": str(exc)}},
            )

    # -- Health & metadata endpoints ---------------------------------------

    @app.get("/healthcheck")
    def healthcheck() -> dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "planexe-mcp-cloud",
            "authentication_required": AUTH_REQUIRED,
        }

    @app.get("/")
    def root() -> dict[str, Any]:
        """Root endpoint with API information."""
        return {
            "service": "PlanExe – AI Project Planning",
            "description": "MCP server that generates rough-draft project plans from a natural-language prompt",
            "version": SERVER_VERSION,
            "endpoints": {
                "mcp": "/mcp",
                "tools": "/mcp/tools",
                "call": "/mcp/tools/call",
                "health": "/healthcheck",
                "mcp_server_card": "/.well-known/mcp/server-card.json",
                "glama_connector": "/.well-known/glama.json",
                "download": f"/download/{{plan_id}}/{REPORT_FILENAME}",
                "sse": "/sse/plan/{plan_id}",
                "llms_txt": "/llms.txt",
            },
            "documentation": "See /docs for OpenAPI documentation",
            "authentication": (
                "Required: X-API-Key (Obtain an api key at home.planexe.org)"
                if AUTH_REQUIRED
                else "Disabled (PLANEXE_MCP_REQUIRE_AUTH=false)"
            ),
        }

    def _llms_txt_path() -> str:
        repo_root = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(repo_root, "public", "llms.txt")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="llms.txt not found")
        return path

    @app.get("/.well-known/mcp/server-card.json")
    def mcp_server_card() -> dict[str, Any]:
        """Serve MCP Server Card for discovery (SEP-1649)."""
        return {
            "version": "1.0",
            "protocolVersion": "2025-06-18",
            "serverInfo": {
                "name": "planexe-mcp-server",
                "title": "PlanExe - AI Project Planning",
                "version": SERVER_VERSION,
            },
            "description": (
                "MCP server that generates strategic project-plan drafts from a "
                "natural-language prompt. Output is a self-contained interactive "
                "HTML report with 20+ sections including executive summary, "
                "interactive Gantt charts, risk analysis, SWOT, governance, "
                "investor pitch, and adversarial stress-test sections."
            ),
            "documentationUrl": "https://docs.planexe.org/",
            "transport": {
                "type": "streamable-http",
                "endpoint": "/mcp/",
            },
            "capabilities": {
                "tools": {},
            },
            "authentication": {
                "required": AUTH_REQUIRED,
                "schemes": ["api-key"],
            },
            "tools": ["dynamic"],
            "prompts": ["dynamic"],
            "resources": ["dynamic"],
        }

    @app.get("/.well-known/glama.json")
    def glama_connector_metadata() -> dict[str, Any]:
        """Serve Glama connector ownership metadata."""
        return {
            "$schema": "https://glama.ai/mcp/schemas/connector.json",
            "maintainers": [{"email": GLAMA_MAINTAINER_EMAIL}],
        }

    @app.get("/llms.txt")
    def llms_txt():
        """Serve llms.txt for AI agent discoverability."""
        return FileResponse(_llms_txt_path(), media_type="text/plain; charset=utf-8")

    @app.get("/llm.txt")
    def llm_txt() -> RedirectResponse:
        """Legacy alias that redirects to canonical /llms.txt."""
        return RedirectResponse(url="/llms.txt", status_code=308)

    @app.get("/robots.txt")
    def robots_txt() -> Response:
        """Allow crawler discovery of public MCP metadata endpoints."""
        content = (
            "User-agent: *\n"
            "Allow: /\n"
            "Sitemap: https://mcp.planexe.org/llms.txt\n"
        )
        return Response(content=content, media_type="text/plain; charset=utf-8")
```

- [ ] **Step 2: Verify file was created**

Run: `wc -l mcp_cloud/route_registration.py`
Expected: approximately 310 lines

---

### Task 6: Rewrite `http_server.py` as re-export shim

Replace the 1,439-line file with a thin backward-compatibility shim that re-exports all symbols tests and the Dockerfile entry point rely on.

**Files:**
- Modify: `mcp_cloud/http_server.py`

- [ ] **Step 1: Rewrite `http_server.py`**

Replace the entire file with:

```python
"""
PlanExe MCP Cloud — HTTP server (backward-compatibility re-export shim)

All implementation has moved to focused modules:
- server_boot.py     — config, FastMCP/FastAPI creation, lifespan, entry point
- middleware.py       — CORS, auth, rate limiting, body size, enforce_api_key
- tool_http_bridge.py — request/response models, result normalization, tool wrappers
- route_registration.py — FastMCP tool registration, MCP prompts, route handlers

This module re-exports public symbols so that existing tests and the
Dockerfile entry point (``python -m mcp_cloud.http_server``) continue
to work without modification.
"""

# --- server_boot exports (config, servers, lifespan) ----------------------
from mcp_cloud.server_boot import (  # noqa: F401
    AUTH_REQUIRED,
    CORS_ORIGINS,
    DOWNLOAD_RATE_LIMIT_REQUESTS,
    DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS,
    GLAMA_MAINTAINER_EMAIL,
    HTTP_HOST,
    HTTP_PORT,
    MAX_BODY_BYTES,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    REQUIRED_API_KEY,
    SERVER_VERSION,
    _parse_bool_env,
    _split_csv_env,
    _startup_log,
    app,
    fastmcp_server,
)

# --- middleware exports (auth, CORS, rate limiting) -----------------------
from mcp_cloud.middleware import (  # noqa: F401
    PUBLIC_JSONRPC_METHODS_NO_AUTH,
    PUBLIC_TOOL_CALLS_NO_AUTH,
    _NormalizeMcpPath,
    _allowed_cors_origin,
    _append_cors_headers,
    _authenticated_user_api_key_ctx,
    _client_identifier,
    _download_rate_buckets,
    _enforce_body_size,
    _enforce_download_rate_limit,
    _enforce_rate_limit,
    _extract_api_key,
    _extract_jsonrpc_methods_from_payload,
    _extract_jsonrpc_methods_from_request,
    _extract_jsonrpc_tools_call_names,
    _extract_rest_tools_call_name,
    _get_authenticated_user_api_key,
    _has_valid_download_token,
    _is_public_mcp_request_without_auth,
    _log_auth_rejection,
    _make_jsonrpc_auth_error,
    _normalize_api_key_value,
    _rate_buckets,
    _rate_lock,
    _request_origin,
    _sweep_rate_buckets,
    _validate_api_key,
    enforce_api_key,
)

# --- tool_http_bridge exports (models, wrappers, normalization) -----------
from mcp_cloud.tool_http_bridge import (  # noqa: F401
    MCPToolCallRequest,
    MCPToolCallResponse,
    ModelProfileInput,
    ResultArtifactInput,
    _normalize_tool_result,
    _parse_error_from_text,
    call_tool_via_registry,
    example_plans,
    example_prompts,
    extract_text_content,
    model_profiles,
    plan_create,
    plan_file_info,
    plan_list,
    plan_resume,
    plan_retry,
    plan_status,
    plan_stop,
    send_feedback,
)

# --- route_registration exports (for direct access) ----------------------
from mcp_cloud.route_registration import (  # noqa: F401
    register_routes,
    register_tools_and_prompts,
)

# --- Entry point (preserves `python -m mcp_cloud.http_server`) -----------
if __name__ == "__main__":
    from mcp_cloud.server_boot import HTTP_HOST, HTTP_PORT, AUTH_REQUIRED
    import logging
    import uvicorn

    logger = logging.getLogger(__name__)
    logger.info(f"Starting PlanExe MCP Cloud server on {HTTP_HOST}:{HTTP_PORT}")
    if AUTH_REQUIRED:
        logger.info(
            "Authentication required: UserApiKey (from home.planexe.org) or PLANEXE_MCP_API_KEY"
        )
    else:
        logger.warning("Authentication disabled via PLANEXE_MCP_REQUIRE_AUTH=false")

    uvicorn.run("mcp_cloud.server_boot:app", host=HTTP_HOST, port=HTTP_PORT, reload=False)
```

- [ ] **Step 2: Verify line count**

Run: `wc -l mcp_cloud/http_server.py`
Expected: approximately 100 lines

---

### Task 7: Run tests to verify backward compatibility

**Files:**
- Test: `mcp_cloud/tests/`

- [ ] **Step 1: Run the full mcp_cloud test suite**

Run from repo root (inside Docker or with appropriate env):
```bash
python -m pytest mcp_cloud/tests/ -v
```

Expected: all tests pass without modification. Key tests to watch:
- `test_auth_key_parsing.py` — accesses `http_server._normalize_api_key_value`, `http_server._extract_api_key`
- `test_cors_config.py` — accesses `http_server._split_csv_env`, `http_server._append_cors_headers`, `http_server._is_public_mcp_request_without_auth`
- `test_download_rate_limit.py` — accesses `http_server._download_rate_buckets`, `http_server._enforce_download_rate_limit`, `http_server.DOWNLOAD_RATE_LIMIT_REQUESTS`
- `test_http_server_routing.py` — accesses `http_server._NormalizeMcpPath`, `http_server.options_mcp`
- `test_tool_surface_consistency.py` — accesses `http_server.fastmcp_server`

- [ ] **Step 2: Fix any import errors**

If any test fails due to a missing re-export, add the missing symbol to `http_server.py`'s import list and re-run.

- [ ] **Step 3: Commit**

```bash
git add mcp_cloud/server_boot.py mcp_cloud/middleware.py mcp_cloud/tool_http_bridge.py mcp_cloud/route_registration.py mcp_cloud/http_server.py
git commit -m "Split mcp_cloud/http_server.py into four focused modules

Extract middleware.py (auth, CORS, rate limiting), tool_http_bridge.py
(request/response models, tool wrappers), route_registration.py (all
route handlers, tool registration), and server_boot.py (config, server
creation, lifespan). http_server.py becomes a re-export shim preserving
backward compatibility for tests and the Dockerfile entry point."
```

---

### Task 8: Update AGENTS.md

**Files:**
- Modify: `mcp_cloud/AGENTS.md`

- [ ] **Step 1: Update module map**

Add the four new modules to the module map table in `AGENTS.md`, and update the `http_server.py` row to note it is now a re-export shim.

Update the module map table to include:

| File | Purpose | Key exports |
|------|---------|-------------|
| `server_boot.py` | Config constants, FastMCP/FastAPI creation, lifespan, entry point | `app` (FastAPI), `fastmcp_server`, `SERVER_VERSION`, all env-var constants |
| `middleware.py` | CORS, auth, rate limiting, body size, `enforce_api_key` middleware | `enforce_api_key`, `apply_middleware`, `_get_authenticated_user_api_key` |
| `tool_http_bridge.py` | Pydantic request/response models, result normalization, FastMCP tool wrappers | `MCPToolCallRequest`, `MCPToolCallResponse`, tool wrapper functions |
| `route_registration.py` | FastMCP tool registration, MCP prompts, all FastAPI route handlers | `register_routes`, `register_tools_and_prompts` |
| `http_server.py` | Re-export shim for backward compatibility | All symbols from the four modules above |

- [ ] **Step 2: Update import graph**

Update the import graph section to reflect the new module structure:

```
http_server.py (re-export shim)
├── server_boot.py (config, app + server creation, lifespan)
│   ├── mcp_cloud.app (facade)
│   ├── mcp_cloud.auth (secret validation)
│   ├── mcp_cloud.download_tokens (secret validation)
│   ├── route_registration.py (register_routes, register_tools_and_prompts)
│   └── middleware.py (apply_middleware, _sweep_rate_buckets)
├── middleware.py (CORS, auth, rate limiting)
│   ├── server_boot.py (constants only)
│   ├── mcp_cloud.app (set/clear_download_base_url, validate_download_token, _resolve_user_from_api_key)
│   └── mcp_cloud.http_utils (strip_redundant_content)
├── tool_http_bridge.py (models, wrappers, normalization)
│   ├── mcp_cloud.app (handler functions)
│   └── middleware.py (_get_authenticated_user_api_key)
└── route_registration.py (routes, tool registration, prompts)
    ├── server_boot.py (constants)
    ├── mcp_cloud.app (handlers, constants)
    ├── tool_http_bridge.py (models, wrappers)
    └── middleware.py (_get_authenticated_user_api_key)
```

- [ ] **Step 3: Commit**

```bash
git add mcp_cloud/AGENTS.md
git commit -m "Update AGENTS.md: document http_server.py split into four modules"
```

---

### Task 9: Update remediation roadmap

**Files:**
- Modify: `docs/proposals/131-codebase-cleanliness-remediation-roadmap.md`

- [ ] **Step 1: Mark http_server.py split as done**

In Issue 1, fix step 2, add a **Done** marker:

Change:
```
2. Split `mcp_cloud/http_server.py` into `middleware`, `route_registration`, `tool_http_bridge`, and `server_boot`.
```
To:
```
2. ~~Split `mcp_cloud/http_server.py` into `middleware`, `route_registration`, `tool_http_bridge`, and `server_boot`.~~ **Done**: Split 1,439-line monolith into 4 focused modules + re-export shim.
```

- [ ] **Step 2: Mark Phase 2 step 2 as done**

Change:
```
2. Refactor `mcp_cloud/http_server.py` second because it sits on a public protocol boundary.
```
To:
```
2. ~~Refactor `mcp_cloud/http_server.py` second because it sits on a public protocol boundary.~~ **Done**.
```

- [ ] **Step 3: Update Success Metric 3**

Change:
```
3. `mcp_cloud/http_server.py` reduced to a focused HTTP assembly module rather than a mixed implementation file.
```
To:
```
3. ~~`mcp_cloud/http_server.py` reduced to a focused HTTP assembly module rather than a mixed implementation file.~~ **Done**: Split into `server_boot.py`, `middleware.py`, `tool_http_bridge.py`, `route_registration.py` + re-export shim.
```

- [ ] **Step 4: Commit**

```bash
git add docs/proposals/131-codebase-cleanliness-remediation-roadmap.md
git commit -m "Update proposal 131: mark mcp_cloud/http_server.py split as done"
```

---

### Task 10: Push and verify CI

- [ ] **Step 1: Push the branch**

```bash
git push -u origin split-mcp-cloud-http-server
```

- [ ] **Step 2: Wait for CI to pass**

Run: `gh pr checks` or monitor GitHub Actions.
Expected: lint, tests, typecheck all pass.

- [ ] **Step 3: Fix any CI failures**

If CI fails, fix the issue and push again. Common issues:
- Missing re-exports in `http_server.py`
- Import ordering (isort/ruff)
- Type annotation issues from moving code between modules
