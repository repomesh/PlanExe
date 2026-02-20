"""
Locate PlanExe config files (.env and llm_config profile files).
The .env file is optional when environment variables are provided by the host.

Finds config files by checking locations in this order:
1. Directory from PLANEXE_CONFIG_PATH (must be an absolute directory path).
2. Current working directory (CWD).
3. PlanExe project root (three levels above this file).

Usage without PLANEXE_CONFIG_PATH:
PROMPT> python -m worker_plan_api.planexe_config

Usage with PLANEXE_CONFIG_PATH:
PROMPT> PLANEXE_CONFIG_PATH='/Users/neoneye/git/PlanExeGroup/PlanExe' python -m worker_plan_api.planexe_config

IDEA: validate the contents of ".env"
IDEA: validate the contents of profile config files (llm_config/*.json)
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
    LLM_CONFIG_JSON_DEFAULT = "baseline.json"


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
        """
        Raises PlanExeConfigError if required configuration files are not found.
        The .env file is optional and may be provided by the host environment.

        :raises: PlanExeConfigError when required files are missing.
        """
        missing_files = []
        if self.llm_config_json_path is None:
            missing_files.append(self.llm_config_json_name)

        if missing_files:
            msg = f"Required configuration file(s) not found: {', '.join(missing_files)}"
            logger.error(msg)
            raise PlanExeConfigError(msg)
        if self.dotenv_path is None:
            logger.info("Optional configuration file '.env' not found; relying on environment variables only.")
        # If no missing files, method completes silently.

    @classmethod
    def load(
        cls,
        model_profile_override: Optional[ModelProfileEnum | str] = None,
        llm_config_json_name_override: Optional[str] = None,
    ) -> 'PlanExeConfig':
        """
        Loads configuration paths by searching predefined locations and resolving
        the effective model profile / profile config filename.

        :param model_profile_override: Optional explicit profile override.
        :param llm_config_json_name_override: Optional explicit config filename override.
        :return: A new PlanExeConfig instance with resolved paths and profile metadata.
        """
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
        """
        Resolves and validates PLANEXE_CONFIG_PATH.
        The value must be an absolute path to an existing directory.

        :return: Path object when valid, otherwise None.
        """
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
        """
        Finds a specific configuration file based on a precedence of locations.

        Search order:
        1. Directory from validated PLANEXE_CONFIG_PATH (if provided and valid).
        2. Current Working Directory (CWD).
        3. PlanExe project root.

        :param filename: The name of the file to find (e.g., ".env").
        :param planexe_config_path: The validated absolute directory path from PLANEXE_CONFIG_PATH.
        :param is_optional: When True, missing file is logged at INFO instead of WARNING.
        :return: The Path to the file if found, otherwise None.
        """
        is_dotenv = filename == ConfigNameEnum.DOTENV.value
        root_path = Path(__file__).parent.parent.parent
        base_paths: list[Path] = []
        if planexe_config_path is not None:
            base_paths.append(planexe_config_path)
        base_paths.append(Path.cwd())
        base_paths.append(root_path)

        for base_path in base_paths:
            candidate_paths = [base_path / filename]
            if not is_dotenv:
                candidate_paths.insert(0, base_path / "llm_config" / filename)
            for candidate_path in candidate_paths:
                if candidate_path.is_file():
                    logger.debug(f"Found {filename!r} at: {candidate_path!r}")
                    return candidate_path

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
