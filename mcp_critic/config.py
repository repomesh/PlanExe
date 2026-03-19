"""
LLM configuration for mcp_critic.

Reuses the llm_factory pattern from worker_plan_internal.
Supports:
  - PLANEXE_MODEL_PROFILE env var (baseline/premium/frontier/custom)
  - PLANEXE_LLM_CONFIG_CUSTOM_FILENAME env var
  - LLM_MODEL env var (specific model name to use)
"""
import logging
import os
from typing import Optional

from worker_plan_internal.llm_factory import get_llm, get_llm_names_by_priority
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelFromName, LLMModelWithInstance

logger = logging.getLogger(__name__)


def build_llm_executor(model_profile: Optional[str] = None) -> LLMExecutor:
    """
    Build an LLMExecutor from env vars or the provided model_profile.

    Priority:
      1. LLM_MODEL env var — specific named model
      2. model_profile arg (or PLANEXE_MODEL_PROFILE env var)
      3. Fallback: all models in priority order from the config
    """
    llm_model_name = os.environ.get("LLM_MODEL", "").strip() or None

    if llm_model_name:
        logger.debug(f"Using LLM_MODEL env var: {llm_model_name!r}")
        llm_models = LLMModelFromName.from_names([llm_model_name])
        return LLMExecutor(llm_models=llm_models)

    resolved_profile = model_profile or os.environ.get("PLANEXE_MODEL_PROFILE", "").strip() or None
    llm_names = get_llm_names_by_priority(model_profile=resolved_profile)
    if not llm_names:
        raise RuntimeError(
            "No LLM models found in config. "
            "Check your llm_config/<profile>.json file and set PLANEXE_MODEL_PROFILE if needed."
        )
    logger.debug(f"Using LLM models by priority: {llm_names}")
    llm_models = LLMModelFromName.from_names(llm_names)
    return LLMExecutor(llm_models=llm_models)
