"""EnrichTeamMembersWithBackgroundStoryTask - Enriches team members with background stories."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.team.enrich_team_members_with_background_story import EnrichTeamMembersWithBackgroundStory
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.enrich_team_contract_type import EnrichTeamMembersWithContractTypeTask
from worker_plan_internal.plan.stages.related_resources import RelatedResourcesTask

logger = logging.getLogger(__name__)


class EnrichTeamMembersWithBackgroundStoryTask(PlanTask):
    """Develop background story for each team member."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'preproject': self.clone(PreProjectAssessmentTask),
            'project_plan': self.clone(ProjectPlanTask),
            'enrich_team_members_with_contract_type': self.clone(EnrichTeamMembersWithContractTypeTask),
            'related_resources': self.clone(RelatedResourcesTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.ENRICH_TEAM_MEMBERS_BACKGROUND_STORY_RAW),
            'clean': self.local_target(FilenameEnum.ENRICH_TEAM_MEMBERS_BACKGROUND_STORY_CLEAN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # In FAST_BUT_SKIP_DETAILS mode, skip fictional biography generation entirely.
        # Pass the bare team member list (title, domain, relevance) through unchanged.
        if self.speedvsdetail == SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS:
            logger.info("FAST_BUT_SKIP_DETAILS mode: skipping biography enrichment.")
            with self.input()['enrich_team_members_with_contract_type']['clean'].open("r") as f:
                team_member_list = json.load(f)
            with self.output()['raw'].open("w") as f:
                json.dump({"team_members": team_member_list}, f, indent=2)
            with self.output()['clean'].open("w") as f:
                json.dump(team_member_list, f, indent=2)
            return

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
        with self.input()['enrich_team_members_with_contract_type']['clean'].open("r") as f:
            team_member_list = json.load(f)
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
            f"File 'team-members-that-needs-to-be-enriched.json':\n{format_json_for_use_in_query(team_member_list)}\n\n"
            f"File 'related-resources.md':\n{related_resources_markdown}"
        )

        # Execute.
        try:
            enrich_team_members_with_background_story = EnrichTeamMembersWithBackgroundStory.execute(llm, query, team_member_list)
        except Exception as e:
            logger.error("EnrichTeamMembersWithBackgroundStory failed: %s", e)
            raise

        # Save the raw output.
        raw_dict = enrich_team_members_with_background_story.to_dict()
        with self.output()['raw'].open("w") as f:
            json.dump(raw_dict, f, indent=2)

        # Save the cleaned up result.
        team_member_list = enrich_team_members_with_background_story.team_member_list
        with self.output()['clean'].open("w") as f:
            json.dump(team_member_list, f, indent=2)
