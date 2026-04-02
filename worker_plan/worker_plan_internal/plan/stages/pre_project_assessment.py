"""PreProjectAssessmentTask - Conducts pre-project assessment."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.expert.pre_project_assessment import PreProjectAssessment
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask

logger = logging.getLogger(__name__)


class PreProjectAssessmentTask(PlanTask):
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PRE_PROJECT_ASSESSMENT_RAW),
            'clean': self.local_target(FilenameEnum.PRE_PROJECT_ASSESSMENT)
        }

    def run_with_llm(self, llm: LLM) -> None:
        logger.info("Conducting pre-project assessment...")

        # Read the plan prompt from the SetupTask's output.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()

        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()

        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            consolidate_assumptions_markdown = f.read()

        # Build the query.
        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}"
        )

        # Execute the pre-project assessment.
        pre_project_assessment = PreProjectAssessment.execute(llm, query)

        # Save raw output.
        raw_path = self.file_path(FilenameEnum.PRE_PROJECT_ASSESSMENT_RAW)
        pre_project_assessment.save_raw(str(raw_path))

        # Save cleaned pre-project assessment.
        clean_path = self.file_path(FilenameEnum.PRE_PROJECT_ASSESSMENT)
        pre_project_assessment.save_preproject_assessment(str(clean_path))
