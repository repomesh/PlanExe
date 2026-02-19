from __future__ import annotations

from typing import Any, Optional

from worker_plan_api.model_profile import ModelProfileEnum, resolve_model_profile_from_parameters


def resolve_model_profile(parameters: Optional[dict[str, Any]]) -> ModelProfileEnum:
    return resolve_model_profile_from_parameters(parameters)
