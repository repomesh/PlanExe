"""Utilities for selecting LLM model profiles and resolving profile config filenames."""

from __future__ import annotations

from enum import Enum
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ModelProfileEnum(str, Enum):
    BASELINE = "baseline"
    PREMIUM = "premium"
    FRONTIER = "frontier"
    CUSTOM = "custom"


DEFAULT_MODEL_PROFILE = ModelProfileEnum.BASELINE
ENV_PLANEXE_MODEL_PROFILE = "PLANEXE_MODEL_PROFILE"
ENV_PLANEXE_LLM_CONFIG_CUSTOM_FILENAME = "PLANEXE_LLM_CONFIG_CUSTOM_FILENAME"

# Strict filename validation:
# - must be a filename (no path separators, no absolute path)
# - must end with ".json"
# - stem must be at least 3 chars and only [a-z0-9_]
_FILENAME_PATTERN = re.compile(r"^[a-z0-9_]{3,}\.json$")


def normalize_model_profile(raw_value: Optional[str]) -> ModelProfileEnum:
    if not isinstance(raw_value, str):
        return DEFAULT_MODEL_PROFILE
    candidate = raw_value.strip().lower()
    for enum_value in ModelProfileEnum:
        if enum_value.value == candidate:
            return enum_value
    logger.warning("Invalid model profile %r. Falling back to %s.", raw_value, DEFAULT_MODEL_PROFILE.value)
    return DEFAULT_MODEL_PROFILE


def resolve_model_profile_from_parameters(parameters: Optional[dict[str, Any]]) -> ModelProfileEnum:
    if not isinstance(parameters, dict):
        return DEFAULT_MODEL_PROFILE
    raw_value = parameters.get("model_profile") or parameters.get("llm_profile")
    return normalize_model_profile(raw_value)


def resolve_model_profile_from_env() -> ModelProfileEnum:
    raw_value = os.environ.get(ENV_PLANEXE_MODEL_PROFILE)
    return normalize_model_profile(raw_value)


def is_valid_llm_config_filename(filename: str) -> bool:
    if not isinstance(filename, str):
        return False
    candidate = filename.strip()
    if not candidate:
        return False
    path = Path(candidate)
    if path.is_absolute():
        return False
    if "/" in candidate or "\\" in candidate:
        return False
    return bool(_FILENAME_PATTERN.match(candidate))


def normalize_llm_config_filename(filename: str) -> Optional[str]:
    """Validate and normalize LLM config filenames."""
    if not isinstance(filename, str):
        return None
    candidate = filename.strip()
    if not candidate:
        return None

    if is_valid_llm_config_filename(candidate):
        return candidate
    return None


def default_filename_for_profile(model_profile: ModelProfileEnum) -> str:
    if model_profile == ModelProfileEnum.BASELINE:
        return "baseline.json"
    if model_profile == ModelProfileEnum.PREMIUM:
        return "premium.json"
    if model_profile == ModelProfileEnum.FRONTIER:
        return "frontier.json"
    # CUSTOM
    custom_name = os.environ.get(ENV_PLANEXE_LLM_CONFIG_CUSTOM_FILENAME, "custom.json")
    normalized_custom_name = normalize_llm_config_filename(custom_name)
    if normalized_custom_name is not None:
        return normalized_custom_name
    logger.warning(
        "Invalid %s=%r. Falling back to baseline.json.",
        ENV_PLANEXE_LLM_CONFIG_CUSTOM_FILENAME,
        custom_name,
    )
    return "baseline.json"


def resolve_llm_config_filename(
    model_profile: Optional[ModelProfileEnum] = None,
    explicit_filename: Optional[str] = None,
) -> str:
    """Resolve selected config filename.

    Precedence:
    1) explicit_filename if provided and valid
    2) profile-based default filename
    """
    selected_profile = model_profile or resolve_model_profile_from_env()

    if isinstance(explicit_filename, str) and explicit_filename.strip():
        normalized_explicit_filename = normalize_llm_config_filename(explicit_filename)
        if normalized_explicit_filename is not None:
            return normalized_explicit_filename
        logger.warning("Invalid explicit LLM config filename %r. Ignoring.", explicit_filename)

    return default_filename_for_profile(selected_profile)
