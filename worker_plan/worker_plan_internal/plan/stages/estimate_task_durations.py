"""EstimateTaskDurationsTask - Estimates durations for WBS tasks in chunks."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.estimate_wbs_task_durations import EstimateWBSTaskDurations
from worker_plan_internal.wbs.wbs_task import WBSProject
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.wbs_project_level1_and_level2 import WBSProjectLevel1AndLevel2Task

logger = logging.getLogger(__name__)


class EstimateTaskDurationsTask(PlanTask):
    """
    This task estimates durations for WBS tasks in chunks.

    It depends on:
      - ProjectPlanTask: providing the project plan JSON.
      - WBSProjectLevel1AndLevel2Task: providing the major phases with subtasks and the task UUIDs.

    For each chunk of 3 task IDs, a raw JSON file (e.g. "011-1-task_durations_raw.json") is written,
    and an aggregated JSON file (defined by FilenameEnum.TASK_DURATIONS) is produced.

    IDEA: 1st estimate the Tasks that have zero children.
    2nd estimate tasks that have children where all children have been estimated.
    repeat until all tasks have been estimated.
    """
    def output(self):
        return self.local_target(FilenameEnum.TASK_DURATIONS)

    def requires(self):
        return {
            'project_plan': self.clone(ProjectPlanTask),
            'wbs_project': self.clone(WBSProjectLevel1AndLevel2Task),
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        logger.info("Estimating task durations...")

        # Load the project plan JSON.
        with self.input()['project_plan']['raw'].open("r") as f:
            project_plan_dict = json.load(f)

        with self.input()['wbs_project'].open("r") as f:
            wbs_project_dict = json.load(f)
        wbs_project = WBSProject.from_dict(wbs_project_dict)

        # json'ish representation of the major phases in the WBS, and their subtasks.
        root_task = wbs_project.root_task
        major_tasks = [child.to_dict() for child in root_task.task_children]
        major_phases_with_subtasks = major_tasks

        # Don't include uuid of the root task. It's the child tasks that are of interest to estimate.
        decompose_task_id_list = []
        for task in wbs_project.root_task.task_children:
            decompose_task_id_list.extend(task.task_ids())

        logger.info(f"There are {len(decompose_task_id_list)} tasks to be estimated.")

        # Split the task IDs into chunks of 3.
        task_ids_chunks = [decompose_task_id_list[i:i + 3] for i in range(0, len(decompose_task_id_list), 3)]

        # In production mode, all chunks are processed.
        # In developer mode, truncate to only 2 chunks for fast turnaround cycle. Otherwise LOTS of tasks are to be estimated.
        logger.info(f"EstimateTaskDurationsTask.speedvsdetail: {self.speedvsdetail}")
        if self.speedvsdetail == SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS:
            logger.info("FAST_BUT_SKIP_DETAILS mode, truncating to 2 chunks for testing.")
            task_ids_chunks = task_ids_chunks[:2]
        else:
            logger.info("Processing all chunks.")

        # Process each chunk.
        accumulated_task_duration_list = []
        for index, task_ids_chunk in enumerate(task_ids_chunks, start=1):
            logger.info("Processing chunk %d of %d", index, len(task_ids_chunks))

            query = EstimateWBSTaskDurations.format_query(
                project_plan_dict,
                major_phases_with_subtasks,
                task_ids_chunk
            )

            # IDEA: If the chunk file already exist, then there is no need to run the LLM again.
            def execute_estimate_task_durations(llm: LLM) -> EstimateWBSTaskDurations:
                return EstimateWBSTaskDurations.execute(llm, query)

            try:
                estimate_durations = llm_executor.run(execute_estimate_task_durations)
            except PipelineStopRequested:
                # Re-raise PipelineStopRequested without wrapping it
                raise
            except Exception as e:
                logger.error(f"Task durations chunk {index} LLM interaction failed.", exc_info=True)
                raise ValueError(f"Task durations chunk {index} LLM interaction failed.") from e

            durations_raw_dict = estimate_durations.raw_response_dict()

            # Write the raw JSON for this chunk.
            filename = FilenameEnum.TASK_DURATIONS_RAW_TEMPLATE.format(index)
            raw_chunk_path = self.run_id_dir / filename
            with open(raw_chunk_path, "w") as f:
                json.dump(durations_raw_dict, f, indent=2)

            accumulated_task_duration_list.extend(durations_raw_dict.get('task_details', []))

        # Write the aggregated task durations.
        aggregated_path = self.file_path(FilenameEnum.TASK_DURATIONS)
        with open(aggregated_path, "w") as f:
            json.dump(accumulated_task_duration_list, f, indent=2)

        logger.info("Task durations estimated and aggregated results written to %s", aggregated_path)
