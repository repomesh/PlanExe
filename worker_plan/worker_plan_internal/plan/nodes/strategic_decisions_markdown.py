"""StrategicDecisionsMarkdownTask - Human readable markdown with the levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.strategic_decisions_markdown import StrategicDecisionsMarkdown
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.enrich_levers import EnrichLeversTask
from worker_plan_internal.plan.nodes.focus_on_vital_few_levers import FocusOnVitalFewLeversTask


class StrategicDecisionsMarkdownTask(PlanTask):
    """Summarize the lever exploration pipeline into a readable strategic-decisions document."""
    def requires(self):
        return {
            'enriched_levers': self.clone(EnrichLeversTask),
            'levers_vital_few': self.clone(FocusOnVitalFewLeversTask)
        }

    def output(self):
        return {
            'markdown': self.local_target(FilenameEnum.STRATEGIC_DECISIONS_MARKDOWN)
        }

    def run(self):
        with self.input()['enriched_levers']['raw'].open("r") as f:
            enrich_lever_list = json.load(f)["characterized_levers"]
        with self.input()['levers_vital_few']['raw'].open("r") as f:
            vital_data = json.load(f)
            vital_lever_list = vital_data["levers"]
            lever_assessments_list = vital_data.get("response", {}).get("lever_assessments", [])
            vital_levers_summary = vital_data.get("response", {}).get("summary", "")

        result = StrategicDecisionsMarkdown(enrich_lever_list, vital_lever_list, vital_levers_summary, lever_assessments_list)
        result.save_markdown(self.output()['markdown'].path)
