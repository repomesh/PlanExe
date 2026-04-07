"""IdentifyPurposeTask - Determine if this is a business/personal/other plan."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.identify_purpose import IdentifyPurpose
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask


class IdentifyPurposeTask(PlanTask):
    """Classify the plan as business, personal, or other to tailor downstream prompts."""
    def requires(self):
        return self.clone(SetupTask)

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.IDENTIFY_PURPOSE_RAW),
            'markdown': self.local_target(FilenameEnum.IDENTIFY_PURPOSE_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input().open("r") as f:
            plan_prompt = f.read()

        identify_purpose = IdentifyPurpose.execute(llm, plan_prompt)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        identify_purpose.save_raw(output_raw_path)
        output_markdown_path = self.output()['markdown'].path
        identify_purpose.save_markdown(output_markdown_path)
