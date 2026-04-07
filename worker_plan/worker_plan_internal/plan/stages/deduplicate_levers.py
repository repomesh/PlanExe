"""DeduplicateLeversTask - The potential levers usually have some redundant levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.deduplicate_levers import DeduplicateLevers
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.potential_levers import PotentialLeversTask


class DeduplicateLeversTask(PlanTask):
    """Triage levers into primary, secondary, or remove."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'potential_levers': self.clone(PotentialLeversTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.DEDUPLICATED_LEVERS_RAW)
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
        with self.input()['potential_levers']['clean'].open("r") as f:
            lever_item_list = json.load(f)

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}"
        )

        deduplicate_levers = DeduplicateLevers.execute(
            llm_executor,
            project_context=query,
            raw_levers_list=lever_item_list
        )

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        deduplicate_levers.save_raw(str(output_raw_path))
