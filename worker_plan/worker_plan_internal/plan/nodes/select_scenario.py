"""SelectScenarioTask - Pick the best fitting scenario to make a plan for."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.select_scenario import SelectScenario
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.plan_type import PlanTypeTask
from worker_plan_internal.plan.nodes.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
from worker_plan_internal.plan.nodes.candidate_scenarios import CandidateScenariosTask


class SelectScenarioTask(PlanTask):
    """Evaluate trade-offs and select the best scenario with a rationale."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'levers_vital_few': self.clone(FocusOnVitalFewLeversTask),
            'candidate_scenarios': self.clone(CandidateScenariosTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.SELECTED_SCENARIO_RAW),
            'clean': self.local_target(FilenameEnum.SELECTED_SCENARIO_CLEAN)
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
        with self.input()['candidate_scenarios']['clean'].open("r") as f:
            scenarios_list = json.load(f).get('scenarios', [])

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}\n\n"
            f"File 'levers_vital_few.json':\n{format_json_for_use_in_query(lever_item_list)}\n\n"
            f"File 'candidate_scenarios.json':\n{format_json_for_use_in_query(scenarios_list)}"
        )

        select_scenario = SelectScenario.execute(
            llm_executor=llm_executor,
            project_context=query,
            scenarios=scenarios_list
        )

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        select_scenario.save_raw(str(output_raw_path))
        output_clean_path = self.output()['clean'].path
        select_scenario.save_clean(str(output_clean_path))
