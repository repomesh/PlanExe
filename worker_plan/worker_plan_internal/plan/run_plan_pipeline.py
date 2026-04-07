"""
PROMPT> python -m worker_plan_internal.plan.run_plan_pipeline

In order to resume an unfinished run.
Insert the run_id_dir of the thing you want to resume.
If it's an already finished run, then remove the "999-pipeline_complete.txt" file.
PROMPT> RUN_ID_DIR=/absolute/path/to/PlanExe_20250216_150332 python -m worker_plan_internal.plan.run_plan_pipeline
"""
from dataclasses import dataclass, field
from datetime import datetime
import os
import logging
import json
import re
from typing import Any, Optional
import luigi
from pathlib import Path
import sys
from llama_index.core.llms.llm import LLM
from worker_plan_api.filenames import FilenameEnum, ExtraFilenameEnum
from worker_plan_api.pipeline_version import PIPELINE_VERSION
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_internal.utils.planexe_llmconfig import PlanExeLLMConfig
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelFromName, ShouldStopCallbackParameters, PipelineStopRequested, RetryConfig
from worker_plan_internal.llm_factory import get_llm_names_by_priority, SPECIAL_AUTO_ID, is_valid_llm_name
from worker_plan_api.model_profile import ModelProfileEnum, normalize_model_profile
from worker_plan_internal.luigi_util.obtain_output_files import ObtainOutputFiles
from worker_plan_internal.plan.pipeline_environment import PipelineEnvironment
from worker_plan_internal.plan.ping_llm import run_ping_llm_report

logger = logging.getLogger(__name__)
DEFAULT_LLM_MODEL = "ollama-llama3.1"

REPORT_EXECUTE_PLAN_SECTION_HIDDEN = True
# REPORT_EXECUTE_PLAN_SECTION_HIDDEN = False

class PlanTask(luigi.Task):
    # PLANEXE_OUTPUTS_DIR: Configurable pipeline outputs directory
    # ============================================================
    # WHY IT EXISTS:
    #   Pipeline outputs were previously stored in a directory that was not covered
    #   by .gitignore. A `git clean` operation destroyed hours of live pipeline
    #   computation data. The default `run/` directory is now gitignored, which
    #   prevents accidental git-related data loss. This env var adds optional
    #   flexibility for operators who want outputs on a separate filesystem
    #   (e.g., an external drive or mounted volume for performance/backup).
    #
    # WHAT IT DOES:
    #   Allows pipeline operators to place pipeline outputs (run directories, logs,
    #   results) outside the git repository using the PLANEXE_OUTPUTS_DIR environment
    #   variable. Useful for large/long-running pipelines where output isolation or
    #   separate storage is desired.
    #
    # DEFAULT BEHAVIOR:
    #   Falls back to 'run/' (gitignored, safe by default). No action required
    #   from existing operators unless they want a different output location.
    #
    # EXAMPLE:
    #   export PLANEXE_OUTPUTS_DIR=/mnt/fast-storage/planexe-runs
    #   python -m worker_plan_internal.plan.run_plan_pipeline
    #
    # Default it to the current timestamp, eg. 19841231_235959
    # Path to the 'run/{run_id}' directory
    _default_outputs_dir = os.getenv('PLANEXE_OUTPUTS_DIR', 'run')
    run_id_dir = luigi.Parameter(default=Path(_default_outputs_dir) / datetime.now().strftime("%Y%m%d_%H%M%S"))

    # By default, run everything but it's slow.
    # This can be overridden in developer mode, where a quick turnaround is needed, and the details are not important.
    speedvsdetail = luigi.EnumParameter(enum=SpeedVsDetailEnum, default=SpeedVsDetailEnum.ALL_DETAILS_BUT_SLOW)

    # List of LLM models to try, in order of priority.
    llm_models = luigi.ListParameter(default=[DEFAULT_LLM_MODEL])

    # Optional callback for updating progress bar and aborting the pipeline.
    # If the callback raises PipelineStopRequested, the pipeline will be aborted. This is the only exception that is allowed to be raised.
    # If the callback raises exceptions different than PipelineStopRequested, the pipeline will be aborted. This means that something went wrong, and we should not continue.
    # If the callback doesn't raise an exception, the pipeline will continue.
    # If the callback is not provided, the pipeline will run until completion.
    _pipeline_executor_callback = luigi.Parameter(default=None, significant=False, visibility=luigi.parameter.ParameterVisibility.PRIVATE)

    @classmethod
    def description(cls) -> str:
        """Brief description of what this task does.

        Default returns the first line of the class docstring.
        Override in subclasses for a custom description.
        """
        doc = cls.__doc__
        if doc:
            return doc.strip().split("\n")[0].strip()
        return ""

    def file_path(self, filename: FilenameEnum) -> Path:
        return self.run_id_dir / filename.value

    def local_target(self, filename: FilenameEnum) -> luigi.LocalTarget:
        return luigi.LocalTarget(self.file_path(filename))

    def create_llm_executor(self) -> LLMExecutor:
        """
        Create an LLMExecutor instance.
        - Responsible for stopping the pipeline when the user presses Ctrl-C or closes the browser tab.
        - Fallback mechanism to try the next LLM if the current one fails.
        """
        # Redirect the callback to the pipeline_executor_callback.
        def should_stop_callback(parameters: ShouldStopCallbackParameters) -> None:
            if self._pipeline_executor_callback is None:
                return
            # The pipeline_executor_callback expects (task, duration) but we have ShouldStopCallbackParameters
            total_duration = parameters.total_duration
            self._pipeline_executor_callback(self, total_duration)

        llm_model_instances = LLMModelFromName.from_names(self.llm_models)

        return LLMExecutor(
            llm_models=llm_model_instances,
            should_stop_callback=should_stop_callback,
            retry_config=RetryConfig(),
        )

    def run(self):
        """
        Don't override this method. Instead either override the run_inner() method, or override the run_with_llm() method.
        """
        try:
            self.run_inner()
        except PipelineStopRequested as e:
            logger.debug(f"{self.__class__.__name__} -> PipelineStopRequested raised: {e}")
            # This exception is raised by the should_stop_callback
            # If we get here, it means that the pipeline was aborted by the callback, such as by the user pressing Ctrl-C or closing the browser tab.
            # Create a flag file to signal that the stop was intentional.
            flag_path = self.run_id_dir / ExtraFilenameEnum.PIPELINE_STOP_REQUESTED_FLAG.value
            logger.info(f"Creating stop flag file: {flag_path!r}")
            flag_path.touch()
            raise
        except Exception as e:
            # Re-raise the exception with a more descriptive message
            raise Exception(f"Failed to run {self.__class__.__name__} with any of the LLMs in the list: {self.llm_models!r} for run_id_dir: {self.run_id_dir!r}") from e

    def run_inner(self):
        """
        Override this method or the run_with_llm() method.
        """
        llm_executor: LLMExecutor = self.create_llm_executor()

        # Attempt executing this code with the first LLM, if that fails, try the next one, and so on.
        def execute_function(llm: LLM) -> None:
            self.run_with_llm(llm)

        # Make multiple attempts at running the run_with_llm() function.
        # No try/except needed here. Let PlanTask.run() handle it.
        llm_executor.run(execute_function)

    def run_with_llm(self, llm: LLM) -> None:
        """
        Override this method or the run_inner() method.
        """
        raise NotImplementedError("Subclasses must implement this method.")


# ---------------------------------------------------------------------------
# Task class definitions have been extracted to individual files under
# worker_plan_internal/plan/nodes/.  The pipeline orchestrator that wires
# them together lives in nodes/full_plan_pipeline.py.
# ---------------------------------------------------------------------------


def _task_class_to_step_label(class_name: str) -> str:
    """Convert a PlanTask class name to a human-readable step label.

    Examples: ``SWOTAnalysisTask`` → ``"SWOT Analysis"``,
    ``GovernancePhase1AuditTask`` → ``"Governance Phase 1 Audit"``.
    """
    name = class_name.removesuffix("Task")
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    name = re.sub(r"(?<=[a-zA-Z])(?=\d)", " ", name)
    name = re.sub(r"(?<=\d)(?=[a-zA-Z])", " ", name)
    return name


@dataclass
class PipelineProgress:
    progress_message: str
    progress_percentage: float
    steps_completed: int
    steps_total: int
    current_step: str = ""


@dataclass
class HandleTaskCompletionParameters:
    task: PlanTask
    progress: PipelineProgress
    duration: float


@dataclass
class ExecutePipeline:
    run_id_dir: Path
    speedvsdetail: SpeedVsDetailEnum
    llm_models: list[str]
    model_profile: ModelProfileEnum = ModelProfileEnum.BASELINE
    full_plan_pipeline_task: Optional[Any] = field(default=None)
    all_expected_filenames: list[str] = field(default_factory=list)
    luigi_build_return_value: Optional[bool] = field(default=None, init=False)

    def setup(self) -> None:
        # Check that the run_id_dir exists and contains the required files.
        if not self.run_id_dir.exists():
            raise FileNotFoundError(f"The run_id_dir does not exist: {self.run_id_dir!r}")
        if not self.run_id_dir.is_dir():
            raise NotADirectoryError(f"The run_id_dir is not a directory: {self.run_id_dir!r}")
        if not (self.run_id_dir / FilenameEnum.START_TIME.value).exists():
            raise FileNotFoundError(f"The '{FilenameEnum.START_TIME.value}' file does not exist in the run_id_dir: {self.run_id_dir!r}")
        if not (self.run_id_dir / FilenameEnum.INITIAL_PLAN.value).exists():
            raise FileNotFoundError(f"The '{FilenameEnum.INITIAL_PLAN.value}' file does not exist in the run_id_dir: {self.run_id_dir!r}")

        from worker_plan_internal.plan.nodes.full_plan_pipeline import FullPlanPipeline
        full_plan_pipeline_task = FullPlanPipeline(
            run_id_dir=self.run_id_dir,
            speedvsdetail=self.speedvsdetail,
            llm_models=self.llm_models,
            _pipeline_executor_callback=self.callback_run_task
        )
        self.full_plan_pipeline_task = full_plan_pipeline_task

        # Obtain a list of all the expected output files of the FullPlanPipeline task and all its dependencies
        obtain_output_files = ObtainOutputFiles.execute(full_plan_pipeline_task)
        self.all_expected_filenames = obtain_output_files.get_all_filenames()

    def resolve_luigi_workers(self) -> int:
        default_workers = 1
        try:
            llm_config = PlanExeLLMConfig.load(model_profile=self.model_profile)
        except Exception as exc:
            logger.warning(
                f"Could not load selected llm_config/<profile>.json; defaulting Luigi workers to {default_workers}: {exc}"
            )
            return default_workers

        workers_candidates: list[int] = []
        for llm_name in self.llm_models:
            config = llm_config.llm_config_dict.get(llm_name)
            if not isinstance(config, dict):
                continue
            luigi_workers_value = config.get("luigi_workers")
            if luigi_workers_value is None:
                continue
            try:
                luigi_workers_int = int(luigi_workers_value)
            except (TypeError, ValueError):
                logger.warning(f"Invalid luigi_workers for {llm_name!r}: {luigi_workers_value!r}")
                continue
            if luigi_workers_int < 1:
                logger.warning(f"Invalid luigi_workers for {llm_name!r}: {luigi_workers_int!r}")
                continue
            workers_candidates.append(luigi_workers_int)

        if not workers_candidates:
            return default_workers
        return min(workers_candidates)

    @classmethod
    def resolve_llm_models(
        cls,
        specified_llm_model: Optional[str],
        model_profile: ModelProfileEnum = ModelProfileEnum.BASELINE,
    ) -> list[str]:
        llm_models = get_llm_names_by_priority(model_profile=model_profile)
        if len(llm_models) == 0:
            logger.error(
                "No LLM models found. Please check your selected llm_config/<profile>.json file and add 'priority' values."
            )
            llm_models = [DEFAULT_LLM_MODEL]

        if specified_llm_model:
            llm_model = specified_llm_model
            logger.info(f"Using the specified LLM model: {llm_model!r}")
            if llm_model != SPECIAL_AUTO_ID:
                if not is_valid_llm_name(llm_model, model_profile=model_profile):
                    logger.error(
                        f"Invalid LLM model: {llm_model!r}. Please check your selected llm_config/<profile>.json file and add the model."
                    )
                    raise ValueError(
                        f"Invalid LLM model: {llm_model!r}. Please check your selected llm_config/<profile>.json file and add the model."
                    )
                llm_models = [llm_model]

        logger.info("These are the LLM models that will be used in the pipeline:")
        for index, llm_name in enumerate(llm_models):
            logger.info(f"{index}. {llm_name!r}")
        return llm_models

    def get_progress_percentage(self) -> PipelineProgress:
        files = []
        try:
            if self.run_id_dir.exists() and self.run_id_dir.is_dir():
                files = [f.name for f in self.run_id_dir.iterdir()]
        except OSError as e:
            logger.warning(f"Could not list files in {run_id_dir}: {e}")

        ignore_files = [
            ExtraFilenameEnum.EXPECTED_FILENAMES1_JSON.value,
            ExtraFilenameEnum.LOG_TXT.value,
            ExtraFilenameEnum.PIPELINE_STOP_REQUESTED_FLAG.value,
            ExtraFilenameEnum.USAGE_METRICS_JSONL.value,
            '.DS_Store',
        ]
        files = [f for f in files if f not in ignore_files]
        # logger.debug(f"Files in run_id_dir for {job.run_id}: {files}") # Debug, can be noisy
        # logger.debug(f"Number of files in run_id_dir for {job.run_id}: {len(files)}") # Debug

        # Determine the progress, by comparing the generated files with the expected_filenames1.json
        set_files = set(files)
        set_expected_files = set(self.all_expected_filenames)
        intersection_files = set_files & set_expected_files
        extra_files = set_files - set_expected_files
        # if len(extra_files) > 0:
        #     logger.debug(f"Extra files: {extra_files}")
        progress_message_long = f"{len(intersection_files)} of {len(set_expected_files)}. Extra files: {len(extra_files)}"
        progress_message_short = f"{len(intersection_files)} of {len(set_expected_files)}"
        progress_message = progress_message_short if len(extra_files) == 0 else progress_message_long
        progress_percentage: float = 0.0
        if len(set_expected_files) > 0:
            progress_percentage = (len(intersection_files) * 100.0) / len(set_expected_files)

        return PipelineProgress(
            progress_message=progress_message,
            progress_percentage=progress_percentage,
            steps_completed=len(intersection_files),
            steps_total=len(set_expected_files),
        )

    def _handle_task_completion(self, parameters: HandleTaskCompletionParameters) -> None:
        """
        Protected hook method for custom logic after a task completes.
        This method is called by callback_run_task.
        Subclasses can override this to implement custom behaviors such as:
        - Updating a database with the latest progress.
        - Checking an external source (like a database flag) to determine if the pipeline should continue or be aborted.

        Args:
            parameters: Details about the PlanTask instance that has successfully completed.
                 The `self` of this method is the ExecutePipeline instance,
                 so you can access `self.run_id_dir`, `self.get_progress_percentage()`, etc.

        Raises:
            PipelineStopRequested: To abort the pipeline execution.
        """
        logger.debug(f"ExecutePipeline._handle_task_completion: Default behavior for task {parameters.task.task_id} in run {self.run_id_dir}. Pipeline will continue.")
        # Default implementation simply allows the pipeline to continue.
        # Subclasses will provide meaningful implementations here.

    def callback_run_task(self, task: PlanTask, duration: float) -> None:
        logger.debug(f"ExecutePipeline.callback_run_task: Current task_id: {task.task_id}. Duration: {duration:.2f} seconds")

        progress: PipelineProgress = self.get_progress_percentage()
        progress.current_step = _task_class_to_step_label(task.__class__.__name__)
        logger.debug(f"ExecutePipeline.callback_run_task: Current progress for run {self.run_id_dir}: {progress!r}")

        parameters = HandleTaskCompletionParameters(task=task, progress=progress, duration=duration)

        # Delegate custom handling (like DB updates or stop checks) to the hook method.
        self._handle_task_completion(parameters)

    @property
    def has_pipeline_complete_file(self) -> bool:
        file_path = self.run_id_dir / FilenameEnum.PIPELINE_COMPLETE.value
        return file_path.exists()

    @property
    def has_report_file(self) -> bool:
        file_path = self.run_id_dir / FilenameEnum.REPORT.value
        return file_path.exists()

    @property
    def has_stop_flag_file(self) -> bool:
        file_path = self.run_id_dir / ExtraFilenameEnum.PIPELINE_STOP_REQUESTED_FLAG.value
        return file_path.exists()

    def run(self):
        # Clean up any pre-existing stop flag before the run.
        stop_flag_path = self.run_id_dir / ExtraFilenameEnum.PIPELINE_STOP_REQUESTED_FLAG.value
        if stop_flag_path.exists():
            logger.debug(f"Removing pre-existing stop flag file: {stop_flag_path!r}")
            stop_flag_path.unlink()

        # Enable file-based usage metrics for this run.
        from worker_plan_internal.llm_util.usage_metrics import set_usage_metrics_path
        usage_metrics_path = self.run_id_dir / ExtraFilenameEnum.USAGE_METRICS_JSONL.value
        set_usage_metrics_path(usage_metrics_path)
        logger.info(f"Usage metrics will be written to {usage_metrics_path}")

        # create a json file with the expected filenames. Save it to the run/run_id/expected_filenames1.json
        expected_filenames_path = self.run_id_dir / ExtraFilenameEnum.EXPECTED_FILENAMES1_JSON.value
        with open(expected_filenames_path, "w") as f:
            json.dump(self.all_expected_filenames, f, indent=2)
        logger.info(f"Saved {len(self.all_expected_filenames)} expected filenames to {expected_filenames_path}")

        # Write pipeline metadata so the version is preserved in the zip snapshot.
        metadata_path = self.run_id_dir / FilenameEnum.PLANEXE_METADATA.value
        with open(metadata_path, "w") as f:
            json.dump({"pipeline_version": PIPELINE_VERSION}, f, indent=2)
        logger.info(f"Wrote pipeline metadata (pipeline_version={PIPELINE_VERSION}) to {metadata_path}")

        luigi_workers = self.resolve_luigi_workers()
        logger.info(f"Luigi workers: {luigi_workers}")
        self.luigi_build_return_value = luigi.build(
            [self.full_plan_pipeline_task],
            local_scheduler=True,
            workers=luigi_workers
        )

        # Clear the usage metrics path after the run.
        set_usage_metrics_path(None)

        # After the pipeline finishes (or fails), check for the stop flag.
        if self.has_stop_flag_file:
            logger.info("Pipeline was stopped intentionally via PipelineStopRequested exception.")

        logger.info(f"luigi_build_return_value: {self.luigi_build_return_value}")
        logger.info(f"has_pipeline_complete_file: {self.has_pipeline_complete_file}")
        logger.info(f"has_report_file: {self.has_report_file}")
        logger.info(f"has_stop_flag_file: {self.has_stop_flag_file}")

class DemoStoppingExecutePipeline(ExecutePipeline):
    """
    Exercise the pipeline stopping mechanism.
    when a task completes it raises PipelineStopRequested and causes the pipeline to stop.
    """
    def _handle_task_completion(self, parameters: HandleTaskCompletionParameters) -> None:
        logger.info("DemoStoppingExecutePipeline._handle_task_completion: Demo of stopping the pipeline.")
        raise PipelineStopRequested("Demo: Stopping the pipeline after task completion")


def configure_logging(run_id_dir: Path) -> int:
    """
    Configure logging for console (plain text) and file output.
    Returns the console log level that was applied.
    """
    level_name = os.environ.get("PLANEXE_LOG_LEVEL", "INFO").upper()
    resolved_level = getattr(logging, level_name, None)
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setLevel(resolved_level)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    log_file: Path = run_id_dir / ExtraFilenameEnum.LOG_TXT.value
    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    return resolved_level


if __name__ == '__main__':
    from llama_index.core.instrumentation import get_dispatcher
    from worker_plan_internal.llm_util.track_activity import TrackActivity
    from worker_plan_internal.llm_util.token_instrumentation import set_current_task_id

    pipeline_environment = PipelineEnvironment.from_env()
    try:
        run_id_dir: Path = pipeline_environment.get_run_id_dir()
    except ValueError as e:
        msg = f"RUN_ID_DIR is not set or invalid. Error getting run_id_dir: {e!r}"
        logger.error(msg)
        print(f"Exiting... {msg}")
        sys.exit(1)

    # Initialize token tracking with the task identifier.
    task_id = os.environ.get("PLANEXE_TASK_ID")
    set_current_task_id(task_id)
    if not task_id:
        logger.warning("PLANEXE_TASK_ID not set. Token metrics will not be recorded.")
    logger.info(f"Initialized token tracking for task_id: {task_id}")

    console_level = configure_logging(run_id_dir)
    logger.info(
        "pipeline_environment: %r (log_level=%s)",
        pipeline_environment,
        logging.getLevelName(console_level),
    )

    # Example logging messages
    if False:
        logger.debug("This is a debug message.")
        logger.info("This is an info message.")
        logger.warning("This is a warning message.")
        logger.error("This is an error message.")
        logger.critical("This is a critical message.")

    speedvsdetail = SpeedVsDetailEnum.ALL_DETAILS_BUT_SLOW
    speedvsdetail_value = pipeline_environment.speed_vs_detail
    if speedvsdetail_value:
        found = False
        for e in SpeedVsDetailEnum:
            if e.value.lower() == speedvsdetail_value.lower():
                speedvsdetail = e
                found = True
                logger.info(f"Setting Speed vs Detail: {speedvsdetail}")
                break
        if not found:
            logger.error(f"Invalid value for SPEED_VS_DETAIL: {speedvsdetail_value}")
    logger.info(f"Speed vs Detail: {speedvsdetail}")

    if False:
        raise Exception("This is a test exception.")

    # logger.info("Environment variables Luigi:\n" + get_env_as_string() + "\n\n\n")

    model_profile = normalize_model_profile(pipeline_environment.model_profile)
    logger.info(f"Model profile: {model_profile.value}")

    llm_models = ExecutePipeline.resolve_llm_models(
        pipeline_environment.llm_model,
        model_profile=model_profile,
    )

    if speedvsdetail == SpeedVsDetailEnum.PING_LLM:
        try:
            run_ping_llm_report(
                run_id_dir=run_id_dir,
                llm_models=LLMModelFromName.from_names(llm_models),
            )
        except Exception as e:
            logger.error("PING_LLM failed: %s", e, exc_info=True)
            sys.exit(1)
        sys.exit(0)

    if True:
        track_activity = TrackActivity(jsonl_file_path=run_id_dir / ExtraFilenameEnum.TRACK_ACTIVITY_JSONL.value, write_to_logger=False)
        get_dispatcher().add_event_handler(track_activity)

    if True:
        execute_pipeline = ExecutePipeline(
            run_id_dir=run_id_dir,
            speedvsdetail=speedvsdetail,
            llm_models=llm_models,
            model_profile=model_profile,
        )
    else:
        execute_pipeline = DemoStoppingExecutePipeline(
            run_id_dir=run_id_dir,
            speedvsdetail=speedvsdetail,
            llm_models=llm_models,
            model_profile=model_profile,
        )

    try:
        execute_pipeline.setup()
    except Exception as e:
        logger.error(f"Failed to setup pipeline: {e}")
        sys.exit(1)

    logger.info(f"execute_pipeline: {execute_pipeline!r}")

    try:
        execute_pipeline.run()
    except Exception as e:
        logger.error(f"Failed to run pipeline: {e}")
        sys.exit(1)
