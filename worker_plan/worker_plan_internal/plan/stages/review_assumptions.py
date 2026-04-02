"""ReviewAssumptionsTask - Find issues with the assumptions."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.review_assumptions import ReviewAssumptions
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.stages.identify_risks import IdentifyRisksTask
from worker_plan_internal.plan.stages.make_assumptions import MakeAssumptionsTask
from worker_plan_internal.plan.stages.distill_assumptions import DistillAssumptionsTask

logger = logging.getLogger(__name__)


class ReviewAssumptionsTask(PlanTask):
    """
    Find issues with the assumptions.
    """
    def requires(self):
        return {
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'physical_locations': self.clone(PhysicalLocationsTask),
            'currency_strategy': self.clone(CurrencyStrategyTask),
            'identify_risks': self.clone(IdentifyRisksTask),
            'make_assumptions': self.clone(MakeAssumptionsTask),
            'distill_assumptions': self.clone(DistillAssumptionsTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.REVIEW_ASSUMPTIONS_RAW),
            'markdown': self.local_target(FilenameEnum.REVIEW_ASSUMPTIONS_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Define the list of (title, path) tuples
        title_path_list = [
            ('Purpose', self.input()['identify_purpose']['markdown'].path),
            ('Plan Type', self.input()['plan_type']['markdown'].path),
            ('Strategic Decisions', self.input()['strategic_decisions_markdown']['markdown'].path),
            ('Scenarios', self.input()['scenarios_markdown']['markdown'].path),
            ('Physical Locations', self.input()['physical_locations']['markdown'].path),
            ('Currency Strategy', self.input()['currency_strategy']['markdown'].path),
            ('Identify Risks', self.input()['identify_risks']['markdown'].path),
            ('Make Assumptions', self.input()['make_assumptions']['markdown'].path),
            ('Distill Assumptions', self.input()['distill_assumptions']['markdown'].path)
        ]

        # Read the files and handle exceptions
        markdown_chunks = []
        for title, path in title_path_list:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    markdown_chunk = f.read()
                markdown_chunks.append(f"# {title}\n\n{markdown_chunk}")
            except FileNotFoundError:
                logger.warning(f"Markdown file not found: {path} (from {title})")
                markdown_chunks.append(f"**Problem with document:** '{title}'\n\nFile not found.")
            except Exception as e:
                logger.error(f"Error reading markdown file {path} (from {title}): {e}")
                markdown_chunks.append(f"**Problem with document:** '{title}'\n\nError reading markdown file.")

        # Combine the markdown chunks
        full_markdown = "\n\n".join(markdown_chunks)

        review_assumptions = ReviewAssumptions.execute(llm, full_markdown)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        review_assumptions.save_raw(str(output_raw_path))
        output_markdown_path = self.output()['markdown'].path
        review_assumptions.save_markdown(str(output_markdown_path))
