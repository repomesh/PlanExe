"""Pipeline stage: classify the project's primary and secondary domains."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.classify_domain_v7 import ClassifyDomain
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.extract_constraints import ExtractConstraintsTask


def _augment_with_context(prompt: str, purpose_md: str, constraints_md: str) -> str:
    """Format the user message with optional purpose and constraint sections.

    Mirrors the augment_with_context helper in the ClassifyDomain
    smoke harness so the Luigi task feeds the classifier the same
    user-message shape the system prompts were tuned against.
    """
    sections: list[str] = [prompt]
    if purpose_md.strip():
        sections.append(
            "## Plan purpose (auto-derived; for context only)\n"
            + purpose_md.strip()
        )
    if constraints_md.strip():
        sections.append(
            "## Extracted constraints (auto-derived; for context only)\n"
            + constraints_md.strip()
        )
    if len(sections) == 1:
        return prompt
    return "\n\n---\n\n".join(sections) + "\n"


class ClassifyDomainTask(PlanTask):
    """Identify a primary domain and zero or more secondary domains for the project.

    Runs after prompt parsing, IdentifyPurpose, and
    ExtractConstraints, mirroring the ClassifyDomain smoke
    harness. Downstream stages read the result to choose domain-
    appropriate assumptions, risks, expert lenses, and templates.

    The classifier itself is a two-pass design:
      1. First pass — adaptive batch loop. Asks the model for
         candidate disciplines per batch, accumulating distinct
         candidates across multiple batches. The system prompt
         is selected based on the IdentifyPurpose tag (personal /
         business / other; falls back to business when missing).
      2. Second pass — primary selection. The model sees the
         enumerated candidate list with the IdentifyPurpose tag
         and picks one as primary, returning a rationale.

    The user message sent to the first pass concatenates the
    raw plan prompt with the IdentifyPurpose markdown and the
    ExtractConstraints markdown under labelled headings — the
    same augment_with_context shape the smoke harness uses.
    """
    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'extract_constraints': self.clone(ExtractConstraintsTask),
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.CLASSIFY_DOMAIN_RAW),
            'markdown': self.local_target(FilenameEnum.CLASSIFY_DOMAIN_MARKDOWN),
        }

    def run_with_llm(self, llm: LLM) -> None:
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['identify_purpose']['raw'].open("r") as f:
            identify_purpose_dict = json.load(f)
        with self.input()['identify_purpose']['markdown'].open("r") as f:
            purpose_markdown = f.read()
        with self.input()['extract_constraints']['markdown'].open("r") as f:
            constraints_markdown = f.read()

        purpose_value = str(identify_purpose_dict.get("purpose", "") or "").strip().lower()
        user_message = _augment_with_context(plan_prompt, purpose_markdown, constraints_markdown)

        result = ClassifyDomain.execute(llm, user_message, purpose=purpose_value)

        result.save_raw(self.output()['raw'].path)
        result.save_markdown(self.output()['markdown'].path)
