"""PremiseAttackTask - Attacks the premises of the plan prompt."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.premise_attack import PremiseAttack
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.stages.setup import SetupTask


class PremiseAttackTask(PlanTask):
    def requires(self):
        return self.clone(SetupTask)

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PREMISE_ATTACK_RAW),
            'markdown': self.local_target(FilenameEnum.PREMISE_ATTACK_MARKDOWN)
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        # Read inputs from required tasks.
        with self.input().open("r") as f:
            plan_prompt = f.read()

        premise_attack = PremiseAttack.execute(llm_executor, plan_prompt)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        premise_attack.save_raw(output_raw_path)
        output_markdown_path = self.output()['markdown'].path
        premise_attack.save_markdown(output_markdown_path)
