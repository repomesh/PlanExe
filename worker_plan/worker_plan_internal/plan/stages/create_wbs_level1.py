"""CreateWBSLevel1Task - Creates the Work Breakdown Structure (WBS) Level 1."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.create_wbs_level1 import CreateWBSLevel1
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask

logger = logging.getLogger(__name__)


class CreateWBSLevel1Task(PlanTask):
    """Extract the project title and top-level phases (WBS Level 1) from the project plan."""
    def requires(self):
        return {
            'project_plan': self.clone(ProjectPlanTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.WBS_LEVEL1_RAW),
            'clean': self.local_target(FilenameEnum.WBS_LEVEL1),
            'project_title': self.local_target(FilenameEnum.WBS_LEVEL1_PROJECT_TITLE)
        }

    def run_with_llm(self, llm: LLM) -> None:
        logger.info("Creating Work Breakdown Structure (WBS) Level 1...")

        # Read the project plan JSON from the dependency.
        with self.input()['project_plan']['raw'].open("r") as f:
            project_plan_dict = json.load(f)

        # Build the query using the project plan.
        query = format_json_for_use_in_query(project_plan_dict)

        # Execute the WBS Level 1 creation.
        create_wbs_level1 = CreateWBSLevel1.execute(llm, query)

        # Save the raw output.
        wbs_level1_raw_dict = create_wbs_level1.raw_response_dict()
        with self.output()['raw'].open("w") as f:
            json.dump(wbs_level1_raw_dict, f, indent=2)

        # Save the cleaned up result.
        wbs_level1_result_json = create_wbs_level1.cleanedup_dict()
        with self.output()['clean'].open("w") as f:
            json.dump(wbs_level1_result_json, f, indent=2)

        # Save the project title.
        with self.output()['project_title'].open("w") as f:
            f.write(create_wbs_level1.project_title)

        logger.info("WBS Level 1 created successfully.")
