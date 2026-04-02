"""TeamMarkdownTask - Generates the final team Markdown document."""
import json
import logging
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.team.team_markdown_document import TeamMarkdownDocumentBuilder
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.enrich_team_environment_info import EnrichTeamMembersWithEnvironmentInfoTask
from worker_plan_internal.plan.stages.review_team import ReviewTeamTask

logger = logging.getLogger(__name__)


class TeamMarkdownTask(PlanTask):
    def requires(self):
        return {
            'enrich_team_members_with_environment_info': self.clone(EnrichTeamMembersWithEnvironmentInfoTask),
            'review_team': self.clone(ReviewTeamTask)
        }

    def output(self):
        return self.local_target(FilenameEnum.TEAM_MARKDOWN)

    def run_inner(self):
        logger.info("TeamMarkdownTask. Loading files...")

        # 1. Read the team_member_list from EnrichTeamMembersWithEnvironmentInfoTask.
        with self.input()['enrich_team_members_with_environment_info']['clean'].open("r") as f:
            team_member_list = json.load(f)

        # 2. Read the json from ReviewTeamTask.
        with self.input()['review_team'].open("r") as f:
            review_team_json = json.load(f)

        logger.info("TeamMarkdownTask. All files are now ready. Processing...")

        # Combine the team members and the review into a Markdown document.
        builder = TeamMarkdownDocumentBuilder()
        builder.append_team_member_subtitle()
        builder.append_roles(team_member_list)
        builder.append_separator()
        builder.append_full_review(review_team_json)
        builder.write_to_file(self.output().path)

        logger.info("TeamMarkdownTask complete.")
