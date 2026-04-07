"""Pipeline stage: extract constraints from user prompt."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.extract_constraints import ExtractConstraints
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask


class ExtractConstraintsTask(PlanTask):
    """Extract positive/negative constraints from the user's prompt."""
    def requires(self):
        return self.clone(SetupTask)

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.EXTRACT_CONSTRAINTS_RAW),
            'markdown': self.local_target(FilenameEnum.EXTRACT_CONSTRAINTS_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        with self.input().open("r") as f:
            plan_prompt = f.read()

        result = ExtractConstraints.execute(llm, plan_prompt)

        output_raw_path = self.output()['raw'].path
        result.save_raw(output_raw_path)
        output_markdown_path = self.output()['markdown'].path
        result.save_markdown(output_markdown_path)
