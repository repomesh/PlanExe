"""ProjectPlanTask - Creates the project plan."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.project_plan import ProjectPlan
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.pre_project_assessment import PreProjectAssessmentTask

logger = logging.getLogger(__name__)

class ProjectPlanTask(PlanTask):
    """Generate the comprehensive project plan."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'preproject': self.clone(PreProjectAssessmentTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PROJECT_PLAN_RAW),
            'markdown': self.local_target(FilenameEnum.PROJECT_PLAN_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        logger.info("Creating plan...")

        # Read the plan prompt from SetupTask's output.
        setup_target = self.input()['setup']
        with setup_target.open("r") as f:
            plan_prompt = f.read()

        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()

        # Load the consolidated assumptions.
        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            consolidate_assumptions_markdown = f.read()

        # Read the pre-project assessment from its file.
        pre_project_assessment_file = self.input()['preproject']['clean']
        with pre_project_assessment_file.open("r") as f:
            pre_project_assessment_dict = json.load(f)

        # Build the query.
        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'pre-project-assessment.json':\n{format_json_for_use_in_query(pre_project_assessment_dict)}"
        )

        # Execute the plan creation.
        project_plan = ProjectPlan.execute(llm, query)

        # Save raw output
        project_plan.save_raw(self.output()['raw'].path)

        # Save markdown output
        project_plan.save_markdown(self.output()['markdown'].path)

        logger.info("Project plan created and saved")
