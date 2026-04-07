"""SelfAuditTask - Performs a self-audit of the plan."""
import logging
from typing import Optional
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.self_audit.self_audit import SelfAudit
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.data_collection import DataCollectionTask
from worker_plan_internal.plan.nodes.related_resources import RelatedResourcesTask
from worker_plan_internal.plan.nodes.swot_analysis import SWOTAnalysisTask
from worker_plan_internal.plan.nodes.team_markdown import TeamMarkdownTask
from worker_plan_internal.plan.nodes.convert_pitch_to_markdown import ConvertPitchToMarkdownTask
from worker_plan_internal.plan.nodes.expert_review import ExpertReviewTask
from worker_plan_internal.plan.nodes.consolidate_governance import ConsolidateGovernanceTask
from worker_plan_internal.plan.nodes.markdown_documents import MarkdownWithDocumentsToCreateAndFindTask
from worker_plan_internal.plan.nodes.wbs_project_level1_level2_level3 import WBSProjectLevel1AndLevel2AndLevel3Task
from worker_plan_internal.plan.nodes.review_plan import ReviewPlanTask
from worker_plan_internal.plan.nodes.questions_and_answers import QuestionsAndAnswersTask
from worker_plan_internal.plan.nodes.premortem import PremortemTask

logger = logging.getLogger(__name__)


class SelfAuditTask(PlanTask):
    """Checklist-based diagnostic: find gaps, contradictions, and unsupported claims across all stages."""

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.SELF_AUDIT_RAW),
            'markdown': self.local_target(FilenameEnum.SELF_AUDIT_MARKDOWN)
        }

    def requires(self):
        return {
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'team_markdown': self.clone(TeamMarkdownTask),
            'related_resources': self.clone(RelatedResourcesTask),
            'consolidate_governance': self.clone(ConsolidateGovernanceTask),
            'swot_analysis': self.clone(SWOTAnalysisTask),
            'pitch_markdown': self.clone(ConvertPitchToMarkdownTask),
            'data_collection': self.clone(DataCollectionTask),
            'documents_to_create_and_find': self.clone(MarkdownWithDocumentsToCreateAndFindTask),
            'wbs_project123': self.clone(WBSProjectLevel1AndLevel2AndLevel3Task),
            'expert_review': self.clone(ExpertReviewTask),
            'project_plan': self.clone(ProjectPlanTask),
            'review_plan': self.clone(ReviewPlanTask),
            'questions_and_answers': self.clone(QuestionsAndAnswersTask),
            'premortem': self.clone(PremortemTask)
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        # Read inputs from required tasks.
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            assumptions_markdown = f.read()
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['data_collection']['markdown'].open("r") as f:
            data_collection_markdown = f.read()
        with self.input()['related_resources']['markdown'].open("r") as f:
            related_resources_markdown = f.read()
        with self.input()['swot_analysis']['markdown'].open("r") as f:
            swot_analysis_markdown = f.read()
        with self.input()['team_markdown'].open("r") as f:
            team_markdown = f.read()
        with self.input()['pitch_markdown']['markdown'].open("r") as f:
            pitch_markdown = f.read()
        with self.input()['expert_review'].open("r") as f:
            expert_review = f.read()
        with self.input()['wbs_project123']['csv'].open("r") as f:
            wbs_project_csv = f.read()
        with self.input()['review_plan']['markdown'].open("r") as f:
            review_plan_markdown = f.read()
        with self.input()['questions_and_answers']['markdown'].open("r") as f:
            questions_and_answers_markdown = f.read()
        with self.input()['premortem']['markdown'].open("r") as f:
            premortem_markdown = f.read()

        # Build the query.
        user_prompt = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{assumptions_markdown}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'data-collection.md':\n{data_collection_markdown}\n\n"
            f"File 'related-resources.md':\n{related_resources_markdown}\n\n"
            f"File 'swot-analysis.md':\n{swot_analysis_markdown}\n\n"
            f"File 'team.md':\n{team_markdown}\n\n"
            f"File 'pitch.md':\n{pitch_markdown}\n\n"
            f"File 'expert-review.md':\n{expert_review}\n\n"
            f"File 'work-breakdown-structure.csv':\n{wbs_project_csv}\n\n"
            f"File 'review-plan.md':\n{review_plan_markdown}\n\n"
            f"File 'questions-and-answers.md':\n{questions_and_answers_markdown}\n\n"
            f"File 'premortem.md':\n{premortem_markdown}"
        )

        logger.info(f"SelfAuditTask.speedvsdetail: {self.speedvsdetail}")
        max_number_of_items: Optional[int] = None
        if self.speedvsdetail == SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS:
            logger.info("FAST_BUT_SKIP_DETAILS mode, truncating to 2 items for testing a subset of the SelfAudit items.")
            max_number_of_items = 2
        else:
            logger.info("Processing all SelfAudit items.")

        # Invoke the LLM
        self_audit = SelfAudit.execute(
            llm_executor=llm_executor,
            user_prompt=user_prompt,
            max_number_of_items=max_number_of_items,
        )

        # Save the results.
        json_path = self.output()['raw'].path
        self_audit.save_raw(json_path)
        markdown_path = self.output()['markdown'].path
        self_audit.save_markdown(markdown_path)
