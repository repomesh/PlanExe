from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class PromptExamplesOutput(BaseModel):
    samples: list[str] = Field(
        ...,
        description=(
            "Example prompts that define the baseline for what a good prompt looks like. "
            "Take inspiration from these when writing your own prompt for plan_create "
            "(typically ~300-800 words). Good prompt shape: objective, scope, constraints, "
            "timeline, stakeholders, budget/resources, and success criteria."
        ),
    )
    message: str


class PromptExamplesInput(BaseModel):
    """No input parameters."""
    pass


class ModelProfilesInput(BaseModel):
    """No input parameters."""
    pass


class ModelProfileModelEntry(BaseModel):
    key: str = Field(..., description="Model key from llm_config/<profile>.json.")
    provider_class: str | None = Field(
        default=None,
        description="Provider class (for example OpenRouter, OpenAI, Ollama).",
    )
    model: str | None = Field(default=None, description="Provider model identifier when present.")
    priority: int | None = Field(
        default=None,
        description="Priority from config (lower number means earlier in selection order).",
    )


class ModelProfileInfo(BaseModel):
    profile: Literal["baseline", "premium", "frontier", "custom"] = Field(
        ...,
        description="Model profile value accepted by plan_create.model_profile.",
    )
    title: str = Field(..., description="Human-friendly profile label.")
    summary: str = Field(..., description="Short profile guidance for callers.")
    model_count: int = Field(..., description="Number of models currently available in this profile.")
    models: list[ModelProfileModelEntry] = Field(
        ...,
        description="Models currently available to this profile.",
    )


class ModelProfilesOutput(BaseModel):
    default_profile: Literal["baseline", "premium", "frontier", "custom"] = Field(
        ...,
        description="Default model profile used when plan_create.model_profile is omitted/invalid.",
    )
    profiles: list[ModelProfileInfo] = Field(
        ...,
        description="Available profile options and their model inventory.",
    )
    message: str = Field(..., description="Caller guidance for selecting plan_create.model_profile.")


class PlanStatusInput(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by plan_create. Use it to reference the plan being created.",
    )


class PlanStopInput(BaseModel):
    task_id: str = Field(
        ...,
        description="The UUID returned by plan_create. Call plan_stop with this task_id to request the plan generation to stop.",
    )


class PlanRetryInput(BaseModel):
    task_id: str = Field(
        ...,
        description="UUID of the failed task to retry.",
    )
    model_profile: Literal["baseline", "premium", "frontier", "custom"] = Field(
        default="baseline",
        description=(
            "Model profile used for the retry run. Defaults to baseline if omitted."
        ),
    )


class PlanFileInfoInput(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by plan_create. Use it to download the created plan.",
    )
    artifact: str = Field(
        default="report",
        description="Download artifact type: report or zip.",
    )


class PlanCreateOutput(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by plan_create. Stable across plan_status/plan_stop/plan_file_info."
    )
    created_at: str


class PlanStatusTiming(BaseModel):
    started_at: str | None
    elapsed_sec: float


class PlanStatusFile(BaseModel):
    path: str
    updated_at: str


class PlanStatusSuccess(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by plan_create."
    )
    state: Literal["pending", "processing", "completed", "failed"] = Field(
        ...,
        description=(
            "Caller contract: pending/processing => keep polling; "
            "completed => download is ready; failed => terminal error."
        ),
    )
    progress_percentage: float = Field(
        ...,
        description="Completion progress from 0 to 100. Monotonically increasing; 100 when state is completed.",
    )
    timing: PlanStatusTiming
    files: list[PlanStatusFile] = Field(
        ...,
        description=(
            "Intermediate output files produced so far. "
            "Use updated_at timestamps to detect stalls. "
            "These files are included in the zip artifact when the task completes."
        ),
    )


class PlanStatusOutput(BaseModel):
    task_id: str | None = Field(
        default=None,
        description="Task UUID returned by plan_create."
    )
    state: Literal["pending", "processing", "completed", "failed"] | None = Field(
        default=None,
        description=(
            "Caller contract: pending/processing => keep polling; "
            "completed => download is ready; failed => terminal error."
        ),
    )
    progress_percentage: float | None = Field(
        default=None,
        description="Completion progress from 0 to 100. Monotonically increasing; 100 when state is completed.",
    )
    timing: PlanStatusTiming | None = None
    files: list[PlanStatusFile] | None = Field(
        default=None,
        description=(
            "Intermediate output files produced so far. "
            "Use updated_at timestamps to detect stalls. "
            "These files are included in the zip artifact when the task completes."
        ),
    )
    error: ErrorDetail | None = None


class PlanStopOutput(BaseModel):
    state: Literal["pending", "processing", "completed", "failed"] | None = Field(
        default=None,
        description="Current task state after stop request.",
    )
    stop_requested: bool | None = Field(
        default=None,
        description="True when stop request flag was set for a pending/processing task.",
    )
    error: ErrorDetail | None = None


class PlanRetryOutput(BaseModel):
    task_id: str | None = Field(
        default=None,
        description="Task UUID that was retried (same ID as the failed task).",
    )
    state: Literal["pending", "processing", "completed", "failed"] | None = Field(
        default=None,
        description="Current task state after retry request.",
    )
    model_profile: Literal["baseline", "premium", "frontier", "custom"] | None = Field(
        default=None,
        description="Model profile assigned to the retry request.",
    )
    retried_at: str | None = Field(
        default=None,
        description="UTC timestamp when the retry request was accepted.",
    )
    error: ErrorDetail | None = None


class PlanFileInfoNotReadyOutput(BaseModel):
    ready: bool = Field(False, description="Always False; indicates the artifact is not yet available.")
    reason: str = Field(..., description="Human-readable explanation, e.g. 'processing' or 'failed'.")


class PlanFileInfoReadyOutput(BaseModel):
    content_type: str = Field(..., description="Artifact content type.")
    sha256: str = Field(..., description="SHA-256 hash of artifact bytes.")
    download_size: int = Field(..., description="Artifact size in bytes.")
    download_url: str | None = Field(
        default=None,
        description="Absolute URL where the requested artifact can be downloaded.",
    )


class PlanFileInfoOutput(BaseModel):
    content_type: str | None = Field(default=None, description="Artifact content type.")
    sha256: str | None = Field(default=None, description="SHA-256 hash of artifact bytes.")
    download_size: int | None = Field(default=None, description="Artifact size in bytes.")
    download_url: str | None = Field(
        default=None,
        description="Absolute URL where the requested artifact can be downloaded.",
    )
    error: ErrorDetail | None = None


class PlanListInput(BaseModel):
    user_api_key: str = Field(
        ...,
        description="User API key (pex_...) to scope the task list to the authenticated user.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of tasks to return (1–50). Newest tasks are returned first.",
    )


class PlanListItem(BaseModel):
    task_id: str = Field(..., description="Task UUID.")
    state: Literal["pending", "processing", "completed", "failed"] = Field(
        ...,
        description="Current task state.",
    )
    progress_percentage: float = Field(..., description="Progress from 0 to 100.")
    created_at: str = Field(..., description="UTC creation timestamp (ISO 8601).")
    prompt_excerpt: str = Field(..., description="First 100 characters of the prompt.")


class PlanListOutput(BaseModel):
    tasks: list[PlanListItem] = Field(..., description="Tasks for the authenticated user, newest first.")
    message: str = Field(..., description="Human-readable summary (e.g. how many tasks were returned).")


class PlanCreateInput(BaseModel):
    prompt: str = Field(
        ...,
        description=(
            "What the plan should cover (goal, context, constraints). "
            "Use prompt_examples to get example prompts; use these as examples for plan_create. "
            "For best results, provide a detailed prompt (typically ~300-800 words). "
            "Good prompt shape: objective, scope, constraints, timeline, stakeholders, "
            "budget/resources, and success criteria. "
            "Write as flowing prose, not structured markdown. Include banned approaches, "
            "governance preferences, and phasing inline. "
            "Short prompts produce less detailed plans. "
            "Do not use plan_create for tiny one-shot outputs (e.g., a 5-point checklist); use direct LLM responses for those."
        ),
    )
    model_profile: Literal["baseline", "premium", "frontier", "custom"] = Field(
        default="baseline",
        description=(
            "Model profile selection: baseline (cheap/fast), premium (higher quality), "
            "frontier (most capable), custom (user-defined). Call model_profiles for runtime availability."
        ),
    )
    user_api_key: str | None = Field(
        default=None,
        description="Optional user API key for credits and attribution.",
    )


# ---------------------------------------------------------------------------
# Backward-compatible aliases for old Task* names (used internally in app.py)
# ---------------------------------------------------------------------------
TaskCreateInput = PlanCreateInput
TaskCreateOutput = PlanCreateOutput
TaskStatusInput = PlanStatusInput
TaskStatusOutput = PlanStatusOutput
TaskStatusTiming = PlanStatusTiming
TaskStatusFile = PlanStatusFile
TaskStatusSuccess = PlanStatusSuccess
TaskStopInput = PlanStopInput
TaskStopOutput = PlanStopOutput
TaskRetryInput = PlanRetryInput
TaskRetryOutput = PlanRetryOutput
TaskFileInfoInput = PlanFileInfoInput
TaskFileInfoOutput = PlanFileInfoOutput
TaskFileInfoNotReadyOutput = PlanFileInfoNotReadyOutput
TaskFileInfoReadyOutput = PlanFileInfoReadyOutput
TaskListInput = PlanListInput
TaskListItem = PlanListItem
TaskListOutput = PlanListOutput
