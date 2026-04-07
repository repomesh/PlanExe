"""DistillAssumptionsTask - Distill raw assumption data."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.distill_assumptions import DistillAssumptions
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.make_assumptions import MakeAssumptionsTask


class DistillAssumptionsTask(PlanTask):
    """Condense verbose assumptions into concise, strategically important ones."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'make_assumptions': self.clone(MakeAssumptionsTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.DISTILL_ASSUMPTIONS_RAW),
            'markdown': self.local_target(FilenameEnum.DISTILL_ASSUMPTIONS_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['identify_purpose']['markdown'].open("r") as f:
            identify_purpose_markdown = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        make_assumptions_target = self.input()['make_assumptions']['clean']
        with make_assumptions_target.open("r") as f:
            assumptions_raw_data = json.load(f)

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.json':\n{format_json_for_use_in_query(assumptions_raw_data)}"
        )

        distill_assumptions = DistillAssumptions.execute(llm, query)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        distill_assumptions.save_raw(str(output_raw_path))
        output_markdown_path = self.output()['markdown'].path
        distill_assumptions.save_markdown(str(output_markdown_path))
