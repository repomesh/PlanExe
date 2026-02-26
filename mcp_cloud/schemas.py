"""PlanExe MCP Cloud – tool schema constants and ToolDefinition."""
from dataclasses import dataclass
from typing import Any, Optional

from mcp_cloud.tool_models import (
    ModelProfilesInput,
    ModelProfilesOutput,
    PromptExamplesInput,
    PromptExamplesOutput,
    PlanCreateInput,
    PlanCreateOutput,
    PlanRetryInput,
    PlanRetryOutput,
    PlanStopOutput,
    PlanStatusInput,
    PlanStopInput,
    PlanFileInfoInput,
    PlanFileInfoNotReadyOutput,
    PlanStatusSuccess,
    PlanFileInfoReadyOutput,
    PlanListInput,
    PlanListOutput,
    ErrorDetail,
)

PLAN_CREATE_INPUT_SCHEMA = PlanCreateInput.model_json_schema()
PLAN_CREATE_OUTPUT_SCHEMA = PlanCreateOutput.model_json_schema()
PLAN_STATUS_SUCCESS_SCHEMA = PlanStatusSuccess.model_json_schema()
PLAN_STATUS_OUTPUT_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"error": ErrorDetail.model_json_schema()},
            "required": ["error"],
        },
        PLAN_STATUS_SUCCESS_SCHEMA,
    ]
}
PLAN_STOP_OUTPUT_SCHEMA = PlanStopOutput.model_json_schema()
PLAN_RETRY_OUTPUT_SCHEMA = PlanRetryOutput.model_json_schema()
PLAN_FILE_INFO_READY_OUTPUT_SCHEMA = PlanFileInfoReadyOutput.model_json_schema()
PLAN_FILE_INFO_NOT_READY_OUTPUT_SCHEMA = PlanFileInfoNotReadyOutput.model_json_schema()
PLAN_FILE_INFO_OUTPUT_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"error": ErrorDetail.model_json_schema()},
            "required": ["error"],
        },
        PLAN_FILE_INFO_NOT_READY_OUTPUT_SCHEMA,
        PLAN_FILE_INFO_READY_OUTPUT_SCHEMA,
    ]
}
PLAN_STATUS_INPUT_SCHEMA = PlanStatusInput.model_json_schema()
PLAN_STOP_INPUT_SCHEMA = PlanStopInput.model_json_schema()
PLAN_RETRY_INPUT_SCHEMA = PlanRetryInput.model_json_schema()
PLAN_FILE_INFO_INPUT_SCHEMA = PlanFileInfoInput.model_json_schema()

PROMPT_EXAMPLES_INPUT_SCHEMA = PromptExamplesInput.model_json_schema()
PROMPT_EXAMPLES_OUTPUT_SCHEMA = PromptExamplesOutput.model_json_schema()
MODEL_PROFILES_INPUT_SCHEMA = ModelProfilesInput.model_json_schema()
MODEL_PROFILES_OUTPUT_SCHEMA = ModelProfilesOutput.model_json_schema()
PLAN_LIST_INPUT_SCHEMA = PlanListInput.model_json_schema()
PLAN_LIST_OUTPUT_SCHEMA = PlanListOutput.model_json_schema()

# Backward-compatible aliases for tests that reference old TASK_* names
TASK_CREATE_INPUT_SCHEMA = PLAN_CREATE_INPUT_SCHEMA
TASK_CREATE_OUTPUT_SCHEMA = PLAN_CREATE_OUTPUT_SCHEMA
TASK_STATUS_INPUT_SCHEMA = PLAN_STATUS_INPUT_SCHEMA
TASK_STATUS_OUTPUT_SCHEMA = PLAN_STATUS_OUTPUT_SCHEMA
TASK_STOP_INPUT_SCHEMA = PLAN_STOP_INPUT_SCHEMA
TASK_STOP_OUTPUT_SCHEMA = PLAN_STOP_OUTPUT_SCHEMA
TASK_RETRY_INPUT_SCHEMA = PLAN_RETRY_INPUT_SCHEMA
TASK_RETRY_OUTPUT_SCHEMA = PLAN_RETRY_OUTPUT_SCHEMA
TASK_FILE_INFO_INPUT_SCHEMA = PLAN_FILE_INFO_INPUT_SCHEMA
TASK_FILE_INFO_OUTPUT_SCHEMA = PLAN_FILE_INFO_OUTPUT_SCHEMA
TASK_LIST_INPUT_SCHEMA = PLAN_LIST_INPUT_SCHEMA
TASK_LIST_OUTPUT_SCHEMA = PLAN_LIST_OUTPUT_SCHEMA


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: Optional[dict[str, Any]] = None
    annotations: Optional[dict[str, Any]] = None

TOOL_DEFINITIONS = [
    ToolDefinition(
        name="prompt_examples",
        description=(
            "Call this first. Returns example prompts that define what a good prompt looks like. "
            "Do NOT call plan_create yet. Optional before plan_create: call model_profiles to choose model_profile. "
            "Next is a non-tool step: formulate a detailed prompt (typically ~300-800 words; use examples as a baseline, similar structure) and get user approval. "
            "Good prompt shape: objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria. "
            "Write the prompt as flowing prose, not structured markdown with headers or bullet lists. "
            "Weave technical specs, constraints, and targets naturally into sentences. Include banned words/approaches and governance preferences inline. "
            "The examples demonstrate this prose style — match their tone and density. "
            "Then call plan_create. "
            "PlanExe is not for tiny one-shot outputs like a 5-point checklist; and it does not support selecting only some internal pipeline steps."
        ),
        input_schema=PROMPT_EXAMPLES_INPUT_SCHEMA,
        output_schema=PROMPT_EXAMPLES_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolDefinition(
        name="model_profiles",
        description=(
            "Optional helper before plan_create. Returns model_profile options with plain-language guidance "
            "and currently available models in each profile. "
            "If no models are available, returns error code MODEL_PROFILES_UNAVAILABLE."
        ),
        input_schema=MODEL_PROFILES_INPUT_SCHEMA,
        output_schema=MODEL_PROFILES_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolDefinition(
        name="plan_create",
        description=(
            "Call only after prompt_examples and after you have completed prompt drafting/approval (non-tool step). "
            "PlanExe turns the approved prompt into a strategic project-plan draft (20+ sections) in ~10-20 min. "
            "Sections include: executive summary, interactive Gantt charts, investor pitch, project plan with SMART criteria, "
            "strategic decision analysis, scenario comparison, assumptions with expert review, governance structure, "
            "SWOT analysis, team role profiles, simulated expert criticism, work breakdown structure, "
            "plan review (critical issues, KPIs, financial strategy, automation opportunities), Q&A, "
            "premortem with failure scenarios, self-audit checklist, and adversarial premise attacks that argue against the project. "
            "The adversarial sections (premortem, self-audit, premise attacks) surface risks and questions the prompter may not have considered. "
            "Returns task_id (UUID); use it for plan_status, plan_stop, plan_retry, and plan_file_info. "
            "If you lose a task_id, call plan_list with your user_api_key to recover it. "
            "Each plan_create call creates a new task_id (no server-side dedup). "
            "If you are unsure which model_profile to choose, call model_profiles first. "
            "If your deployment uses credits, include user_api_key to charge the correct account. "
            "Common error codes: INVALID_USER_API_KEY, USER_API_KEY_REQUIRED, INSUFFICIENT_CREDITS."
        ),
        input_schema=PLAN_CREATE_INPUT_SCHEMA,
        output_schema=PLAN_CREATE_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    ),
    ToolDefinition(
        name="plan_status",
        description=(
            "Returns status and progress of the plan currently being created. "
            "Poll at reasonable intervals only (e.g. every 5 minutes): plan generation typically takes 10-20 minutes "
            "(baseline profile) and may take longer on higher-quality profiles. "
            "State contract: pending/processing => keep polling; completed => download is ready; failed => terminal error. "
            "progress_percentage is 0-100 (integer-like float); 100 when completed. "
            "files lists intermediate outputs produced so far; use their updated_at timestamps to detect stalls. "
            "Unknown task_id returns error code TASK_NOT_FOUND. "
            "Troubleshooting: pending for >5 minutes likely means queued but not picked up by a worker. "
            "processing with no file-output changes for >20 minutes likely means failed/stalled. "
            "Report these issues to https://github.com/PlanExeOrg/PlanExe/issues ."
        ),
        input_schema=PLAN_STATUS_INPUT_SCHEMA,
        output_schema=PLAN_STATUS_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolDefinition(
        name="plan_stop",
        description=(
            "Request the plan generation to stop. Pass the task_id (the UUID returned by plan_create). "
            "Stopping is asynchronous: the stop flag is set immediately but the task may continue briefly before halting. "
            "A stopped task will eventually transition to the failed state. "
            "If the task is already completed or failed, stop_requested returns false (the task already finished). "
            "Unknown task_id returns error code TASK_NOT_FOUND."
        ),
        input_schema=PLAN_STOP_INPUT_SCHEMA,
        output_schema=PLAN_STOP_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolDefinition(
        name="plan_retry",
        description=(
            "Retry a task that is currently in failed state. "
            "Pass the failed task_id and optionally model_profile (defaults to baseline). "
            "The task is reset to pending, prior artifacts are cleared, and the same task_id is requeued for processing. "
            "Returns TASK_NOT_FOUND when task_id is unknown and TASK_NOT_FAILED when the task is not in failed state."
        ),
        input_schema=PLAN_RETRY_INPUT_SCHEMA,
        output_schema=PLAN_RETRY_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    ),
    ToolDefinition(
        name="plan_file_info",
        description=(
            "Returns file metadata (content_type, download_url, download_size) for the report or zip artifact. "
            "Use artifact='report' (default) for the interactive HTML report (~700KB, self-contained with embedded JS "
            "for collapsible sections and interactive Gantt charts — open in a browser). "
            "Use artifact='zip' for the full pipeline output bundle (md, json, csv intermediary files that fed the report). "
            "While the task is still pending or processing, returns {ready:false,reason:\"processing\"}. "
            "Check readiness by testing whether download_url is present in the response. "
            "Once ready, present download_url to the user or fetch and save the file locally. "
            "If your client exposes plan_download (e.g. mcp_local), prefer that to save the file locally. "
            "Terminal error codes: generation_failed (plan failed), content_unavailable (artifact missing). "
            "Unknown task_id returns error code TASK_NOT_FOUND."
        ),
        input_schema=PLAN_FILE_INFO_INPUT_SCHEMA,
        output_schema=PLAN_FILE_INFO_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolDefinition(
        name="plan_list",
        description=(
            "List the most recent tasks for an authenticated user. "
            "Requires user_api_key (pex_...). "
            "Returns up to `limit` tasks (default 10, max 50) newest-first, each with task_id, state, "
            "progress_percentage, created_at (ISO 8601), and a prompt_excerpt (first 100 chars). "
            "Use this to recover a lost task_id or to review recent activity."
        ),
        input_schema=PLAN_LIST_INPUT_SCHEMA,
        output_schema=PLAN_LIST_OUTPUT_SCHEMA,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
]
