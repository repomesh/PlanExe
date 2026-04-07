"""ConvertPitchToMarkdownTask - Human readable version of the pitch."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.pitch.convert_pitch_to_markdown import ConvertPitchToMarkdown
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.create_pitch import CreatePitchTask


class ConvertPitchToMarkdownTask(PlanTask):
    """Convert the raw pitch JSON into a polished, scannable markdown document."""
    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PITCH_CONVERT_TO_MARKDOWN_RAW),
            'markdown': self.local_target(FilenameEnum.PITCH_MARKDOWN)
        }

    def requires(self):
        return {
            'pitch': self.clone(CreatePitchTask),
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read the project plan JSON.
        with self.input()['pitch'].open("r") as f:
            pitch_json = json.load(f)

        # Build the query
        query = format_json_for_use_in_query(pitch_json)

        # Execute the conversion.
        converted = ConvertPitchToMarkdown.execute(llm, query)

        # Save the results.
        json_path = self.output()['raw'].path
        converted.save_raw(json_path)
        markdown_path = self.output()['markdown'].path
        converted.save_markdown(markdown_path)
