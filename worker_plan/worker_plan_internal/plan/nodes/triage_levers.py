"""TriageLeversTask - The potential levers usually have some redundant levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.triage_levers import TriageLevers
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.plan_type import PlanTypeTask
from worker_plan_internal.plan.nodes.potential_levers import PotentialLeversTask


class TriageLeversTask(PlanTask):
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
            'raw': self.local_target(FilenameEnum.TRIAGED_LEVERS_RAW)
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

        triage_levers = TriageLevers.execute(
            llm_executor,
            project_context=query,
            raw_levers_list=lever_item_list
        )

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        triage_levers.save_raw(str(output_raw_path))
