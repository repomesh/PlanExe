"""FindTeamMembersTask - Identifies team members needed for the project."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.team.find_team_members import FindTeamMembers
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.related_resources import RelatedResourcesTask

logger = logging.getLogger(__name__)


class FindTeamMembersTask(PlanTask):
    """Identify team members required for project execution."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'preproject': self.clone(PreProjectAssessmentTask),
            'project_plan': self.clone(ProjectPlanTask),
            'related_resources': self.clone(RelatedResourcesTask),
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.FIND_TEAM_MEMBERS_RAW),
            'clean': self.local_target(FilenameEnum.FIND_TEAM_MEMBERS_CLEAN)
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
        with self.input()['preproject']['clean'].open("r") as f:
            pre_project_assessment_dict = json.load(f)
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['related_resources']['markdown'].open("r") as f:
            related_resources_markdown = f.read()

        # Build the query.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'pre-project-assessment.json':\n{format_json_for_use_in_query(pre_project_assessment_dict)}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'related-resources.md':\n{related_resources_markdown}"
        )

        # Execute.
        try:
            find_team_members = FindTeamMembers.execute(llm, query)
        except Exception as e:
            logger.error("FindTeamMembers failed: %s", e)
            raise

        # Save the raw output.
        raw_dict = find_team_members.to_dict()
        with self.output()['raw'].open("w") as f:
            json.dump(raw_dict, f, indent=2)

        # Save the cleaned up result.
        team_member_list = find_team_members.team_member_list
        with self.output()['clean'].open("w") as f:
            json.dump(team_member_list, f, indent=2)
