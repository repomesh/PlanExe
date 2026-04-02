"""CreatePitchTask - Create a pitch that explains the project plan from multiple perspectives."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.pitch.create_pitch import CreatePitch
from worker_plan_internal.wbs.wbs_task import WBSProject
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.wbs_project_level1_and_level2 import WBSProjectLevel1AndLevel2Task
from worker_plan_internal.plan.stages.related_resources import RelatedResourcesTask

logger = logging.getLogger(__name__)


class CreatePitchTask(PlanTask):
    """
    Create a the pitch that explains the project plan, from multiple perspectives.

    This task depends on:
      - ProjectPlanTask: provides the project plan JSON.
      - WBSProjectLevel1AndLevel2Task: containing the top level of the project plan.

    The resulting pitch JSON is written to the file specified by FilenameEnum.PITCH.
    """
    def output(self):
        return self.local_target(FilenameEnum.PITCH_RAW)

    def requires(self):
        return {
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'wbs_project': self.clone(WBSProjectLevel1AndLevel2Task),
            'related_resources': self.clone(RelatedResourcesTask)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read the project plan JSON.
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()

        with self.input()['wbs_project'].open("r") as f:
            wbs_project_dict = json.load(f)
        wbs_project = WBSProject.from_dict(wbs_project_dict)
        wbs_project_json = wbs_project.to_dict()

        with self.input()['related_resources']['markdown'].open("r") as f:
            related_resources_markdown = f.read()

        # Build the query
        query = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'project_plan.md':\n{project_plan_markdown}\n\n"
            f"File 'Work Breakdown Structure.json':\n{format_json_for_use_in_query(wbs_project_json)}\n\n"
            f"File 'similar_projects.md':\n{related_resources_markdown}"
        )

        # Execute the pitch creation.
        create_pitch = CreatePitch.execute(llm, query)
        pitch_dict = create_pitch.raw_response_dict()

        # Write the resulting pitch JSON to the output file.
        with self.output().open("w") as f:
            json.dump(pitch_dict, f, indent=2)

        logger.info("Pitch created and written to %s", self.output().path)
