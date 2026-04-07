"""WBSProjectLevel1AndLevel2AndLevel3Task - Create a WBS project from Level 1, Level 2 and Level 3 JSON files."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.wbs.wbs_task import WBSProject
from worker_plan_internal.wbs.wbs_populate import WBSPopulate
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.wbs_project_level1_and_level2 import WBSProjectLevel1AndLevel2Task
from worker_plan_internal.plan.nodes.create_wbs_level3 import CreateWBSLevel3Task


class WBSProjectLevel1AndLevel2AndLevel3Task(PlanTask):
    """Merge all three WBS levels into the complete project hierarchy (JSON + CSV)."""
    def output(self):
        return {
            'full': self.local_target(FilenameEnum.WBS_PROJECT_LEVEL1_AND_LEVEL2_AND_LEVEL3_FULL),
            'csv': self.local_target(FilenameEnum.WBS_PROJECT_LEVEL1_AND_LEVEL2_AND_LEVEL3_CSV)
        }

    def requires(self):
        return {
            'wbs_project12': self.clone(WBSProjectLevel1AndLevel2Task),
            'wbs_level3': self.clone(CreateWBSLevel3Task),
        }

    def run_inner(self):
        wbs_project_path = self.input()['wbs_project12'].path
        with open(wbs_project_path, "r") as f:
            wbs_project_dict = json.load(f)
        wbs_project = WBSProject.from_dict(wbs_project_dict)

        wbs_level3_path = self.input()['wbs_level3'].path
        WBSPopulate.extend_project_with_decomposed_tasks_json(wbs_project, wbs_level3_path)

        json_representation = json.dumps(wbs_project.to_dict(), indent=2)
        with self.output()['full'].open("w") as f:
            f.write(json_representation)

        csv_representation = wbs_project.to_csv_string()
        with self.output()['csv'].open("w") as f:
            f.write(csv_representation)
