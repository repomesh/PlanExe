"""
Locate PlanExe config files (.env and llm_config profile files).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging
import os
from enum import Enum

from worker_plan_api.model_profile import (
    DEFAULT_MODEL_PROFILE,
    ModelProfileEnum,
    normalize_model_profile,
    resolve_llm_config_filename,
    resolve_model_profile_from_env,
)

logger = logging.getLogger(__name__)


class ConfigNameEnum(str, Enum):
    DOTENV = ".env"
    LLM_CONFIG_JSON_DEFAULT = "llm_config.json"


class EnvNameEnum(str, Enum):
    PLANEXE_CONFIG_PATH = "PLANEXE_CONFIG_PATH"


class PlanExeConfigError(Exception):
    """Raised when there is an error with the configuration."""
    pass


@dataclass
class PlanExeConfig:
    """Resolved config paths and selected LLM profile/config file."""

    planexe_config_path: Optional[Path]
    dotenv_path: Optional[Path]
    model_profile: ModelProfileEnum
    llm_config_json_name: str
    llm_config_json_path: Optional[Path]

    def raise_if_required_files_not_found(self) -> None:
        missing_files = []
        if self.llm_config_json_path is None:
            missing_files.append(self.llm_config_json_name)

        if missing_files:
            msg = f"Required configuration file(s) not found: {', '.join(missing_files)}"
            logger.error(msg)
            raise PlanExeConfigError(msg)
        if self.dotenv_path is None:
            logger.info("Optional configuration file '.env' not found; relying on environment variables only.")

    @classmethod
    def load(
        cls,
        model_profile_override: Optional[ModelProfileEnum | str] = None,
        llm_config_json_name_override: Optional[str] = None,
    ) -> 'PlanExeConfig':
        logger.debug("PlanExeConfig.load() creating a new instance...")
        planexe_config_path = cls.resolve_planexe_config_path()

        if isinstance(model_profile_override, ModelProfileEnum):
            model_profile = model_profile_override
        elif isinstance(model_profile_override, str):
            model_profile = normalize_model_profile(model_profile_override)
        else:
            model_profile = resolve_model_profile_from_env()

        llm_config_json_name = resolve_llm_config_filename(
            model_profile=model_profile,
            explicit_filename=llm_config_json_name_override,
        )

        dotenv_path = cls.find_file_in_search_order(
            ConfigNameEnum.DOTENV.value,
            planexe_config_path,
            is_optional=True,
        )
        llm_config_json_path = cls.find_file_in_search_order(llm_config_json_name, planexe_config_path)

        # Safe fallback: if profile config is missing, use baseline config.
        if llm_config_json_path is None and llm_config_json_name != ConfigNameEnum.LLM_CONFIG_JSON_DEFAULT.value:
            baseline_name = ConfigNameEnum.LLM_CONFIG_JSON_DEFAULT.value
            baseline_path = cls.find_file_in_search_order(baseline_name, planexe_config_path)
            if baseline_path is not None:
                logger.warning(
                    "Selected profile config %r not found. Falling back to baseline config %r.",
                    llm_config_json_name,
                    baseline_name,
                )
                llm_config_json_name = baseline_name
                llm_config_json_path = baseline_path
                model_profile = DEFAULT_MODEL_PROFILE

        return cls(
            planexe_config_path=planexe_config_path,
            dotenv_path=dotenv_path,
            model_profile=model_profile,
            llm_config_json_name=llm_config_json_name,
            llm_config_json_path=llm_config_json_path,
        )

    @classmethod
    def resolve_planexe_config_path(cls) -> Optional[Path]:
        path_str = os.environ.get(EnvNameEnum.PLANEXE_CONFIG_PATH.value)
        if path_str is None:
            logger.debug("PLANEXE_CONFIG_PATH is not set")
            return None

        try:
            path_obj = Path(path_str)
        except Exception as e:
            logger.error(f"Invalid PLANEXE_CONFIG_PATH string '{path_str!r}': {e!r}")
            return None
        if not path_obj.is_absolute():
            logger.error(f"PLANEXE_CONFIG_PATH must be an absolute path: {path_obj!r}")
            return None
        if not path_obj.is_dir():
            logger.error(f"PLANEXE_CONFIG_PATH must be a directory: {path_obj!r}")
            return None
        logger.debug(f"Using PLANEXE_CONFIG_PATH: {path_obj!r}")
        return path_obj

    @classmethod
    def find_file_in_search_order(
        cls,
        filename: str,
        planexe_config_path: Optional[Path],
        is_optional: bool = False,
    ) -> Optional[Path]:
        if planexe_config_path is not None:
            config_file_path = planexe_config_path / filename
            if config_file_path.is_file():
                logger.debug(f"Found {filename!r} at config_file_path: {config_file_path!r}")
                return config_file_path

        cwd_file_path = Path.cwd() / filename
        if cwd_file_path.is_file():
            logger.debug(f"Found {filename!r} at cwd_file_path: {cwd_file_path!r}")
            return cwd_file_path

        root_file_path = Path(__file__).parent.parent.parent / filename
        if root_file_path.is_file():
            logger.debug(f"Found {filename!r} at root_file_path: {root_file_path!r}")
            return root_file_path

        if is_optional:
            logger.info(f"Optional file {filename!r} not found in any of the search locations (ENV_VAR, CWD, Project Root).")
        else:
            logger.warning(f"{filename!r} not found in any of the search locations (ENV_VAR, CWD, Project Root).")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = PlanExeConfig.load()
    print(f"config: {config!r}")
    config.raise_if_required_files_not_found()
