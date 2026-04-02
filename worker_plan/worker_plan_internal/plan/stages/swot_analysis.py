"""SWOTAnalysisTask - Performs SWOT analysis on the project plan."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.swot.swot_analysis import SWOTAnalysis
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.related_resources import RelatedResourcesTask

logger = logging.getLogger(__name__)


class SWOTAnalysisTask(PlanTask):
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'preproject': self.clone(PreProjectAssessmentTask),
            'project_plan': self.clone(ProjectPlanTask),
            'related_resources': self.clone(RelatedResourcesTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.SWOT_RAW),
            'markdown': self.local_target(FilenameEnum.SWOT_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['identify_purpose']['raw'].open("r") as f:
            identify_purpose_dict = json.load(f)
        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            consolidate_assumptions_markdown = f.read()
        with self.input()['preproject']['clean'].open("r") as f:
            pre_project_assessment_dict = json.load(f)
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['related_resources']['markdown'].open("r") as f:
            related_resources_markdown = f.read()

        # Build the query for SWOT analysis.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'pre-project-assessment.json':\n{format_json_for_use_in_query(pre_project_assessment_dict)}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'related-resources.md':\n{related_resources_markdown}"
        )

        # Execute the SWOT analysis.
        # Send the identify_purpose_dict to SWOTAnalysis, and use business/personal/other to select the system prompt
        try:
            swot_analysis = SWOTAnalysis.execute(llm=llm, query=query, identify_purpose_dict=identify_purpose_dict)
        except Exception as e:
            logger.error("SWOT analysis failed: %s", e)
            raise

        # Convert the SWOT analysis to a dict and markdown.
        swot_raw_dict = swot_analysis.to_dict()
        swot_markdown = swot_analysis.to_markdown(include_metadata=False, include_purpose=False)

        # Write the raw SWOT JSON.
        with self.output()['raw'].open("w") as f:
            json.dump(swot_raw_dict, f, indent=2)

        # Write the SWOT analysis as Markdown.
        markdown_path = self.output()['markdown'].path
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(swot_markdown)
