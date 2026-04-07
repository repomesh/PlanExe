"""ExecutiveSummaryTask - Creates an executive summary of the plan."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.executive_summary import ExecutiveSummary
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
from worker_plan_internal.plan.nodes.review_plan import ReviewPlanTask


class ExecutiveSummaryTask(PlanTask):
    """Produce a concise one-pager for decision-makers with key findings and recommendations."""
    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.EXECUTIVE_SUMMARY_RAW),
            'markdown': self.local_target(FilenameEnum.EXECUTIVE_SUMMARY_MARKDOWN)
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
            'wbs_project123': self.clone(WBSProjectLevel1AndLevel2AndLevel3Task),
            'review_plan': self.clone(ReviewPlanTask)
        }

    def run_with_llm(self, llm: LLM) -> None:
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
            f"File 'work-breakdown-structure.csv':\n{wbs_project_csv}\n\n"
            f"File 'review-plan.md':\n{review_plan_markdown}"
        )

        # Create the executive summary.
        executive_summary = ExecutiveSummary.execute(llm, query)

        # Save the results.
        json_path = self.output()['raw'].path
        executive_summary.save_raw(json_path)
        markdown_path = self.output()['markdown'].path
        executive_summary.save_markdown(markdown_path)
