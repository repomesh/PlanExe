"""CandidateScenariosTask - Combinations of the vital few levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.candidate_scenarios import CandidateScenarios
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.focus_on_vital_few_levers import FocusOnVitalFewLeversTask


class CandidateScenariosTask(PlanTask):
    """
    Combinations of the vital few levers.
    """
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'levers_vital_few': self.clone(FocusOnVitalFewLeversTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.CANDIDATE_SCENARIOS_RAW),
            'clean': self.local_target(FilenameEnum.CANDIDATE_SCENARIOS_CLEAN)
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
        with self.input()['levers_vital_few']['raw'].open("r") as f:
            lever_item_list = json.load(f)["levers"]

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}\n\n"
        )

        scenarios = CandidateScenarios.execute(
            llm_executor=llm_executor,
            project_context=query,
            raw_vital_levers=lever_item_list
        )

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        scenarios.save_raw(str(output_raw_path))
        output_clean_path = self.output()['clean'].path
        scenarios.save_clean(str(output_clean_path))
