"""PotentialLeversTask - Identify potential levers that can be adjusted."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.identify_potential_levers import IdentifyPotentialLevers
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask


class PotentialLeversTask(PlanTask):
    """
    Identify potential levers that can be adjusted.
    """
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.POTENTIAL_LEVERS_RAW),
            'clean': self.local_target(FilenameEnum.POTENTIAL_LEVERS_CLEAN),
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['identify_purpose']['markdown'].open("r") as f:
            identify_purpose_markdown = f.read()
        with self.input()['plan_type']['markdown'].open("r") as f:
            plan_type_markdown = f.read()

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}"
        )

        identify_potential_levers = IdentifyPotentialLevers.execute(llm_executor, query)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        identify_potential_levers.save_raw(str(output_raw_path))
        output_clean_path = self.output()['clean'].path
        identify_potential_levers.save_clean(str(output_clean_path))
