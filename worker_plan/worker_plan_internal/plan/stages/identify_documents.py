"""IdentifyDocumentsTask - Identifies documents that need to be created or found."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.document.identify_documents import IdentifyDocuments
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.related_resources import RelatedResourcesTask
from worker_plan_internal.plan.stages.swot_analysis import SWOTAnalysisTask
from worker_plan_internal.plan.stages.team_markdown import TeamMarkdownTask
from worker_plan_internal.plan.stages.expert_review import ExpertReviewTask


class IdentifyDocumentsTask(PlanTask):
    """
    Identify documents that need to be created or found for the project.
    """
    def output(self):
        return {
            "raw": self.local_target(FilenameEnum.IDENTIFIED_DOCUMENTS_RAW),
            "markdown": self.local_target(FilenameEnum.IDENTIFIED_DOCUMENTS_MARKDOWN),
            "documents_to_find": self.local_target(FilenameEnum.IDENTIFIED_DOCUMENTS_TO_FIND_JSON),
            "documents_to_create": self.local_target(FilenameEnum.IDENTIFIED_DOCUMENTS_TO_CREATE_JSON),
        }

    def requires(self):
        return {
            'identify_purpose': self.clone(IdentifyPurposeTask),
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
        with self.input()['identify_purpose']['raw'].open("r") as f:
            identify_purpose_dict = json.load(f)
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
        identify_documents = IdentifyDocuments.execute(
            llm=llm,
            user_prompt=query,
            identify_purpose_dict=identify_purpose_dict
        )

        # Save the results.
        identify_documents.save_raw(self.output()["raw"].path)
        identify_documents.save_markdown(self.output()["markdown"].path)
        identify_documents.save_json_documents_to_find(self.output()["documents_to_find"].path)
        identify_documents.save_json_documents_to_create(self.output()["documents_to_create"].path)
