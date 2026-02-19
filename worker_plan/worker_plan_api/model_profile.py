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
ENV_PLANEXE_LLM_CONFIG_NAME_LEGACY = "PLANEXE_LLM_CONFIG_NAME"

# Strict filename validation:
# - must be a filename (no path separators, no absolute path)
# - must start with "llm_config"
# - must end with ".json"
# - optional suffix after "llm_config." must be at least 3 chars and only [a-z0-9_]
_FILENAME_PATTERN = re.compile(r"^llm_config(?:\.[a-z0-9_]{3,})?\.json$")


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


def default_filename_for_profile(model_profile: ModelProfileEnum) -> str:
    if model_profile == ModelProfileEnum.BASELINE:
        return "llm_config.json"
    if model_profile == ModelProfileEnum.PREMIUM:
        return "llm_config.premium.json"
    if model_profile == ModelProfileEnum.FRONTIER:
        return "llm_config.frontier.json"
    # CUSTOM
    custom_name = os.environ.get(ENV_PLANEXE_LLM_CONFIG_CUSTOM_FILENAME, "llm_config.custom.json")
    if is_valid_llm_config_filename(custom_name):
        return custom_name.strip()
    logger.warning(
        "Invalid %s=%r. Falling back to llm_config.json.",
        ENV_PLANEXE_LLM_CONFIG_CUSTOM_FILENAME,
        custom_name,
    )
    return "llm_config.json"


def resolve_llm_config_filename(
    model_profile: Optional[ModelProfileEnum] = None,
    explicit_filename: Optional[str] = None,
) -> str:
    """Resolve selected config filename.

    Precedence:
    1) explicit_filename if provided and valid
    2) legacy env PLANEXE_LLM_CONFIG_NAME if provided and valid
    3) profile-based default filename
    """
    selected_profile = model_profile or resolve_model_profile_from_env()

    if isinstance(explicit_filename, str) and explicit_filename.strip():
        explicit_candidate = explicit_filename.strip()
        if is_valid_llm_config_filename(explicit_candidate):
            return explicit_candidate
        logger.warning("Invalid explicit LLM config filename %r. Ignoring.", explicit_filename)

    legacy_name = os.environ.get(ENV_PLANEXE_LLM_CONFIG_NAME_LEGACY)
    if isinstance(legacy_name, str) and legacy_name.strip():
        legacy_candidate = legacy_name.strip()
        if is_valid_llm_config_filename(legacy_candidate):
            logger.info(
                "Using legacy %s=%s. Consider migrating to %s + profile files.",
                ENV_PLANEXE_LLM_CONFIG_NAME_LEGACY,
                legacy_candidate,
                ENV_PLANEXE_MODEL_PROFILE,
            )
            return legacy_candidate
        logger.warning(
            "Invalid %s=%r. Ignoring legacy override and using profile mapping.",
            ENV_PLANEXE_LLM_CONFIG_NAME_LEGACY,
            legacy_name,
        )

    return default_filename_for_profile(selected_profile)
