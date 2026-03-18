"""
PlanExe Critic MCP Server — standalone premise attack, premortem, and SWOT.

Wraps PlanExe's critic pipeline (PremiseAttack, Premortem, SWOT) as MCP tools
so external agents can stress-test their plans.

Usage:
    python -m mcp_critic.server           # stdio mode (Claude Desktop, Cursor, etc.)
    python -m mcp_critic.server --sse     # SSE mode (remote HTTP agents)

Environment variables:
    LLM_MODEL                             — use a specific named model
    PLANEXE_MODEL_PROFILE                 — baseline / premium / frontier / custom
    PLANEXE_LLM_CONFIG_CUSTOM_FILENAME    — custom llm_config JSON filename
"""
import asyncio
import json
import logging
import sys
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

MODEL_PROFILE_SCHEMA = {
    "type": "string",
    "enum": ["baseline", "premium", "frontier", "custom"],
    "description": "Model profile: baseline (fast/cheap), premium, frontier (most capable), custom.",
}

OUTPUT_FORMAT_SCHEMA = {
    "type": "string",
    "enum": ["json", "markdown"],
    "default": "json",
    "description": "Response format: 'json' (structured) or 'markdown' (human-readable).",
}

PREMISE_ATTACK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The plan, idea, or implementation to stress-test.",
        },
        "model_profile": MODEL_PROFILE_SCHEMA,
        "format": OUTPUT_FORMAT_SCHEMA,
    },
    "required": ["prompt"],
}

PREMORTEM_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The plan to analyze for failure modes.",
        },
        "speed_vs_detail": {
            "type": "string",
            "enum": ["fast_but_skip_details", "all_details_but_slow"],
            "default": "fast_but_skip_details",
            "description": (
                "fast_but_skip_details: 3 assumptions + 3 failure modes (1 LLM call). "
                "all_details_but_slow: 9 assumptions + 9 failure modes (3 LLM calls)."
            ),
        },
        "model_profile": MODEL_PROFILE_SCHEMA,
        "format": OUTPUT_FORMAT_SCHEMA,
    },
    "required": ["prompt"],
}

SWOT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The plan or project to analyze.",
        },
        "model_profile": MODEL_PROFILE_SCHEMA,
        "format": OUTPUT_FORMAT_SCHEMA,
    },
    "required": ["prompt"],
}

CRITIQUE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The plan to critique.",
        },
        "tools": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["premise_attack", "premortem", "swot"],
            },
            "description": "Which tools to run. Defaults to all three.",
        },
        "model_profile": MODEL_PROFILE_SCHEMA,
        "format": OUTPUT_FORMAT_SCHEMA,
    },
    "required": ["prompt"],
}

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

CRITIC_SERVER_INSTRUCTIONS = (
    "PlanExe Critic runs three stress-test tools over a plan: "
    "premise_attack (5-lens ensemble that attacks the plan's WHY), "
    "premortem (failure mode analysis: what will kill this project and when), "
    "swot (strengths, weaknesses, opportunities, threats with recommendations). "
    "Use critique to run all three in one call. "
    "All tools are synchronous and may take 30–120 seconds depending on model and detail level. "
    "Configure the LLM via LLM_MODEL or PLANEXE_MODEL_PROFILE environment variables."
)

mcp_critic = Server("planexe-mcp-critic", instructions=CRITIC_SERVER_INSTRUCTIONS)


@mcp_critic.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="premise_attack",
            description=(
                "Run PremiseAttack: a 5-lens ensemble that attacks the fundamental WHY of a plan. "
                "Lenses: Integrity, Accountability, Spectrum, Cascade, Escalation. "
                "Each lens independently produces reasons to reject, second-order effects, evidence, and a bottom line. "
                "Returns a combined verdict (REJECT/PROCEED) with per-lens details."
            ),
            inputSchema=PREMISE_ATTACK_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="premortem",
            description=(
                "Run Premortem: imagine the project has failed and work backward. "
                "Produces assumptions_to_kill (foundational beliefs to validate immediately) "
                "and failure_modes (causal failure stories with tripwires, playbooks, and stop rules). "
                "Use fast_but_skip_details for quick analysis or all_details_but_slow for comprehensive coverage."
            ),
            inputSchema=PREMORTEM_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="swot",
            description=(
                "Run SWOT analysis: strengths, weaknesses, opportunities, threats. "
                "Also returns recommendations, strategic objectives, assumptions, missing information, "
                "and 5 critical questions. Uses business-focused system prompt by default."
            ),
            inputSchema=SWOT_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="critique",
            description=(
                "Run all three critic tools (premise_attack, premortem, swot) in one call "
                "and return a combined report. This is the 'hire us to vet your plan' endpoint. "
                "Use the tools parameter to select a subset. Partial results are returned if any tool fails."
            ),
            inputSchema=CRITIQUE_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
    ]


def _wrap_response(payload: dict[str, Any], is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=is_error,
    )


@mcp_critic.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        response = {"error": {"code": "INVALID_TOOL", "message": f"Unknown tool: {name}"}}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response))],
            structuredContent=response,
            isError=True,
        )
    return await handler(arguments)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_premise_attack(arguments: dict[str, Any]) -> CallToolResult:
    from mcp_critic.tools import run_premise_attack

    prompt = arguments.get("prompt", "")
    model_profile = arguments.get("model_profile") or None
    output_format = arguments.get("format", "json")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_premise_attack(prompt=prompt, model_profile=model_profile, output_format=output_format),
        )
    except Exception as e:
        logger.error("handle_premise_attack failed", exc_info=True)
        result = {"error": {"code": "TOOL_ERROR", "message": str(e)}}
        return _wrap_response(result, is_error=True)

    is_error = "error" in result and result.get("verdict") == "ERROR"
    return _wrap_response(result, is_error=is_error)


async def handle_premortem(arguments: dict[str, Any]) -> CallToolResult:
    from mcp_critic.tools import run_premortem

    prompt = arguments.get("prompt", "")
    speed_vs_detail = arguments.get("speed_vs_detail", "fast_but_skip_details")
    model_profile = arguments.get("model_profile") or None
    output_format = arguments.get("format", "json")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_premortem(
                prompt=prompt,
                speed_vs_detail=speed_vs_detail,
                model_profile=model_profile,
                output_format=output_format,
            ),
        )
    except Exception as e:
        logger.error("handle_premortem failed", exc_info=True)
        result = {"error": {"code": "TOOL_ERROR", "message": str(e)}}
        return _wrap_response(result, is_error=True)

    is_error = "error" in result
    return _wrap_response(result, is_error=is_error)


async def handle_swot(arguments: dict[str, Any]) -> CallToolResult:
    from mcp_critic.tools import run_swot

    prompt = arguments.get("prompt", "")
    model_profile = arguments.get("model_profile") or None
    output_format = arguments.get("format", "json")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_swot(prompt=prompt, model_profile=model_profile, output_format=output_format),
        )
    except Exception as e:
        logger.error("handle_swot failed", exc_info=True)
        result = {"error": {"code": "TOOL_ERROR", "message": str(e)}}
        return _wrap_response(result, is_error=True)

    is_error = "error" in result
    return _wrap_response(result, is_error=is_error)


async def handle_critique(arguments: dict[str, Any]) -> CallToolResult:
    from mcp_critic.tools import run_critique

    prompt = arguments.get("prompt", "")
    tools = arguments.get("tools") or None
    model_profile = arguments.get("model_profile") or None
    output_format = arguments.get("format", "json")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_critique(
                prompt=prompt,
                tools=tools,
                model_profile=model_profile,
                output_format=output_format,
            ),
        )
    except Exception as e:
        logger.error("handle_critique failed", exc_info=True)
        result = {"error": {"code": "TOOL_ERROR", "message": str(e)}}
        return _wrap_response(result, is_error=True)

    is_error = bool(result.get("errors"))
    return _wrap_response(result, is_error=is_error)


_TOOL_HANDLERS = {
    "premise_attack": handle_premise_attack,
    "premortem": handle_premortem,
    "swot": handle_swot,
    "critique": handle_critique,
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    logger.info("Starting PlanExe Critic MCP server (stdio)")
    async with stdio_server() as streams:
        await mcp_critic.run(
            streams[0],
            streams[1],
            mcp_critic.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
