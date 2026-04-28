"""PlanTypeTask - Determine if the plan is purely digital or requires physical locations."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.identify_plan_type import IdentifyPlanType
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.classify_domain import ClassifyDomainTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask


class PlanTypeTask(PlanTask):
    """
    Determine if the plan is purely digital or requires physical locations.
    """
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'classify_domain': self.clone(ClassifyDomainTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.PLAN_TYPE_RAW),
            'markdown': self.local_target(FilenameEnum.PLAN_TYPE_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['classify_domain']['markdown'].open("r") as f:
            classify_domain_markdown = f.read()
        with self.input()['identify_purpose']['markdown'].open("r") as f:
            identify_purpose_markdown = f.read()

        query = (
            f"File 'plan.txt':\n{plan_prompt}\n\n"
            f"File 'classify_domain.md':\n{classify_domain_markdown}\n\n"
            f"File 'purpose.md':\n{identify_purpose_markdown}"
        )

        identify_plan_type = IdentifyPlanType.execute(llm, query)

        # Write the result to disk.
        output_raw_path = self.output()['raw'].path
        identify_plan_type.save_raw(str(output_raw_path))
        output_markdown_path = self.output()['markdown'].path
        identify_plan_type.save_markdown(str(output_markdown_path))
