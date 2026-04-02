"""CreateWBSLevel2Task - Creates the Work Breakdown Structure (WBS) Level 2."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.create_wbs_level2 import CreateWBSLevel2
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.create_wbs_level1 import CreateWBSLevel1Task
from worker_plan_internal.plan.stages.data_collection import DataCollectionTask

logger = logging.getLogger(__name__)


class CreateWBSLevel2Task(PlanTask):
    """
    Creates the Work Breakdown Structure (WBS) Level 2.
    Depends on:
      - ProjectPlanTask: provides the project plan as JSON.
      - CreateWBSLevel1Task: provides the cleaned WBS Level 1 result.
    Produces:
      - Raw WBS Level 2 output (007-wbs_level2_raw.json)
      - Cleaned WBS Level 2 output (008-wbs_level2.json)
    """
    def requires(self):
        return {
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'wbs_level1': self.clone(CreateWBSLevel1Task),
            'data_collection': self.clone(DataCollectionTask),
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.WBS_LEVEL2_RAW),
            'clean': self.local_target(FilenameEnum.WBS_LEVEL2)
        }

    def run_with_llm(self, llm: LLM) -> None:
        logger.info("Creating Work Breakdown Structure (WBS) Level 2...")

        # Read inputs from required tasks.
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['data_collection']['markdown'].open("r") as f:
            data_collection_markdown = f.read()
        with self.input()['wbs_level1']['clean'].open("r") as f:
            wbs_level1_result_json = json.load(f)

        query = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'project_plan.md':\n{project_plan_markdown}\n\n"
            f"File 'WBS Level 1.json':\n{format_json_for_use_in_query(wbs_level1_result_json)}\n\n"
            f"File 'data_collection.md':\n{data_collection_markdown}"
        )

        # Execute the WBS Level 2 creation.
        create_wbs_level2 = CreateWBSLevel2.execute(llm, query)

        # Retrieve and write the raw output.
        wbs_level2_raw_dict = create_wbs_level2.raw_response_dict()
        with self.output()['raw'].open("w") as f:
            json.dump(wbs_level2_raw_dict, f, indent=2)

        # Retrieve and write the cleaned output (e.g. major phases with subtasks).
        with self.output()['clean'].open("w") as f:
            json.dump(create_wbs_level2.major_phases_with_subtasks, f, indent=2)

        logger.info("WBS Level 2 created successfully.")
