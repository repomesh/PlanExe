"""FocusOnVitalFewLeversTask - Apply the 80/20 principle to the levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.focus_on_vital_few_levers import FocusOnVitalFewLevers
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.enrich_levers import EnrichLeversTask


class FocusOnVitalFewLeversTask(PlanTask):
    """
    Apply the 80/20 principle to the levers.
    """
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'enriched_levers': self.clone(EnrichLeversTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.VITAL_FEW_LEVERS_RAW)
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
        with self.input()['enriched_levers']['raw'].open("r") as f:
            lever_item_list = json.load(f)["characterized_levers"]

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}\n\n"
        )

        focus_on_vital_few_levers = FocusOnVitalFewLevers.execute(
            llm_executor,
            project_context=query,
            raw_levers_list=lever_item_list
        )

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        focus_on_vital_few_levers.save_raw(str(output_raw_path))
