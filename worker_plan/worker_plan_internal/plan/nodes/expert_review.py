"""ExpertReviewTask - Finds experts to review the SWOT analysis and have them provide criticism."""
import json
import logging
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.expert.expert_finder import ExpertFinder
from worker_plan_internal.expert.expert_criticism import ExpertCriticism
from worker_plan_internal.expert.expert_orchestrator import ExpertOrchestrator
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.swot_analysis import SWOTAnalysisTask

logger = logging.getLogger(__name__)


class ExpertReviewTask(PlanTask):
    """Assemble a panel of domain experts and have them critique the plan."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'preproject': self.clone(PreProjectAssessmentTask),
            'project_plan': self.clone(ProjectPlanTask),
            'swot_analysis': self.clone(SWOTAnalysisTask)
        }

    def output(self):
        return self.local_target(FilenameEnum.EXPERT_CRITICISM_MARKDOWN)

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        logger.info("Finding experts to review the SWOT analysis, and having them provide criticism...")

        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['preproject']['clean'].open("r") as f:
            pre_project_assessment_dict = json.load(f)
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        swot_markdown_path = self.input()['swot_analysis']['markdown'].path
        with open(swot_markdown_path, "r", encoding="utf-8") as f:
            swot_markdown = f.read()

        # Build the query.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'pre-project assessment.json':\n{format_json_for_use_in_query(pre_project_assessment_dict)}\n\n"
            f"File 'project_plan.md':\n{project_plan_markdown}\n\n"
            f"File 'SWOT Analysis.md':\n{swot_markdown}"
        )

        # Define callback functions.
        def phase1_post_callback(expert_finder: ExpertFinder) -> None:
            raw_path = self.run_id_dir / FilenameEnum.EXPERTS_RAW.value
            cleaned_path = self.run_id_dir / FilenameEnum.EXPERTS_CLEAN.value
            expert_finder.save_raw(str(raw_path))
            expert_finder.save_cleanedup(str(cleaned_path))

        def phase2_post_callback(expert_criticism: ExpertCriticism, expert_index: int) -> None:
            file_path = self.run_id_dir / FilenameEnum.EXPERT_CRITICISM_RAW_TEMPLATE.format(expert_index + 1)
            expert_criticism.save_raw(str(file_path))

        # Execute the expert orchestration.
        expert_orchestrator = ExpertOrchestrator()
        # IDEA: max_expert_count. don't truncate to 2 experts. Interview them all in production mode.
        # IDEA: If the expert file for expert_index already exist, then there is no need to run the LLM again.
        expert_orchestrator.phase1_post_callback = phase1_post_callback
        expert_orchestrator.phase2_post_callback = phase2_post_callback
        expert_orchestrator.execute(llm_executor, query)

        # Write final expert criticism markdown.
        expert_criticism_markdown_file = self.file_path(FilenameEnum.EXPERT_CRITICISM_MARKDOWN)
        with expert_criticism_markdown_file.open("w") as f:
            f.write(expert_orchestrator.to_markdown())
