"""ConsolidateAssumptionsMarkdownTask - Combines multiple small markdown documents into one."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.shorten_markdown import ShortenMarkdown
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.stages.identify_risks import IdentifyRisksTask
from worker_plan_internal.plan.stages.make_assumptions import MakeAssumptionsTask
from worker_plan_internal.plan.stages.distill_assumptions import DistillAssumptionsTask
from worker_plan_internal.plan.stages.review_assumptions import ReviewAssumptionsTask

logger = logging.getLogger(__name__)


class ConsolidateAssumptionsMarkdownTask(PlanTask):
    """Merge locations, currency, risks, and assumption stages into one reference document."""
    def requires(self):
        return {
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'physical_locations': self.clone(PhysicalLocationsTask),
            'currency_strategy': self.clone(CurrencyStrategyTask),
            'identify_risks': self.clone(IdentifyRisksTask),
            'make_assumptions': self.clone(MakeAssumptionsTask),
            'distill_assumptions': self.clone(DistillAssumptionsTask),
            'review_assumptions': self.clone(ReviewAssumptionsTask)
        }

    def output(self):
        return {
            'full': self.local_target(FilenameEnum.CONSOLIDATE_ASSUMPTIONS_FULL_MARKDOWN),
            'short': self.local_target(FilenameEnum.CONSOLIDATE_ASSUMPTIONS_SHORT_MARKDOWN)
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

        # Define the list of (title, path) tuples
        title_path_list = [
            ('Purpose', self.input()['identify_purpose']['markdown'].path),
            ('Plan Type', self.input()['plan_type']['markdown'].path),
            ('Physical Locations', self.input()['physical_locations']['markdown'].path),
            ('Currency Strategy', self.input()['currency_strategy']['markdown'].path),
            ('Identify Risks', self.input()['identify_risks']['markdown'].path),
            ('Make Assumptions', self.input()['make_assumptions']['markdown'].path),
            ('Distill Assumptions', self.input()['distill_assumptions']['markdown'].path),
            ('Review Assumptions', self.input()['review_assumptions']['markdown'].path)
        ]

        # Read the files and handle exceptions
        full_markdown_chunks = []
        short_markdown_chunks = []
        for title, path in title_path_list:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    markdown_chunk = f.read()
                full_markdown_chunks.append(f"# {title}\n\n{markdown_chunk}")
            except FileNotFoundError:
                logger.warning(f"Markdown file not found: {path} (from {title})")
                full_markdown_chunks.append(f"**Problem with document:** '{title}'\n\nFile not found.")
                short_markdown_chunks.append(f"**Problem with document:** '{title}'\n\nFile not found.")
                continue
            except Exception as e:
                logger.error(f"Error reading markdown file {path} (from {title}): {e}")
                full_markdown_chunks.append(f"**Problem with document:** '{title}'\n\nError reading markdown file.")
                short_markdown_chunks.append(f"**Problem with document:** '{title}'\n\nError reading markdown file.")
                continue

            # IDEA: If the chunk file already exist, then there is no need to run the LLM again.
            def execute_shorten_markdown(llm: LLM) -> ShortenMarkdown:
                return ShortenMarkdown.execute(llm, markdown_chunk)

            try:
                shorten_markdown = llm_executor.run(execute_shorten_markdown)
                short_markdown_chunks.append(f"# {title}\n{shorten_markdown.markdown}")
            except PipelineStopRequested:
                # Re-raise PipelineStopRequested without wrapping it
                raise
            except Exception as e:
                logger.error(f"Error shortening markdown file {path} (from {title}): {e}")
                short_markdown_chunks.append(f"**Problem with document:** '{title}'\n\nError shortening markdown file.")
                continue

        # Combine the markdown chunks
        full_markdown = "\n\n".join(full_markdown_chunks)
        short_markdown = "\n\n".join(short_markdown_chunks)

        # Write the result to disk.
        output_full_markdown_path = self.output()['full'].path
        with open(output_full_markdown_path, "w", encoding="utf-8") as f:
            f.write(full_markdown)

        output_short_markdown_path = self.output()['short'].path
        with open(output_short_markdown_path, "w", encoding="utf-8") as f:
            f.write(short_markdown)
