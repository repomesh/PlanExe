"""
PlanExe MCP Cloud – thin re-export facade.

All symbols previously importable from ``mcp_cloud.app`` are re-exported here
so that existing callers (http_server.py, tests, etc.) continue to work.
The actual implementations live in the focused modules under ``mcp_cloud/``.
"""
import asyncio

from mcp.server.stdio import stdio_server

# -- db_setup: Flask app, DB, constants, request classes, MCP Server ----------
from mcp_cloud.db_setup import (  # noqa: F401
    app,
    db,
    build_postgres_uri_from_env,
    ensure_planitem_stop_columns,
    PLANEXE_SERVER_INSTRUCTIONS,
    mcp_cloud_server as mcp_cloud,
    BASE_DIR_RUN,
    WORKER_PLAN_URL,
    REPORT_FILENAME,
    REPORT_CONTENT_TYPE,
    ZIP_FILENAME,
    ZIP_CONTENT_TYPE,
    ZIP_SNAPSHOT_MAX_BYTES,
    ModelProfileInput,
    MODEL_PROFILE_TITLES,
    MODEL_PROFILE_SUMMARIES,
    TaskCreateRequest,
    TaskStatusRequest,
    TaskStopRequest,
    TaskRetryRequest,
    TaskFileInfoRequest,
    TaskListRequest,
    ModelProfilesRequest,
    PlanItem,
    PlanState,
    EventItem,
    EventType,
    UserAccount,
    UserApiKey,
    logger,
)

# -- auth: API-key hashing and user resolution --------------------------------
from mcp_cloud.auth import (  # noqa: F401
    _hash_user_api_key,
    _resolve_user_from_api_key,
)

# -- db_queries: task lookup and sync DB operations ----------------------------
from mcp_cloud.db_queries import (  # noqa: F401
    find_plan_by_task_id,
    get_task_by_id,
    resolve_task_for_task_id,
    _create_task_sync,
    _get_task_status_snapshot_sync,
    _request_task_stop_sync,
    _retry_failed_task_sync,
    _get_task_for_report_sync,
    _list_tasks_sync,
    get_task_state_mapping,
    _extract_task_create_metadata_overrides,
    _merge_task_create_config,
)

# -- zip_utils: zip extraction, sanitization, hashing -------------------------
from mcp_cloud.zip_utils import (  # noqa: F401
    list_files_from_zip_bytes,
    extract_file_from_zip_bytes,
    extract_file_from_zip_file,
    fetch_report_from_db,
    fetch_zip_snapshot,
    fetch_file_from_zip_snapshot,
    list_files_from_zip_snapshot,
    _sanitize_legacy_zip_snapshot,
    compute_sha256,
)

# -- worker_fetchers: HTTP fetchers for worker_plan artifacts ------------------
from mcp_cloud.worker_fetchers import (  # noqa: F401
    fetch_artifact_from_worker_plan,
    fetch_file_list_from_worker_plan,
    list_files_from_local_run_dir,
    fetch_zip_from_worker_plan,
    fetch_user_downloadable_zip,
)

# -- model_profiles: model profile introspection ------------------------------
from mcp_cloud.model_profiles import (  # noqa: F401
    _sort_llm_config_entries,
    _extract_model_profile_entries,
    _profile_models_payload,
    _get_model_profiles_sync,
)

# -- download_tokens: signed download tokens and URL builders ------------------
from mcp_cloud.download_tokens import (  # noqa: F401
    _download_base_url_ctx,
    set_download_base_url,
    clear_download_base_url,
    _get_download_base_url,
    _get_download_token_secret,
    generate_download_token,
    validate_download_token,
    build_report_download_url,
    build_zip_download_url,
    build_report_download_path,
    build_zip_download_path,
)

# -- prompt_examples: example prompt loading -----------------------------------
from mcp_cloud.prompt_examples import (  # noqa: F401
    _load_mcp_example_prompts,
    _builtin_mcp_example_prompts,
)

# -- schemas: tool schema constants and ToolDefinition -------------------------
from mcp_cloud.schemas import (  # noqa: F401
    PLAN_CREATE_INPUT_SCHEMA,
    PLAN_CREATE_OUTPUT_SCHEMA,
    PLAN_STATUS_SUCCESS_SCHEMA,
    PLAN_STATUS_OUTPUT_SCHEMA,
    PLAN_STOP_OUTPUT_SCHEMA,
    PLAN_RETRY_OUTPUT_SCHEMA,
    PLAN_FILE_INFO_READY_OUTPUT_SCHEMA,
    PLAN_FILE_INFO_NOT_READY_OUTPUT_SCHEMA,
    PLAN_FILE_INFO_OUTPUT_SCHEMA,
    PLAN_STATUS_INPUT_SCHEMA,
    PLAN_STOP_INPUT_SCHEMA,
    PLAN_RETRY_INPUT_SCHEMA,
    PLAN_FILE_INFO_INPUT_SCHEMA,
    PROMPT_EXAMPLES_INPUT_SCHEMA,
    PROMPT_EXAMPLES_OUTPUT_SCHEMA,
    MODEL_PROFILES_INPUT_SCHEMA,
    MODEL_PROFILES_OUTPUT_SCHEMA,
    PLAN_LIST_INPUT_SCHEMA,
    PLAN_LIST_OUTPUT_SCHEMA,
    TASK_CREATE_INPUT_SCHEMA,
    TASK_CREATE_OUTPUT_SCHEMA,
    TASK_STATUS_INPUT_SCHEMA,
    TASK_STATUS_OUTPUT_SCHEMA,
    TASK_STOP_INPUT_SCHEMA,
    TASK_STOP_OUTPUT_SCHEMA,
    TASK_RETRY_INPUT_SCHEMA,
    TASK_RETRY_OUTPUT_SCHEMA,
    TASK_FILE_INFO_INPUT_SCHEMA,
    TASK_FILE_INFO_OUTPUT_SCHEMA,
    TASK_LIST_INPUT_SCHEMA,
    TASK_LIST_OUTPUT_SCHEMA,
    ToolDefinition,
    TOOL_DEFINITIONS,
)

# -- handlers: MCP tool handlers and dispatch ----------------------------------
from mcp_cloud.handlers import (  # noqa: F401
    handle_list_tools,
    handle_call_tool,
    handle_plan_create,
    handle_prompt_examples,
    handle_model_profiles,
    handle_plan_status,
    handle_plan_stop,
    handle_plan_retry,
    handle_plan_file_info,
    handle_plan_list,
    TOOL_HANDLERS,
    handle_task_create,
    handle_task_status,
    handle_task_stop,
    handle_task_retry,
    handle_task_file_info,
    handle_task_list,
)


async def main():
    """Main entry point for MCP server."""
    logger.info("Starting PlanExe MCP Cloud...")

    with app.app_context():
        db.create_all()
        logger.info("Database initialized")

    async with stdio_server() as streams:
        await mcp_cloud.run(
            streams[0],
            streams[1],
            mcp_cloud.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
