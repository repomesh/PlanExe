"""DataCollectionTask - Determines what kind of data is to be collected."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.data_collection import DataCollection
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.related_resources import RelatedResourcesTask
from worker_plan_internal.plan.nodes.swot_analysis import SWOTAnalysisTask
from worker_plan_internal.plan.nodes.team_markdown import TeamMarkdownTask
from worker_plan_internal.plan.nodes.expert_review import ExpertReviewTask


class DataCollectionTask(PlanTask):
    """Specify data-gathering actions needed to validate the plan: market, financial, regulatory, etc."""
    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.DATA_COLLECTION_RAW),
            'markdown': self.local_target(FilenameEnum.DATA_COLLECTION_MARKDOWN)
        }

    def requires(self):
        return {
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'related_resources': self.clone(RelatedResourcesTask),
            'swot_analysis': self.clone(SWOTAnalysisTask),
            'team_markdown': self.clone(TeamMarkdownTask),
            'expert_review': self.clone(ExpertReviewTask)
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
        with self.input()['related_resources']['markdown'].open("r") as f:
            related_resources_markdown = f.read()
        with self.input()['swot_analysis']['markdown'].open("r") as f:
            swot_analysis_markdown = f.read()
        with self.input()['team_markdown'].open("r") as f:
            team_markdown = f.read()
        with self.input()['expert_review'].open("r") as f:
            expert_review = f.read()

        # Build the query.
        query = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{assumptions_markdown}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'related-resources.md':\n{related_resources_markdown}\n\n"
            f"File 'swot-analysis.md':\n{swot_analysis_markdown}\n\n"
            f"File 'team.md':\n{team_markdown}\n\n"
            f"File 'expert-review.md':\n{expert_review}"
        )

        # Invoke the LLM.
        data_collection = DataCollection.execute(llm, query)

        # Save the results.
        json_path = self.output()['raw'].path
        data_collection.save_raw(json_path)
        markdown_path = self.output()['markdown'].path
        data_collection.save_markdown(markdown_path)
