"""PhysicalLocationsTask - Identify/suggest physical locations for the plan."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.physical_locations import PhysicalLocations
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.plan_type import PlanTypeTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask

logger = logging.getLogger(__name__)


class PhysicalLocationsTask(PlanTask):
    """Determine where the project operates — extract or suggest physical locations."""
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PHYSICAL_LOCATIONS_RAW),
            'markdown': self.local_target(FilenameEnum.PHYSICAL_LOCATIONS_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        logger.info("Identify/suggest physical locations for the plan...")

        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['identify_purpose']['markdown'].open("r") as f:
            identify_purpose_markdown = f.read()
        with self.input()['plan_type']['raw'].open("r") as f:
            plan_type_dict = json.load(f)
        with self.input()['plan_type']['markdown'].open("r") as f:
            plan_type_markdown = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()

        output_raw_path = self.output()['raw'].path
        output_markdown_path = self.output()['markdown'].path

        plan_type = plan_type_dict.get("plan_type")
        if plan_type == "physical":
            query = (
                f"File 'plan.txt':\n{plan_prompt}\n\n"
                f"File 'purpose.md':\n{identify_purpose_markdown}\n\n"
                f"File 'plan_type.md':\n{plan_type_markdown}\n\n"
                f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
                f"File 'scenarios.md':\n{scenarios_markdown}"
            )

            physical_locations = PhysicalLocations.execute(llm, query)

            # Write the physical locations to disk.
            physical_locations.save_raw(str(output_raw_path))
            physical_locations.save_markdown(str(output_markdown_path))
        else:
            # Write an empty file to indicate that there are no physical locations.
            data = {
                "comment": "The plan is purely digital, without any physical locations."
            }
            with open(output_raw_path, "w") as f:
                json.dump(data, f, indent=2)

            with open(output_markdown_path, "w", encoding='utf-8') as f:
                f.write("The plan is purely digital, without any physical locations.")
