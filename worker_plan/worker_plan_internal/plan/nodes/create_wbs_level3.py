"""CreateWBSLevel3Task - Creates the Work Breakdown Structure (WBS) Level 3."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.create_wbs_level3 import CreateWBSLevel3
from worker_plan_internal.wbs.wbs_task import WBSProject
from worker_plan_internal.wbs.wbs_populate import WBSPopulate
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.wbs_project_level1_and_level2 import WBSProjectLevel1AndLevel2Task
from worker_plan_internal.plan.nodes.estimate_task_durations import EstimateTaskDurationsTask
from worker_plan_internal.plan.nodes.data_collection import DataCollectionTask

logger = logging.getLogger(__name__)


class CreateWBSLevel3Task(PlanTask):
    """Break Level 2 tasks into detailed subtasks (WBS Level 3)."""
    def output(self):
        return self.local_target(FilenameEnum.WBS_LEVEL3)

    def requires(self):
        return {
            'project_plan': self.clone(ProjectPlanTask),
            'wbs_project': self.clone(WBSProjectLevel1AndLevel2Task),
            'task_durations': self.clone(EstimateTaskDurationsTask),
            'data_collection': self.clone(DataCollectionTask),
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        logger.info("Creating Work Breakdown Structure (WBS) Level 3...")

        # Read inputs from required tasks.
        with self.input()['project_plan']['raw'].open("r") as f:
            project_plan_dict = json.load(f)

        with self.input()['wbs_project'].open("r") as f:
            wbs_project_dict = json.load(f)
        wbs_project = WBSProject.from_dict(wbs_project_dict)

        with self.input()['data_collection']['markdown'].open("r") as f:
            data_collection_markdown = f.read()

        # Load the estimated task durations.
        task_duration_list_path = self.input()['task_durations'].path
        WBSPopulate.extend_project_with_durations_json(wbs_project, task_duration_list_path)

        # for each task in the wbs_project, find the task that has no children
        tasks_with_no_children = []
        def visit_task(task):
            if len(task.task_children) == 0:
                tasks_with_no_children.append(task)
            else:
                for child in task.task_children:
                    visit_task(child)
        visit_task(wbs_project.root_task)

        # for each task with no children, extract the task_id
        decompose_task_id_list = []
        for task in tasks_with_no_children:
            decompose_task_id_list.append(task.id)

        logger.info("There are %d tasks to be decomposed.", len(decompose_task_id_list))

        # In production mode, all chunks are processed.
        # In developer mode, truncate to only 2 chunks for fast turnaround cycle. Otherwise LOTS of tasks are to be decomposed.
        logger.info(f"CreateWBSLevel3Task.speedvsdetail: {self.speedvsdetail}")
        if self.speedvsdetail == SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS:
            logger.info("FAST_BUT_SKIP_DETAILS mode, truncating to 2 chunks for testing.")
            decompose_task_id_list = decompose_task_id_list[:2]
        else:
            logger.info("Processing all chunks.")

        project_plan_str = format_json_for_use_in_query(project_plan_dict)
        wbs_project_str = format_json_for_use_in_query(wbs_project.to_dict())

        # Loop over each task ID.
        wbs_level3_result_accumulated = []
        total_tasks = len(decompose_task_id_list)
        for index, task_id in enumerate(decompose_task_id_list, start=1):
            logger.info("Decomposing task %d of %d", index, total_tasks)

            query = (
                f"The project plan:\n{project_plan_str}\n\n"
                f"Data collection:\n{data_collection_markdown}\n\n"
                f"Work breakdown structure:\n{wbs_project_str}\n\n"
                f"Only decompose this task:\n\"{task_id}\""
            )

            # IDEA: If the chunk file already exist, then there is no need to run the LLM again.
            def execute_create_wbs_level3(llm: LLM) -> CreateWBSLevel3:
                return CreateWBSLevel3.execute(llm, query, task_id)

            try:
                create_wbs_level3 = llm_executor.run(execute_create_wbs_level3)
            except PipelineStopRequested:
                # Re-raise PipelineStopRequested without wrapping it
                raise
            except Exception as e:
                logger.error(f"WBS Level 3 task {index} LLM interaction failed.", exc_info=True)
                raise ValueError(f"WBS Level 3 task {index} LLM interaction failed.") from e

            wbs_level3_raw_dict = create_wbs_level3.raw_response_dict()

            # Write the raw JSON for this task using the FilenameEnum template.
            raw_filename = FilenameEnum.WBS_LEVEL3_RAW_TEMPLATE.value.format(index)
            raw_chunk_path = self.run_id_dir / raw_filename
            with open(raw_chunk_path, 'w') as f:
                json.dump(wbs_level3_raw_dict, f, indent=2)

            # Accumulate the decomposed tasks.
            wbs_level3_result_accumulated.extend(create_wbs_level3.tasks)

        # Write the aggregated WBS Level 3 result.
        aggregated_path = self.file_path(FilenameEnum.WBS_LEVEL3)
        with open(aggregated_path, 'w') as f:
            json.dump(wbs_level3_result_accumulated, f, indent=2)

        logger.info("WBS Level 3 created and aggregated results written to %s", aggregated_path)
