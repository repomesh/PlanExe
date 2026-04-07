"""RedlineGateTask - Checks the plan prompt against redline criteria."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.redline_gate import RedlineGate
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask


class RedlineGateTask(PlanTask):
    """Block prompts that cross policy, legal, or ethical red lines."""

    def requires(self):
        return self.clone(SetupTask)

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.REDLINE_GATE_RAW),
            'markdown': self.local_target(FilenameEnum.REDLINE_GATE_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input().open("r") as f:
            plan_prompt = f.read()

        redline_gate = RedlineGate.execute(llm, plan_prompt)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        redline_gate.save_raw(output_raw_path)
        output_markdown_path = self.output()['markdown'].path
        redline_gate.save_markdown(output_markdown_path)
