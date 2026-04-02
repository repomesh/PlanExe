"""WBSProjectLevel1AndLevel2Task - Create a WBS project from Level 1 and Level 2 JSON files."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.wbs.wbs_populate import WBSPopulate
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.create_wbs_level1 import CreateWBSLevel1Task
from worker_plan_internal.plan.stages.create_wbs_level2 import CreateWBSLevel2Task


class WBSProjectLevel1AndLevel2Task(PlanTask):
    """
    Create a WBS project from the WBS Level 1 and Level 2 JSON files.

    It depends on:
      - CreateWBSLevel1Task: providing the cleaned WBS Level 1 JSON.
      - CreateWBSLevel2Task: providing the major phases with subtasks and the task UUIDs.
    """
    def output(self):
        return self.local_target(FilenameEnum.WBS_PROJECT_LEVEL1_AND_LEVEL2)

    def requires(self):
        return {
            'wbs_level1': self.clone(CreateWBSLevel1Task),
            'wbs_level2': self.clone(CreateWBSLevel2Task),
        }

    def run_inner(self):
        wbs_level1_path = self.input()['wbs_level1']['clean'].path
        wbs_level2_path = self.input()['wbs_level2']['clean'].path
        wbs_project = WBSPopulate.project_from_level1_json(wbs_level1_path)
        WBSPopulate.extend_project_with_level2_json(wbs_project, wbs_level2_path)

        json_representation = json.dumps(wbs_project.to_dict(), indent=2)
        with self.output().open("w") as f:
            f.write(json_representation)
