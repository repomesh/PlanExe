"""ReviewTeamTask - Reviews the assembled team."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.team.review_team import ReviewTeam
from worker_plan_internal.team.team_markdown_document import TeamMarkdownDocumentBuilder
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.enrich_team_environment_info import EnrichTeamMembersWithEnvironmentInfoTask
from worker_plan_internal.plan.nodes.related_resources import RelatedResourcesTask

logger = logging.getLogger(__name__)


class ReviewTeamTask(PlanTask):
    """Review and validate the assembled team composition."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'preproject': self.clone(PreProjectAssessmentTask),
            'project_plan': self.clone(ProjectPlanTask),
            'enrich_team_members_with_environment_info': self.clone(EnrichTeamMembersWithEnvironmentInfoTask),
            'related_resources': self.clone(RelatedResourcesTask)
        }

    def output(self):
        return self.local_target(FilenameEnum.REVIEW_TEAM_RAW)

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
        with self.input()['enrich_team_members_with_environment_info']['clean'].open("r") as f:
            team_member_list = json.load(f)
        with self.input()['related_resources']['markdown'].open("r") as f:
            related_resources_markdown = f.read()

        # Convert the team members to a Markdown document.
        builder = TeamMarkdownDocumentBuilder()
        builder.append_roles(team_member_list, title=None)
        team_document_markdown = builder.to_string()

        # Build the query.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'pre-project-assessment.json':\n{format_json_for_use_in_query(pre_project_assessment_dict)}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'team-members.md':\n{team_document_markdown}\n\n"
            f"File 'related-resources.md':\n{related_resources_markdown}"
        )

        # Execute.
        try:
            review_team = ReviewTeam.execute(llm, query)
        except Exception as e:
            logger.error("ReviewTeam failed: %s", e)
            raise

        # Save the raw output.
        raw_dict = review_team.to_dict()
        with self.output().open("w") as f:
            json.dump(raw_dict, f, indent=2)

        logger.info("ReviewTeamTask complete.")
