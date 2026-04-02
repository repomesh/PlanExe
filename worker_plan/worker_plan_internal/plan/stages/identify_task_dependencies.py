"""IdentifyTaskDependenciesTask - Identifies the dependencies between WBS tasks."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.identify_wbs_task_dependencies import IdentifyWBSTaskDependencies
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.create_wbs_level2 import CreateWBSLevel2Task
from worker_plan_internal.plan.stages.data_collection import DataCollectionTask

logger = logging.getLogger(__name__)


class IdentifyTaskDependenciesTask(PlanTask):
    """
    This task identifies the dependencies between WBS tasks.
    """
    def output(self):
        return self.local_target(FilenameEnum.TASK_DEPENDENCIES_RAW)

    def requires(self):
        return {
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'wbs_level2': self.clone(CreateWBSLevel2Task),
            'data_collection': self.clone(DataCollectionTask),
        }

    def run_with_llm(self, llm: LLM) -> None:
        logger.info("Identifying task dependencies...")

        # Read inputs from required tasks.
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['data_collection']['markdown'].open("r") as f:
            data_collection_markdown = f.read()
        with self.input()['wbs_level2']['clean'].open("r") as f:
            major_phases_with_subtasks = json.load(f)

        # Build the query
        query = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'project_plan.md':\n{project_plan_markdown}\n\n"
            f"File 'Work Breakdown Structure.json':\n{format_json_for_use_in_query(major_phases_with_subtasks)}\n\n"
            f"File 'data_collection.md':\n{data_collection_markdown}"
        )

        # Execute the dependency identification.
        identify_dependencies = IdentifyWBSTaskDependencies.execute(llm, query)
        dependencies_raw_dict = identify_dependencies.raw_response_dict()

        # Write the raw dependencies JSON to the output file.
        with self.output().open("w") as f:
            json.dump(dependencies_raw_dict, f, indent=2)

        logger.info("Task dependencies identified and written to %s", self.output().path)
