"""ReviewPlanTask - Asks questions about the almost finished plan."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.review_plan import ReviewPlan
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
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
from worker_plan_internal.plan.nodes.wbs_project_level1_level2_level3 import WBSProjectLevel1AndLevel2AndLevel3Task


class ReviewPlanTask(PlanTask):
    """Critically review the near-final plan with targeted questions and SMART recommendations."""
    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.REVIEW_PLAN_RAW),
            'markdown': self.local_target(FilenameEnum.REVIEW_PLAN_MARKDOWN)
        }

    def requires(self):
        return {
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'data_collection': self.clone(DataCollectionTask),
            'related_resources': self.clone(RelatedResourcesTask),
            'swot_analysis': self.clone(SWOTAnalysisTask),
            'team_markdown': self.clone(TeamMarkdownTask),
            'pitch_markdown': self.clone(ConvertPitchToMarkdownTask),
            'expert_review': self.clone(ExpertReviewTask),
            'wbs_project123': self.clone(WBSProjectLevel1AndLevel2AndLevel3Task)
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

        # Build the query.
        query = (
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
            f"File 'work-breakdown-structure.csv':\n{wbs_project_csv}"
        )

        # Perform the review.
        review_plan = ReviewPlan.execute(llm_executor=llm_executor, document=query, speed_vs_detail=self.speedvsdetail)

        # Save the results.
        json_path = self.output()['raw'].path
        review_plan.save_raw(json_path)
        markdown_path = self.output()['markdown'].path
        review_plan.save_markdown(markdown_path)
