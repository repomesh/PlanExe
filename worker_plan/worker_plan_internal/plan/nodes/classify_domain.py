"""Pipeline stage: classify the project's primary and secondary domains."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.classify_domain import ClassifyDomain
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask


class ClassifyDomainTask(PlanTask):
    """Identify a primary domain and zero or more secondary domains for the project.

    Runs immediately after prompt parsing and before strategic-lever
    identification. Downstream stages can read the result to choose
    domain-appropriate assumptions, risks, expert lenses, and templates.
    """
    def requires(self):
        return self.clone(SetupTask)

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.CLASSIFY_DOMAIN_RAW),
            'markdown': self.local_target(FilenameEnum.CLASSIFY_DOMAIN_MARKDOWN),
        }

    def run_with_llm(self, llm: LLM) -> None:
        with self.input().open("r") as f:
            plan_prompt = f.read()

        result = ClassifyDomain.execute(llm, plan_prompt)

        result.save_raw(self.output()['raw'].path)
        result.save_markdown(self.output()['markdown'].path)
