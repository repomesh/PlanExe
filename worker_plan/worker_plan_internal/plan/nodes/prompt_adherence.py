"""PromptAdherenceTask - Check how faithfully the plan follows the original prompt."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.prompt_adherence import PromptAdherence
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_api.plan_file import PlanFile
from worker_plan_internal.plan.nodes.initial_plan_raw import InitialPlanRawTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.executive_summary import ExecutiveSummaryTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask


class PromptAdherenceTask(PlanTask):
    """Score how faithfully the final plan follows the user's original prompt."""

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PROMPT_ADHERENCE_RAW),
            'markdown': self.local_target(FilenameEnum.PROMPT_ADHERENCE_MARKDOWN),
        }

    def requires(self):
        return {
            'plan_raw': self.clone(InitialPlanRawTask),
            'project_plan': self.clone(ProjectPlanTask),
            'executive_summary': self.clone(ExecutiveSummaryTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        plan_file = PlanFile.load(self.input()['plan_raw'].path)
        plan_prompt = plan_file.plan_prompt
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['executive_summary']['markdown'].open("r") as f:
            executive_summary_markdown = f.read()
        with self.input()['consolidate_assumptions_markdown']['full'].open("r") as f:
            assumptions_markdown = f.read()

        plan_context = (
            f"File 'executive_summary.md':\n{executive_summary_markdown}\n\n"
            f"File 'project_plan.md':\n{project_plan_markdown}\n\n"
            f"File 'consolidate_assumptions_full.md':\n{assumptions_markdown}"
        )

        result = PromptAdherence.execute(
            llm_executor=llm_executor,
            plan_prompt=plan_prompt,
            plan_context=plan_context,
        )

        result.save_raw(self.output()['raw'].path)
        result.save_markdown(self.output()['markdown'].path)
