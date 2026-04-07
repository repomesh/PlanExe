"""IdentifyRisksTask - Identify risks for the plan."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.identify_risks import IdentifyRisks
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask


class IdentifyRisksTask(PlanTask):
    """Build a risk register covering strategic, operational, financial, and location-specific risks."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'physical_locations': self.clone(PhysicalLocationsTask),
            'currency_strategy': self.clone(CurrencyStrategyTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.IDENTIFY_RISKS_RAW),
            'markdown': self.local_target(FilenameEnum.IDENTIFY_RISKS_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['identify_purpose']['markdown'].open("r") as f:
            identify_purpose_markdown = f.read()
        with self.input()['plan_type']['markdown'].open("r") as f:
            plan_type_markdown = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['physical_locations']['markdown'].open("r") as f:
            physical_locations_markdown = f.read()
        with self.input()['currency_strategy']['markdown'].open("r") as f:
            currency_strategy_markdown = f.read()

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
            f"File 'plan_type.md':\n{plan_type_markdown}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'physical_locations.md':\n{physical_locations_markdown}\n\n"
            f"File 'currency_strategy.md':\n{currency_strategy_markdown}"
        )

        identify_risks = IdentifyRisks.execute(llm, query)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        identify_risks.save_raw(str(output_raw_path))
        output_markdown_path = self.output()['markdown'].path
        identify_risks.save_markdown(str(output_markdown_path))
