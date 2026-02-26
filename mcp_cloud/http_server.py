"""
HTTP server wrapper for PlanExe MCP Cloud

Provides HTTP/JSON endpoints for MCP tool calls with API key authentication.
Supports deployment to Railway and other cloud platforms.
"""
import asyncio
import contextvars
import json
import logging
import os
import sys
from urllib.parse import urlparse
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from time import monotonic
from typing import Annotated, Any, Awaitable, Callable, Literal, Optional, Sequence

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ContentBlock, TextContent, ToolAnnotations

from mcp_cloud.http_utils import strip_redundant_content
from mcp_cloud.tool_models import (
    ModelProfilesOutput,
    PlanCreateOutput,
    PlanFileInfoOutput,
    PlanListOutput,
    PlanRetryOutput,
    PlanStatusOutput,
    PlanStopOutput,
)

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

from mcp_cloud.app import (
    PLANEXE_SERVER_INSTRUCTIONS,
    REPORT_CONTENT_TYPE,
    REPORT_FILENAME,
    TOOL_DEFINITIONS,
    ZIP_CONTENT_TYPE,
    ZIP_FILENAME,
    clear_download_base_url,
    fetch_artifact_from_worker_plan,
    fetch_user_downloadable_zip,
    handle_plan_create,
    handle_plan_list,
    handle_model_profiles,
    handle_plan_status,
    handle_plan_retry,
    handle_plan_stop,
    handle_plan_file_info,
    handle_prompt_examples,
    resolve_plan_for_task_id,
    set_download_base_url,
    validate_download_token,
    _resolve_user_from_api_key,
)

REQUIRED_API_KEY = os.environ.get("PLANEXE_MCP_API_KEY")

HTTP_HOST = os.environ.get("PLANEXE_MCP_HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("PORT") or os.environ.get("PLANEXE_MCP_HTTP_PORT", "8001"))
MAX_BODY_BYTES = int(os.environ.get("PLANEXE_MCP_MAX_BODY_BYTES", "1048576"))
RATE_LIMIT_REQUESTS = int(os.environ.get("PLANEXE_MCP_RATE_LIMIT", "60"))
RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("PLANEXE_MCP_RATE_WINDOW_SECONDS", "60"))
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


def _split_csv_env(value: Optional[str]) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    if not raw:
        return []

    values: list[str]
    if raw.startswith("[") and raw.endswith("]"):
        # Allow JSON array format in env var, e.g. ["https://a", "https://b"].
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
        # Be tolerant to copy-pasted shell quoting in deployment env values.
        if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
            normalized = normalized[1:-1].strip()
        if normalized:
            origins.append(normalized)
    return origins


CORS_ORIGINS = _split_csv_env(os.environ.get("PLANEXE_MCP_CORS_ORIGINS"))
if not CORS_ORIGINS:
    # Use wildcard so that browser-based tools (e.g. MCP Inspector at
    # localhost:6274) can connect directly.  API-key auth is the primary
    # access control; CORS is defence-in-depth only.
    CORS_ORIGINS = ["*"]

PUBLIC_JSONRPC_METHODS_NO_AUTH = {
    "initialize",
    "notifications/initialized",
    "tools/list",
    "prompts/list",
    "resources/list",
    "resources/templates/list",
    "ping",
}
PUBLIC_TOOL_CALLS_NO_AUTH = {
    "model_profiles",
    "prompt_examples",
}


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
    headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

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
                headers["Vary"] = f"{existing_vary}, Origin"
        else:
            headers["Vary"] = "Origin"
    return response


def _extract_jsonrpc_methods_from_payload(payload: Any) -> list[str]:
    methods: list[str] = []
    if isinstance(payload, dict):
        method = payload.get("method")
        if isinstance(method, str):
            methods.append(method)
        return methods

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                method = item.get("method")
                if isinstance(method, str):
                    methods.append(method)
    return methods


async def _extract_jsonrpc_methods_from_request(request: Request) -> list[str]:
    """Best-effort extraction of JSON-RPC method names from request body."""
    try:
        body = await request.body()
    except Exception:
        return []
    if not body:
        return []
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []
    return _extract_jsonrpc_methods_from_payload(payload)


def _extract_jsonrpc_tools_call_names(payload: Any) -> list[str]:
    names: list[str] = []
    entries: list[Any]
    if isinstance(payload, dict):
        entries = [payload]
    elif isinstance(payload, list):
        entries = payload
    else:
        return names

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("method") != "tools/call":
            continue
        params = entry.get("params")
        if not isinstance(params, dict):
            continue
        name = params.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def _extract_rest_tools_call_name(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    tool = payload.get("tool")
    return tool if isinstance(tool, str) else None


async def _is_public_mcp_request_without_auth(request: Request) -> bool:
    """Allow unauthenticated MCP handshake/discovery calls."""
    path = request.url.path
    method = request.method.upper()

    # Keep slashless /mcp compatible for probing and redirect handling.
    if path == "/mcp" and method in {"GET", "HEAD", "POST"}:
        return True
    if path == "/mcp/" and method in {"GET", "HEAD"}:
        return True

    # Public HTTP JSON endpoint for tool introspection.
    if path == "/mcp/tools" and method == "GET":
        return True

    # REST MCP tools call endpoint: expose only free setup/discovery tools.
    if path == "/mcp/tools/call" and method == "POST":
        try:
            payload = json.loads((await request.body()) or b"")
        except json.JSONDecodeError:
            return False
        tool = _extract_rest_tools_call_name(payload)
        return tool in PUBLIC_TOOL_CALLS_NO_AUTH

    # Streamable HTTP endpoint: allow lightweight discovery methods and free setup tools.
    if path != "/mcp/" or method != "POST":
        return False

    try:
        payload = json.loads((await request.body()) or b"")
    except json.JSONDecodeError:
        return False

    methods = _extract_jsonrpc_methods_from_payload(payload)
    if not methods:
        return False
    if all(item in PUBLIC_JSONRPC_METHODS_NO_AUTH for item in methods):
        return True

    if all(item == "tools/call" for item in methods):
        names = _extract_jsonrpc_tools_call_names(payload)
        if names and all(name in PUBLIC_TOOL_CALLS_NO_AUTH for name in names):
            return True
    return False


async def _log_auth_rejection(request: Request, reason: str) -> None:
    methods = await _extract_jsonrpc_methods_from_request(request)
    logger.info(
        "Auth rejected: reason=%s method=%s path=%s client=%s ua=%s jsonrpc_methods=%s",
        reason,
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent", ""),
        methods,
    )

_rate_lock = asyncio.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_authenticated_user_api_key_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "authenticated_user_api_key", default=None
)


def _normalize_api_key_value(raw_value: Optional[str]) -> Optional[str]:
    """Strip common copy-paste artefacts from an API key value.

    Handles cases where clients paste the full header line (e.g. 'X-API-Key: pex_…')
    or include a Bearer/token scheme prefix (e.g. 'Bearer pex_…'), or wrap the
    value in quotes.
    """
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None

    lower = value.lower()

    # Strip common header-name prefixes (copy-paste of the full header line).
    for prefix in ("x-api-key:", "api-key:", "api_key:", "authorization:"):
        if lower.startswith(prefix):
            value = value[len(prefix):].strip()
            lower = value.lower()
            break

    # Strip scheme prefixes.
    if lower.startswith("bearer "):
        value = value[7:].strip()
    elif lower.startswith("token "):
        value = value[6:].strip()
    elif " " in value:
        # Generic "<scheme> <token>" – keep the last segment.
        value = value.rsplit(" ", 1)[-1].strip()

    # Strip matching surrounding quotes.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()

    return value or None


def _extract_api_key(request: Request) -> Optional[str]:
    # Prefer Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    normalized_auth = _normalize_api_key_value(auth_header)
    if normalized_auth:
        return normalized_auth

    # Fall back to explicit API-key headers (case-insensitive via Starlette).
    for header_name in ("X-API-Key", "API-Key", "API_KEY", "X_API_KEY"):
        value = _normalize_api_key_value(request.headers.get(header_name))
        if value:
            return value

    return None


async def _validate_api_key(request: Request) -> Optional[JSONResponse]:
    """Return an error response if API key validation fails.
    Accepts: (1) valid UserApiKey from DB, or (2) PLANEXE_MCP_API_KEY if set.
    Authentication can be disabled with PLANEXE_MCP_REQUIRE_AUTH=false.
    """
    if not AUTH_REQUIRED:
        return None

    provided_key = _extract_api_key(request)
    if not provided_key:
        await _log_auth_rejection(request, reason="missing_api_key")
        return JSONResponse(
            status_code=401,
            content={
                "detail": "Missing API key. Use X-API-Key."
            },
        )

    # Accept PLANEXE_MCP_API_KEY (shared secret) if configured
    if REQUIRED_API_KEY and provided_key == REQUIRED_API_KEY:
        _authenticated_user_api_key_ctx.set(None)
        return None

    # Accept valid UserApiKey from database (pex_... keys from home.planexe.org)
    user = await asyncio.to_thread(_resolve_user_from_api_key, provided_key)
    if user:
        _authenticated_user_api_key_ctx.set(provided_key)
        return None

    await _log_auth_rejection(request, reason="invalid_api_key")
    return JSONResponse(status_code=403, content={"detail": "Invalid API key"})


def _get_authenticated_user_api_key() -> Optional[str]:
    """Return the current request's authenticated UserApiKey, if available."""
    try:
        return _authenticated_user_api_key_ctx.get()
    except LookupError:
        return None


def _client_identifier(request: Request) -> str:
    api_key = _extract_api_key(request)
    if api_key:
        return f"key:{api_key}"
    if request.client and request.client.host:
        return f"ip:{request.client.host}"
    return "ip:unknown"


async def _enforce_rate_limit(request: Request) -> Optional[JSONResponse]:
    if RATE_LIMIT_REQUESTS <= 0:
        return None
    # Apply to the legacy JSON-call endpoint and to the Streamable HTTP /mcp endpoint.
    if request.url.path not in ("/mcp/tools/call", "/mcp", "/mcp/"):
        return None

    identifier = _client_identifier(request)
    now = monotonic()
    async with _rate_lock:
        bucket = _rate_buckets[identifier]
        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
        bucket.append(now)
    return None


async def _sweep_rate_buckets(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RATE_LIMIT_WINDOW_SECONDS)
        except asyncio.TimeoutError:
            pass
        now = monotonic()
        async with _rate_lock:
            for key in list(_rate_buckets):
                bucket = _rate_buckets[key]
                while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
                    bucket.popleft()
                if not bucket:
                    del _rate_buckets[key]


async def _enforce_body_size(request: Request) -> Optional[JSONResponse]:
    if request.method != "POST" or request.url.path != "/mcp/tools/call":
        return None

    content_length = request.headers.get("content-length")
    if not content_length:
        return JSONResponse(
            status_code=411,
            content={"detail": "Length Required"},
        )

    try:
        if int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid Content-Length header"},
        )
    return None


class MCPToolCallRequest(BaseModel):
    tool: str
    arguments: dict[str, Any]
    metadata: Optional[dict[str, Any]] = None


class MCPToolCallResponse(BaseModel):
    content: list[dict[str, Any]]
    error: Optional[dict[str, Any]] = None




def extract_text_content(text_contents: Sequence[Any]) -> list[dict[str, Any]]:
    """Extract text content from MCP TextContent objects."""
    result = []
    for item in text_contents:
        if hasattr(item, 'text'):
            result.append({"text": item.text})
        elif isinstance(item, dict):
            result.append(item)
        else:
            result.append({"text": str(item)})
    return result


def _parse_error_from_text(text: Any) -> Optional[dict[str, Any]]:
    if not isinstance(text, str):
        return None
    if not text or text[:1] not in ("{", "["):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and "error" in parsed:
        error = parsed["error"]
        if isinstance(error, dict):
            return error
        return {"message": str(error)}
    return None


def _normalize_tool_result(result: Any) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    if isinstance(result, tuple) and len(result) == 2:
        result = result[0]
    if isinstance(result, CallToolResult):
        content_blocks = result.content
        content = extract_text_content(content_blocks)
        error = None
        for item in content:
            if isinstance(item, dict) and "error" in item:
                error = item["error"]
                break
            if isinstance(item, dict) and "text" in item:
                parsed_error = _parse_error_from_text(item["text"])
                if parsed_error:
                    error = parsed_error
                    break
        return content, error
    if isinstance(result, ContentBlock):
        content_blocks: Sequence[Any] = [result]
    elif isinstance(result, list):
        content_blocks = result
    elif isinstance(result, dict):
        content_blocks = [result]
    else:
        content_blocks = [TextContent(type="text", text=str(result))]

    content = extract_text_content(content_blocks)
    error = None
    for item in content:
        if isinstance(item, dict) and "error" in item:
            error = item["error"]
            break
        if isinstance(item, dict) and "text" in item:
            parsed_error = _parse_error_from_text(item["text"])
            if parsed_error:
                error = parsed_error
                break
    return content, error


ModelProfileInput = Literal["baseline", "premium", "frontier", "custom"]
ResultArtifactInput = Literal["report", "zip"]


async def plan_create(
    prompt: str,
    model_profile: Annotated[
        ModelProfileInput,
        Field(description="Model profile: baseline, premium, frontier, custom. Call model_profiles to inspect options."),
    ] = "baseline",
) -> Annotated[CallToolResult, PlanCreateOutput]:
    """Create a new PlanExe task. Use prompt_examples first for example prompts."""
    authenticated_user_api_key = _get_authenticated_user_api_key()
    arguments: dict[str, Any] = {
        "prompt": prompt,
        "model_profile": model_profile,
    }
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_plan_create(
        arguments,
    )


async def plan_status(
    task_id: str = Field(..., description="Task UUID returned by plan_create."),
) -> Annotated[CallToolResult, PlanStatusOutput]:
    return await handle_plan_status({"task_id": task_id})


async def plan_stop(
    task_id: str = Field(..., description="Task UUID returned by plan_create. Use it to stop the plan creation."),
) -> Annotated[CallToolResult, PlanStopOutput]:
    return await handle_plan_stop({"task_id": task_id})


async def plan_retry(
    task_id: str = Field(..., description="UUID of the failed task to retry."),
    model_profile: Annotated[
        ModelProfileInput,
        Field(description="Model profile used for retry. Defaults to baseline."),
    ] = "baseline",
) -> Annotated[CallToolResult, PlanRetryOutput]:
    return await handle_plan_retry({"task_id": task_id, "model_profile": model_profile})


async def plan_file_info(
    task_id: str = Field(..., description="Task UUID returned by plan_create. Use it to download the created plan."),
    artifact: Annotated[
        ResultArtifactInput,
        Field(description="Download artifact type: report or zip."),
    ] = "report",
) -> Annotated[CallToolResult, PlanFileInfoOutput]:
    return await handle_plan_file_info({"task_id": task_id, "artifact": artifact})


async def prompt_examples() -> CallToolResult:
    """Return curated example prompts from the catalog (no arguments)."""
    return await handle_prompt_examples({})


async def model_profiles() -> Annotated[CallToolResult, ModelProfilesOutput]:
    """Return model_profile options with currently available models."""
    return await handle_model_profiles({})


async def plan_list(
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of tasks to return (1–50). Newest tasks are returned first."),
) -> Annotated[CallToolResult, PlanListOutput]:
    """List the most recent tasks for an authenticated user."""
    authenticated_user_api_key = _get_authenticated_user_api_key()
    arguments: dict[str, Any] = {"limit": limit}
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_plan_list(arguments)


def _register_tools(server: FastMCP) -> None:
    handler_map = {
        "plan_create": plan_create,
        "plan_status": plan_status,
        "plan_stop": plan_stop,
        "plan_retry": plan_retry,
        "plan_file_info": plan_file_info,
        "plan_list": plan_list,
        "prompt_examples": prompt_examples,
        "model_profiles": model_profiles,
    }
    for tool in TOOL_DEFINITIONS:
        handler = handler_map.get(tool.name)
        if handler is None:
            logger.warning("No HTTP handler registered for tool %s", tool.name)
            continue
        server.tool(
            name=tool.name,
            description=tool.description,
            annotations=ToolAnnotations(**tool.annotations) if tool.annotations else None,
        )(handler)


fastmcp_server = FastMCP(
    name="planexe-mcp-server",
    instructions=PLANEXE_SERVER_INSTRUCTIONS,
    host=HTTP_HOST,
    port=HTTP_PORT,
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
)
_register_tools(fastmcp_server)
fastmcp_http_app = fastmcp_server.streamable_http_app()


def _get_fastmcp(request: Request) -> FastMCP:
    fastmcp_server = getattr(request.app.state, "fastmcp_server", None)
    if fastmcp_server is None:
        raise HTTPException(status_code=503, detail="mcp_cloud not initialized")
    return fastmcp_server


@asynccontextmanager
async def _lifespan(app: FastAPI):
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


app = FastAPI(
    title="PlanExe – AI Project Planning",
    description="MCP server that generates strategic project-plan drafts from a natural-language prompt",
    version="1.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],  # Allow any header (e.g. X-API-Key) for CORS preflight
)


def _request_origin(request: Request) -> str:
    """Return externally visible scheme+host, honoring reverse-proxy headers."""
    parsed = urlparse(str(request.base_url))

    # Railway/reverse proxies terminate TLS and forward the original scheme/host.
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    forwarded_host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()

    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else parsed.scheme
    netloc = forwarded_host or request.headers.get("Host") or parsed.netloc
    return f"{scheme}://{netloc}"


def _has_valid_download_token(request: Request) -> bool:
    """Return True when the request carries a valid signed download token.

    Expected URL shape: /download/{task_id}/{filename}?token=...
    The token is validated against the task_id and filename so it cannot be
    reused for a different artifact.
    """
    token = request.query_params.get("token")
    if not token:
        return False
    parts = request.url.path.strip("/").split("/")
    # parts == ["download", "{task_id}", "{filename}"]
    if len(parts) != 3 or parts[0] != "download":
        return False
    task_id, filename = parts[1], parts[2]
    return validate_download_token(token, task_id, filename)


@app.middleware("http")
async def enforce_api_key(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    # OPTIONS (CORS preflight) must not require auth; browser does not send custom headers
    if request.method != "OPTIONS" and not await _is_public_mcp_request_without_auth(request) and (
        request.url.path.startswith("/mcp") or request.url.path.startswith("/download")
    ):
        # /download with a valid signed token is self-authenticating — no API key needed.
        is_tokenized_download = (
            request.url.path.startswith("/download")
            and _has_valid_download_token(request)
        )
        if not is_tokenized_download:
            error_response = await _validate_api_key(request)
            if error_response:
                return _append_cors_headers(request, error_response)

    error_response = await _enforce_body_size(request)
    if error_response:
        return _append_cors_headers(request, error_response)

    error_response = await _enforce_rate_limit(request)
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


@app.options("/mcp")
@app.options("/mcp/")
async def options_mcp() -> Response:
    """Handle CORS preflight for /mcp so browser-based tools (e.g. MCP Inspector) succeed."""
    return Response(status_code=200)


@app.api_route("/mcp", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
async def redirect_mcp_no_trailing_slash() -> RedirectResponse:
    """Normalize '/mcp' to '/mcp/' so streamable HTTP requests avoid 405 mismatches."""
    return RedirectResponse(url="/mcp/", status_code=307)


@app.post("/mcp/tools/call", response_model=MCPToolCallResponse)
async def call_tool(
    payload: MCPToolCallRequest,
    fastmcp_server: FastMCP = Depends(_get_fastmcp),
) -> MCPToolCallResponse:
    """
    Call an MCP tool by name with arguments.

    This endpoint wraps the stdio-based MCP tool handlers for HTTP access.
    """
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


@app.get("/mcp/tools")
async def list_tools(fastmcp_server: FastMCP = Depends(_get_fastmcp)) -> dict[str, Any]:
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

# Mount the Streamable HTTP MCP endpoint AFTER the explicit /mcp/tools and
# /mcp/tools/call routes so that those routes take priority.  Starlette checks
# routes in registration order; if the mount were first it would shadow the
# REST endpoints with a 404 from the sub-app.
app.mount("/mcp", fastmcp_http_app)

@app.get("/download/{task_id}/{filename}")
async def download_report(
    task_id: str,
    filename: str,
    token: Optional[str] = None,
) -> Response:
    """Download the generated report HTML or zip for a task.

    Authentication: either a valid ``?token=...`` query parameter (signed,
    expiring) or a valid API key in the request headers (existing behaviour).
    The middleware enforces one of these; the token is re-validated here for
    defence-in-depth.
    """
    if filename not in (REPORT_FILENAME, ZIP_FILENAME):
        raise HTTPException(status_code=404, detail="Report not found")
    # Defence-in-depth: if a token was supplied, it must be valid for this artifact.
    if token is not None and not validate_download_token(token, task_id, filename):
        raise HTTPException(status_code=401, detail="Invalid or expired download token")
    plan = await asyncio.to_thread(resolve_plan_for_task_id, task_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if filename == ZIP_FILENAME:
        content_bytes = await fetch_user_downloadable_zip(str(plan.id))
        if content_bytes is None:
            raise HTTPException(status_code=404, detail="Report not found")
        headers = {"Content-Disposition": f'attachment; filename="{task_id}.zip"'}
        return Response(content=content_bytes, media_type=ZIP_CONTENT_TYPE, headers=headers)

    content_bytes = await fetch_artifact_from_worker_plan(str(plan.id), REPORT_FILENAME)
    if content_bytes is None:
        raise HTTPException(status_code=404, detail="Report not found")
    headers = {"Content-Disposition": f'inline; filename="{REPORT_FILENAME}"'}
    return Response(content=content_bytes, media_type=REPORT_CONTENT_TYPE, headers=headers)


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
        "version": "1.0.0",
        "endpoints": {
            "mcp": "/mcp",
            "tools": "/mcp/tools",
            "call": "/mcp/tools/call",
            "health": "/healthcheck",
            "glama_connector": "/.well-known/glama.json",
            "download": f"/download/{{task_id}}/{REPORT_FILENAME}",
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
    """
    Resolve canonical llms metadata file path.
    """
    repo_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(repo_root, "public", "llms.txt")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="llms.txt not found")
    return path


@app.get("/.well-known/glama.json")
def glama_connector_metadata() -> dict[str, Any]:
    """Serve Glama connector ownership metadata."""
    return {
        "$schema": "https://glama.ai/mcp/schemas/connector.json",
        "maintainers": [{"email": GLAMA_MAINTAINER_EMAIL}],
    }


@app.get("/llms.txt")
def llms_txt():
    """
    Serve llms.txt for AI agent discoverability.

    This endpoint provides information about PlanExe for autonomous AI agents
    looking for project planning and execution tools. Designed for agent-first
    organizations and AI workforce deployments.
    """
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


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting PlanExe MCP Cloud server on {HTTP_HOST}:{HTTP_PORT}")
    if AUTH_REQUIRED:
        logger.info(
            "Authentication required: UserApiKey (from home.planexe.org) or PLANEXE_MCP_API_KEY"
        )
    else:
        logger.warning("Authentication disabled via PLANEXE_MCP_REQUIRE_AUTH=false")

    uvicorn.run("http_server:app", host=HTTP_HOST, port=HTTP_PORT, reload=False)
