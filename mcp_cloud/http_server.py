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
from mcp.types import CallToolResult, ContentBlock, TextContent

from mcp_cloud.http_utils import strip_redundant_content
from mcp_cloud.tool_models import (
    ModelProfilesOutput,
    TaskCreateOutput,
    TaskFileInfoOutput,
    TaskStatusOutput,
    TaskStopOutput,
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
    REPORT_CONTENT_TYPE,
    REPORT_FILENAME,
    TOOL_DEFINITIONS,
    ZIP_CONTENT_TYPE,
    ZIP_FILENAME,
    clear_download_base_url,
    fetch_artifact_from_worker_plan,
    fetch_user_downloadable_zip,
    handle_task_create,
    handle_model_profiles,
    handle_task_status,
    handle_task_stop,
    handle_task_file_info,
    handle_prompt_examples,
    resolve_task_for_task_id,
    set_download_base_url,
    _resolve_user_from_api_key,
)

REQUIRED_API_KEY = os.environ.get("PLANEXE_MCP_API_KEY")

HTTP_HOST = os.environ.get("PLANEXE_MCP_HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("PORT") or os.environ.get("PLANEXE_MCP_HTTP_PORT", "8001"))
MAX_BODY_BYTES = int(os.environ.get("PLANEXE_MCP_MAX_BODY_BYTES", "1048576"))
RATE_LIMIT_REQUESTS = int(os.environ.get("PLANEXE_MCP_RATE_LIMIT", "60"))
RATE_LIMIT_WINDOW_SECONDS = float(os.environ.get("PLANEXE_MCP_RATE_WINDOW_SECONDS", "60"))


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
    return [item.strip() for item in value.split(",") if item.strip()]


CORS_ORIGINS = _split_csv_env(os.environ.get("PLANEXE_MCP_CORS_ORIGINS"))
if not CORS_ORIGINS:
    # Use wildcard so that browser-based tools (e.g. MCP Inspector at
    # localhost:6274) can connect directly.  API-key auth is the primary
    # access control; CORS is defence-in-depth only.
    CORS_ORIGINS = ["*"]

_rate_lock = asyncio.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_authenticated_user_api_key_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "authenticated_user_api_key", default=None
)


def _extract_api_key(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
            if token:
                return token
    header_key = request.headers.get("X-API-Key") or request.headers.get("API_KEY")
    if header_key:
        return header_key
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
    if request.url.path != "/mcp/tools/call":
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


async def task_create(
    prompt: str,
    model_profile: Annotated[
        ModelProfileInput,
        Field(description="Model profile: baseline, premium, frontier, custom. Call model_profiles to inspect options."),
    ] = "baseline",
) -> Annotated[CallToolResult, TaskCreateOutput]:
    """Create a new PlanExe task. Use prompt_examples first for example prompts."""
    authenticated_user_api_key = _get_authenticated_user_api_key()
    arguments: dict[str, Any] = {
        "prompt": prompt,
        "model_profile": model_profile,
    }
    if authenticated_user_api_key:
        arguments["user_api_key"] = authenticated_user_api_key
    return await handle_task_create(
        arguments,
    )


async def task_status(
    task_id: str = Field(..., description="Task UUID returned by task_create."),
) -> Annotated[CallToolResult, TaskStatusOutput]:
    return await handle_task_status({"task_id": task_id})


async def task_stop(
    task_id: str = Field(..., description="Task UUID returned by task_create. Use it to stop the plan creation."),
) -> Annotated[CallToolResult, TaskStopOutput]:
    return await handle_task_stop({"task_id": task_id})


async def task_file_info(
    task_id: str = Field(..., description="Task UUID returned by task_create. Use it to download the created plan."),
    artifact: Annotated[
        ResultArtifactInput,
        Field(description="Download artifact type: report or zip."),
    ] = "report",
) -> Annotated[CallToolResult, TaskFileInfoOutput]:
    return await handle_task_file_info({"task_id": task_id, "artifact": artifact})


async def prompt_examples() -> CallToolResult:
    """Return curated example prompts from the catalog (no arguments)."""
    return await handle_prompt_examples({})


async def model_profiles() -> Annotated[CallToolResult, ModelProfilesOutput]:
    """Return model_profile options with currently available models."""
    return await handle_model_profiles({})


def _register_tools(server: FastMCP) -> None:
    handler_map = {
        "task_create": task_create,
        "task_status": task_status,
        "task_stop": task_stop,
        "task_file_info": task_file_info,
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
        )(handler)


fastmcp_server = FastMCP(
    name="planexe-mcp-server",
    instructions=(
        "PlanExe generates rough-draft project plans from a natural-language prompt. "
        "Use PlanExe for substantial multi-phase projects with constraints, stakeholders, budgets, and timelines. "
        "Do not use PlanExe for tiny one-shot outputs (for example: 'give me a 5-point checklist'); use a normal LLM response for that. "
        "The planning pipeline is fixed end-to-end; callers cannot select individual internal pipeline steps to run. "
        "Required interaction order: call prompt_examples first. "
        "Optional before task_create: call model_profiles to see profile guidance and available models under current whitelist settings. "
        "Then perform a non-tool step: draft a strong prompt and get user approval. "
        "Only after approval, call task_create. "
        "Then poll task_status (about every 5 minutes); use task_file_info when complete. To stop, call task_stop with the task_id from task_create. "
        "task_status state contract: pending/processing => keep polling; completed => download is ready; failed => terminal error. "
        "Troubleshooting: if task_status stays in pending for longer than 5 minutes, the task was likely queued but not picked up by a worker (server issue). "
        "If task_status is in processing and output files do not change for longer than 20 minutes, the task_create likely failed/stalled. "
        "In both cases, report the issue to PlanExe developers on GitHub: https://github.com/PlanExeOrg/PlanExe/issues . "
        "Main output: large HTML report (~700KB) and zip of intermediary files (md, json, csv)."
    ),
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
    description="MCP server that generates rough-draft project plans from a natural-language prompt",
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


@app.middleware("http")
async def enforce_api_key(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    # OPTIONS (CORS preflight) must not require auth; browser does not send custom headers
    if request.method != "OPTIONS" and (
        request.url.path.startswith("/mcp") or request.url.path.startswith("/download")
    ):
        error_response = await _validate_api_key(request)
        if error_response:
            return error_response

    error_response = await _enforce_body_size(request)
    if error_response:
        return error_response

    error_response = await _enforce_rate_limit(request)
    if error_response:
        return error_response

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
    return response


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


@app.post("/mcp/tools/call", response_model=MCPToolCallResponse)
async def call_tool(
    payload: MCPToolCallRequest,
    fastmcp_server: FastMCP = Depends(_get_fastmcp),
) -> MCPToolCallResponse:
    """
    Call an MCP tool by name with arguments.

    This endpoint wraps the stdio-based MCP tool handlers for HTTP access.
    Download URLs use the request host when PLANEXE_MCP_PUBLIC_BASE_URL is not set (set in middleware).
    """
    arguments = dict(payload.arguments or {})
    if payload.tool == "task_create":
        authenticated_user_api_key = _get_authenticated_user_api_key()
        if authenticated_user_api_key and not arguments.get("user_api_key"):
            arguments["user_api_key"] = authenticated_user_api_key
        if isinstance(payload.metadata, dict):
            arguments["metadata"] = dict(payload.metadata)

        # Backward compatibility: move legacy speed args into hidden metadata.
        legacy_speed_vs_detail = arguments.pop("speed_vs_detail", None)
        legacy_speed = arguments.pop("speed", None)
        if isinstance(legacy_speed_vs_detail, str) or isinstance(legacy_speed, str):
            metadata = arguments.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                arguments["metadata"] = metadata
            task_create_metadata = metadata.get("task_create")
            if not isinstance(task_create_metadata, dict):
                task_create_metadata = {}
                metadata["task_create"] = task_create_metadata
            if isinstance(legacy_speed_vs_detail, str):
                task_create_metadata.setdefault("speed_vs_detail", legacy_speed_vs_detail)
            if isinstance(legacy_speed, str):
                task_create_metadata.setdefault("speed", legacy_speed)

        result = await handle_task_create(arguments)
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
async def download_report(task_id: str, filename: str) -> Response:
    """Download the generated report HTML for a task."""
    if filename not in (REPORT_FILENAME, ZIP_FILENAME):
        raise HTTPException(status_code=404, detail="Report not found")
    task = await asyncio.to_thread(resolve_task_for_task_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if filename == ZIP_FILENAME:
        content_bytes = await fetch_user_downloadable_zip(str(task.id))
        if content_bytes is None:
            raise HTTPException(status_code=404, detail="Report not found")
        headers = {"Content-Disposition": f'attachment; filename="{task_id}.zip"'}
        return Response(content=content_bytes, media_type=ZIP_CONTENT_TYPE, headers=headers)

    content_bytes = await fetch_artifact_from_worker_plan(str(task.id), REPORT_FILENAME)
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
