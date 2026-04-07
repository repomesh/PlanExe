"""EnrichLeversTask - Enrich potential levers with more information."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.enrich_potential_levers import EnrichPotentialLevers
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.deduplicate_levers import DeduplicateLeversTask


class EnrichLeversTask(PlanTask):
    """Add description, synergy, and conflict text to each lever."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'deduplicate_levers': self.clone(DeduplicateLeversTask),
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.ENRICHED_LEVERS_RAW)
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
        with self.input()['deduplicate_levers']['raw'].open("r") as f:
            json_dict = json.load(f)
            lever_item_list = json_dict["deduplicated_levers"]

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}"
        )

        enrich_potential_levers = EnrichPotentialLevers.execute(
            llm_executor,
            project_context=query,
            raw_levers_list=lever_item_list
        )

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        enrich_potential_levers.save_raw(str(output_raw_path))
