"""RelatedResourcesTask - Finds related resources for the project."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.related_resources import RelatedResources
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask

logger = logging.getLogger(__name__)


class RelatedResourcesTask(PlanTask):
    """Identify external resources needed: software, APIs, datasets, services, etc."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.RELATED_RESOURCES_RAW),
            'markdown': self.local_target(FilenameEnum.RELATED_RESOURCES_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            consolidate_assumptions_markdown = f.read()
        with self.input()['project_plan']['raw'].open("r") as f:
            project_plan_dict = json.load(f)

        # Build the query.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'project-plan.json':\n{format_json_for_use_in_query(project_plan_dict)}"
        )

        # Execute.
        try:
            related_resources = RelatedResources.execute(llm, query)
        except Exception as e:
            logger.error("SimilarProjects failed: %s", e)
            raise

        # Save the results.
        related_resources.save_raw(self.output()['raw'].path)
        related_resources.save_markdown(self.output()['markdown'].path)
