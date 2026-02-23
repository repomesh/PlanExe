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
            "Take inspiration from these when writing your own prompt for task_create."
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
        description="Model profile value accepted by task_create.model_profile.",
    )
    title: str = Field(..., description="Human-friendly profile label.")
    summary: str = Field(..., description="Short profile guidance for callers.")
    available: bool = Field(..., description="True when the profile config file was found and parsed.")
    model_count: int = Field(..., description="Number of models currently available in this profile.")
    models: list[ModelProfileModelEntry] = Field(
        ...,
        description="Models currently available to this profile.",
    )


class ModelProfilesOutput(BaseModel):
    default_profile: Literal["baseline", "premium", "frontier", "custom"] = Field(
        ...,
        description="Default model profile used when task_create.model_profile is omitted/invalid.",
    )
    profiles: list[ModelProfileInfo] = Field(
        ...,
        description="Available profile options and their model inventory.",
    )
    message: str = Field(..., description="Caller guidance for selecting task_create.model_profile.")


class TaskStatusInput(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by task_create. Use it to reference the plan being created.",
    )


class TaskStopInput(BaseModel):
    task_id: str = Field(
        ...,
        description="The UUID returned by task_create. Call task_stop with this task_id to request the plan generation to stop.",
    )


class TaskFileInfoInput(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by task_create. Use it to download the created plan.",
    )
    artifact: str = Field(
        default="report",
        description="Download artifact type: report or zip.",
    )


class TaskCreateOutput(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by task_create. Stable across task_status/task_stop/task_file_info."
    )
    created_at: str


class TaskStatusTiming(BaseModel):
    started_at: str | None
    elapsed_sec: float


class TaskStatusFile(BaseModel):
    path: str
    updated_at: str


class TaskStatusSuccess(BaseModel):
    task_id: str = Field(
        ...,
        description="Task UUID returned by task_create."
    )
    state: Literal["pending", "processing", "completed", "failed"] = Field(
        ...,
        description=(
            "Caller contract: pending/processing => keep polling; "
            "completed => download is ready; failed => terminal error."
        ),
    )
    progress_percentage: float
    timing: TaskStatusTiming
    files: list[TaskStatusFile]


class TaskStatusOutput(BaseModel):
    task_id: str | None = Field(
        default=None,
        description="Task UUID returned by task_create."
    )
    state: Literal["pending", "processing", "completed", "failed"] | None = Field(
        default=None,
        description=(
            "Caller contract: pending/processing => keep polling; "
            "completed => download is ready; failed => terminal error."
        ),
    )
    progress_percentage: float | None = None
    timing: TaskStatusTiming | None = None
    files: list[TaskStatusFile] | None = None
    error: ErrorDetail | None = None


class TaskStopOutput(BaseModel):
    state: Literal["pending", "processing", "completed", "failed"] | None = Field(
        default=None,
        description="Current task state after stop request.",
    )
    stop_requested: bool | None = Field(
        default=None,
        description="True when stop request flag was set for a pending/processing task.",
    )
    error: ErrorDetail | None = None


class TaskFileInfoReadyOutput(BaseModel):
    content_type: str = Field(..., description="Artifact content type.")
    sha256: str = Field(..., description="SHA-256 hash of artifact bytes.")
    download_size: int = Field(..., description="Artifact size in bytes.")
    download_url: str | None = Field(
        default=None,
        description=(
            "Absolute artifact download URL when server base URL is known "
            "(PLANEXE_MCP_PUBLIC_BASE_URL or request host)."
        ),
    )


class TaskFileInfoOutput(BaseModel):
    content_type: str | None = Field(default=None, description="Artifact content type.")
    sha256: str | None = Field(default=None, description="SHA-256 hash of artifact bytes.")
    download_size: int | None = Field(default=None, description="Artifact size in bytes.")
    download_url: str | None = Field(
        default=None,
        description=(
            "Absolute artifact download URL when server base URL is known. "
            "May be omitted in some deployments."
        ),
    )
    error: ErrorDetail | None = None


class TaskCreateInput(BaseModel):
    prompt: str = Field(
        ...,
        description=(
            "What the plan should cover (goal, context, constraints). "
            "Use prompt_examples to get example prompts; use these as examples for task_create. "
            "Short prompts produce less detailed plans. "
            "Do not use task_create for tiny one-shot outputs (e.g., a 5-point checklist); use direct LLM responses for those."
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
