"""ScenariosMarkdownTask - Present the scenarios in a human readable format."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.scenarios_markdown import ScenariosMarkdown
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.candidate_scenarios import CandidateScenariosTask
from worker_plan_internal.plan.nodes.select_scenario import SelectScenarioTask


class ScenariosMarkdownTask(PlanTask):
    """Format the selected scenario and rejected alternatives into a readable document."""
    def requires(self):
        return {
            'candidate_scenarios': self.clone(CandidateScenariosTask),
            'selected_scenario': self.clone(SelectScenarioTask)
        }

    def output(self):
        return {
            'markdown': self.local_target(FilenameEnum.SCENARIOS_MARKDOWN)
        }

    def run(self):
        with self.input()['candidate_scenarios']['clean'].open("r") as f:
            scenarios_list = json.load(f).get('scenarios', [])
        with self.input()['selected_scenario']['clean'].open("r") as f:
            selected_scenario_dict = json.load(f)

        # Extract the required data from the selected scenario
        plan_characteristics = selected_scenario_dict.get('plan_characteristics', {})
        scenario_assessments = selected_scenario_dict.get('scenario_assessments', [])
        final_choice = selected_scenario_dict.get('final_choice', {})

        result = ScenariosMarkdown(scenarios_list, plan_characteristics, scenario_assessments, final_choice)
        result.save_markdown(self.output()['markdown'].path)
