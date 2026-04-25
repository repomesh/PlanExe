"""
Classify the project domain.

Given a user prompt, identify a single primary domain and zero or more
secondary domains. Domains are open-ended human-readable labels (e.g.
"Research", "Education", "Manufacturing", "Event Planning", "Personal");
the LLM picks them — there is no hardcoded vocabulary.

Downstream pipeline stages can use the domain to select the right
assumptions, questions, risks, compliance checks, expert lenses, and
planning templates.

The goal here is not to draft the plan. The goal is to answer:
    "What kind of project is this, and what kinds of expertise,
     constraints, and planning logic does it require?"

PROMPT> python -m worker_plan_internal.assume.classify_domain
"""
import time
from math import ceil
import logging
import json
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)


class DomainClassificationResult(BaseModel):
    """
    Structured output for project domain classification.
    """
    primary_domain: str = Field(
        description=(
            "The single most representative domain for this project. "
            "A short, human-readable label such as 'Research', 'Education', "
            "'Manufacturing', 'Event Planning', 'Personal', 'Software', "
            "'Healthcare', 'Construction', 'Agriculture', 'Logistics'. "
            "Pick the one domain whose expertise, constraints, and planning "
            "templates the rest of the pipeline should default to."
        )
    )
    secondary_domains: list[str] = Field(
        default_factory=list,
        description=(
            "Zero or more additional domains that are clearly relevant but "
            "secondary to the primary. Use the same human-readable label "
            "style as primary_domain. Return an empty list if the project "
            "is purely single-domain. Do not include the primary domain here. "
            "Do not pad with weakly-relevant domains — only include a "
            "domain if downstream planning would actually benefit from "
            "applying that domain's lens."
        )
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "How confident are you in the primary_domain choice? "
            "'high' when the prompt clearly belongs to one domain. "
            "'medium' when there are concrete details but the domain is "
            "an interpretation. "
            "'low' when the prompt is too vague or spans many domains "
            "without a clear lead."
        )
    )
    rationale: str = Field(
        description=(
            "A 1-2 sentence explanation of why this primary_domain was "
            "chosen and why each secondary_domain is relevant."
        )
    )


CLASSIFY_DOMAIN_SYSTEM_PROMPT = """
You are a domain classifier for a project planning system called PlanExe.

Your job is to read a user's project prompt and decide what KIND of project it is, so that downstream planning stages can apply the right expertise, assumptions, risk lenses, compliance checks, expert reviewers, and planning templates.

You are NOT drafting the plan. You are answering only:
    "What kind of project is this, and what kinds of expertise, constraints, and planning logic does it require?"

Output two things:
1. ONE primary_domain — the single most representative domain.
2. A list of secondary_domains — zero or more additional domains that downstream planning would clearly benefit from.

DOMAIN VOCABULARY:
- Domains are short, human-readable English labels. There is NO fixed list — pick whatever label best describes the project.
- Examples (illustrative, not exhaustive): "Research", "Education", "Manufacturing", "Event Planning", "Personal", "Software", "Construction", "Healthcare", "Agriculture", "Logistics", "Energy", "Hospitality", "Public Policy", "Finance", "Defense", "Media Production", "Transportation", "Real Estate", "Non-profit", "Retail".
- Use Title Case ("Event Planning", not "event planning" or "event-planning").
- Keep labels concise — 1 to 3 words. No sentences, no parentheses.
- Be specific enough to be useful, but not so narrow that no expert lens fits. "Healthcare" is good. "Pediatric Cardiology" is too narrow. "Stuff" is too broad.

PRIMARY VS SECONDARY:
- primary_domain is what the project IS — its center of gravity. If the project is "Open a coffee shop in Copenhagen", the primary is "Hospitality" or "Retail" (whichever frame fits better), not "Construction" — even if the project involves a buildout.
- secondary_domains are domains that are clearly relevant but supportive. For the coffee shop, "Construction" might be a secondary (because of the fit-out), and "Marketing" might be another.
- Do NOT pad secondary_domains. Empty list is the right answer for a single-domain project. Only include a secondary if a real planning stage would benefit from applying that lens.
- Do NOT repeat the primary_domain in secondary_domains.

CONFIDENCE:
- "high": the prompt clearly belongs to one well-defined domain.
- "medium": the prompt has concrete details but the domain is an interpretation, OR the project genuinely spans 2-3 domains without a single dominant one.
- "low": the prompt is too vague to classify reliably, or could plausibly be many different things.

RATIONALE:
- 1-2 sentences. Explain why the primary was chosen and (briefly) why each secondary is relevant. Reference the specific signals in the prompt.

EDGE CASES:
- Prompts about an individual's life, hobby, health, household, or relationships → primary "Personal" (with secondaries like "Health" or "Education" if relevant).
- Prompts about an academic study, scientific experiment, or knowledge-generation goal → primary "Research".
- Prompts about a one-time gathering (concert, conference, wedding, festival) → primary "Event Planning".
- Prompts about producing physical goods at scale → primary "Manufacturing".
- Prompts about teaching, curricula, schools, or learner outcomes → primary "Education".
- Mixed projects (e.g. a research lab that also runs an annual conference) — use the primary that drives most of the planning effort and expertise; put the others in secondary_domains.

Respond ONLY with a valid JSON object containing:
- "primary_domain": a single short Title Case label.
- "secondary_domains": a list of zero or more short Title Case labels (must not include the primary).
- "confidence": "low", "medium", or "high".
- "rationale": a 1-2 sentence explanation.
"""


@dataclass
class ClassifyDomain:
    """
    Classify a user prompt into a primary domain and zero or more secondary domains.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str

    @classmethod
    def execute(cls, llm: LLM, user_prompt: str) -> "ClassifyDomain":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")

        logger.debug(f"User Prompt:\n{user_prompt}")

        system_prompt = CLASSIFY_DOMAIN_SYSTEM_PROMPT.strip()

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(DomainClassificationResult)
        start_time = time.perf_counter()
        try:
            chat_response = sllm.chat(chat_message_list)
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.debug(f"LLM chat interaction failed [{llm_error.error_id}]: {e}")
            logger.error(f"LLM chat interaction failed [{llm_error.error_id}]", exc_info=True)
            raise llm_error from e

        end_time = time.perf_counter()
        duration = int(ceil(end_time - start_time))
        raw_content = chat_response.message.content or ""
        response_byte_count = len(raw_content.encode('utf-8'))
        logger.info(
            f"LLM chat interaction completed in {duration} seconds. "
            f"Response byte count: {response_byte_count}"
        )

        pydantic_instance: DomainClassificationResult = chat_response.raw
        if pydantic_instance is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")

        # Defensive cleanup: drop the primary from secondary if the model put it there.
        primary = pydantic_instance.primary_domain.strip()
        cleaned_secondary = [
            d.strip() for d in pydantic_instance.secondary_domains
            if d.strip() and d.strip().lower() != primary.lower()
        ]
        # Deduplicate while preserving order.
        seen: set[str] = set()
        deduped_secondary: list[str] = []
        for d in cleaned_secondary:
            key = d.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped_secondary.append(d)
        pydantic_instance = DomainClassificationResult(
            primary_domain=primary,
            secondary_domains=deduped_secondary,
            confidence=pydantic_instance.confidence,
            rationale=pydantic_instance.rationale,
        )

        json_response = pydantic_instance.model_dump()

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration"] = duration
        metadata["response_byte_count"] = response_byte_count

        markdown = cls.convert_to_markdown(pydantic_instance)

        return cls(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
            markdown=markdown,
        )

    def to_dict(
        self,
        include_metadata: bool = True,
        include_system_prompt: bool = True,
        include_user_prompt: bool = True,
    ) -> dict:
        d = self.response.copy()
        if include_metadata:
            d["metadata"] = self.metadata
        if include_system_prompt:
            d["system_prompt"] = self.system_prompt
        if include_user_prompt:
            d["user_prompt"] = self.user_prompt
        return d

    def save_raw(self, file_path: str) -> None:
        with open(file_path, 'w') as f:
            f.write(json.dumps(self.to_dict(), indent=2))

    @staticmethod
    def convert_to_markdown(result: DomainClassificationResult) -> str:
        if not isinstance(result, DomainClassificationResult):
            raise ValueError("Response must be a DomainClassificationResult object.")

        if result.secondary_domains:
            secondary_display = ", ".join(result.secondary_domains)
        else:
            secondary_display = "_(none)_"

        lines = [
            f"**Primary domain:** {result.primary_domain}",
            "",
            f"**Secondary domains:** {secondary_display}",
            "",
            f"**Confidence:** {result.confidence.title()}",
            "",
            f"**Rationale:** {result.rationale}",
        ]
        return "\n".join(lines)

    def save_markdown(self, file_path: str) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.markdown)


if __name__ == "__main__":
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_api.prompt_catalog import PromptCatalog

    llm = get_llm("ollama-llama3.1")

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    sorted_items = sorted(all_items, key=lambda x: len(x.prompt), reverse=True)

    print("=== Domain classification on the longest catalog prompts ===")
    for item in sorted_items[:5]:
        print(f"\nPrompt ID: {item.id} (length: {len(item.prompt)} chars)")
        print(f"Preview: {item.prompt[:120]}...")
        try:
            result = ClassifyDomain.execute(llm, item.prompt)
            json_response = result.to_dict(
                include_system_prompt=False,
                include_user_prompt=False,
                include_metadata=False,
            )
            print(f"Response: {json.dumps(json_response, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
