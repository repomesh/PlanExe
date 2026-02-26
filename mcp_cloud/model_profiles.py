"""PlanExe MCP Cloud – model profile introspection."""
import json
import logging
import os
from typing import Any, Optional

from worker_plan_api.model_profile import (
    ModelProfileEnum,
    default_filename_for_profile,
    resolve_model_profile_from_env,
)
from worker_plan_api.planexe_config import PlanExeConfig
from worker_plan_api.llm_class_filter import (
    ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES,
    is_llm_class_allowed,
    parse_llm_class_whitelist,
)

from mcp_cloud.db_setup import MODEL_PROFILE_TITLES, MODEL_PROFILE_SUMMARIES

logger = logging.getLogger(__name__)


def _sort_llm_config_entries(items: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    def sort_key(item: tuple[str, Any]) -> tuple[int, str]:
        key, model_data = item
        priority = None
        if isinstance(model_data, dict):
            maybe_priority = model_data.get("priority")
            if isinstance(maybe_priority, int):
                priority = maybe_priority
        if priority is None:
            priority = 999999
        return priority, key

    return sorted(items, key=sort_key)


def _extract_model_profile_entries(
    model_map: dict[str, Any],
    whitelist: Optional[set[str]],
) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []

    for model_key, model_data in _sort_llm_config_entries(list(model_map.items())):
        class_name = model_data.get("class") if isinstance(model_data, dict) else None
        if not is_llm_class_allowed(class_name, whitelist):
            continue

        model_name = None
        priority = None
        if isinstance(model_data, dict):
            arguments = model_data.get("arguments")
            if isinstance(arguments, dict):
                maybe_model = arguments.get("model")
                if isinstance(maybe_model, str):
                    model_name = maybe_model
            maybe_priority = model_data.get("priority")
            if isinstance(maybe_priority, int):
                priority = maybe_priority
            elif isinstance(model_data.get("prio"), int):
                priority = model_data["prio"]

        models.append(
            {
                "key": model_key,
                "provider_class": class_name if isinstance(class_name, str) else None,
                "model": model_name,
                "priority": priority,
            }
        )

    return models


def _profile_models_payload(
    profile: ModelProfileEnum,
    whitelist: Optional[set[str]],
) -> dict[str, Any]:
    config_filename = default_filename_for_profile(profile)
    planexe_config_path = PlanExeConfig.resolve_planexe_config_path()
    config_path = PlanExeConfig.find_file_in_search_order(config_filename, planexe_config_path)
    if config_path is None:
        return {
            "profile": profile.value,
            "title": MODEL_PROFILE_TITLES[profile.value],
            "summary": MODEL_PROFILE_SUMMARIES[profile.value],
            "model_count": 0,
            "models": [],
        }

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            model_map = json.load(fh)
    except Exception as exc:
        logger.warning(
            "Unable to read profile config %s for model profile %s: %s",
            config_filename,
            profile.value,
            exc,
        )
        return {
            "profile": profile.value,
            "title": MODEL_PROFILE_TITLES[profile.value],
            "summary": MODEL_PROFILE_SUMMARIES[profile.value],
            "model_count": 0,
            "models": [],
        }

    if not isinstance(model_map, dict):
        return {
            "profile": profile.value,
            "title": MODEL_PROFILE_TITLES[profile.value],
            "summary": MODEL_PROFILE_SUMMARIES[profile.value],
            "model_count": 0,
            "models": [],
        }

    models = _extract_model_profile_entries(model_map, whitelist)
    return {
        "profile": profile.value,
        "title": MODEL_PROFILE_TITLES[profile.value],
        "summary": MODEL_PROFILE_SUMMARIES[profile.value],
        "model_count": len(models),
        "models": models,
    }


def _get_model_profiles_sync() -> dict[str, Any]:
    raw_whitelist = os.environ.get(ENV_PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES)
    whitelist = parse_llm_class_whitelist(raw_whitelist)
    default_profile = resolve_model_profile_from_env().value
    profiles_all = [
        _profile_models_payload(profile, whitelist)
        for profile in ModelProfileEnum
    ]
    profiles = [profile for profile in profiles_all if int(profile.get("model_count") or 0) > 0]

    return {
        "default_profile": default_profile,
        "profiles": profiles,
        "message": (
            "Use one of these profile values in plan_create.model_profile. "
            "Model lists show what is currently available in each profile."
        ),
    }
