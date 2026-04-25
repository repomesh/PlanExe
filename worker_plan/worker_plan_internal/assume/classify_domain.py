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

Decide what KIND of project the user's prompt is, so downstream planning stages can apply the right expertise, risks, and templates. You are NOT drafting the plan.

OUTPUT:
- primary_domain: ONE short Title Case label (1-3 words).
- secondary_domains: list of additional domain labels, in priority order. **Default is an EMPTY list.** Only add a domain if it survives both tests below.
- confidence: low / medium / high.
- rationale: 1-2 sentences referencing concrete signals in the prompt.

# RULES — apply in this order

## Rule 1 — Default to fewer
Most projects are single-domain. Returning `secondary_domains: []` is a respectable answer and often correct. Hard cap: at most 3 secondaries, only when the project genuinely spans that many distinct expert lenses.

## Rule 2 — The two tests for every candidate secondary
Before you put a label in secondary_domains, both of these must be TRUE. If either fails, drop the candidate.

(a) **Different-expert test.** Would the team need to hire someone whose expertise is THIS domain, separate from the primary-domain experts? If the same primary-domain firm or staff would naturally handle that work, the candidate FAILS — drop it.
   - Yacht primary "Maritime" → DROP "Construction" (shipyards already employ welders, fitters, finishers).
   - Yacht primary "Maritime" → DROP "Real Estate" (a yacht is not real estate even if someone lives on it).
   - Tunnel primary "Construction" → DROP "Logistics" (the marine civil-works contractor lowers and joins the segments — that's their job).
   - Tunnel primary "Construction" → DROP "Engineering" (civil engineers ARE Construction).
   - Factory primary "Manufacturing" → DROP "Engineering" (industrial engineers ARE Manufacturing).
   - Software primary "Software" → DROP "Engineering" / "Computer Science" / "Mathematics" (unless the project is mathematical research distinct from coding).
   - Archiving primary "Archiving" → DROP "Engineering" (retrofitting equipment is part of operations, not a separate engineering R&D effort). Use a concrete domain like "Software" only if a separate software engineering team is needed.

(b) **Specific-gap test.** If you removed this domain, would the downstream plan miss a CONCRETE question, regulator, risk, stakeholder, or template that the primary domain wouldn't have surfaced? If you can't name the gap in one sentence, drop the candidate.

## Rule 3 — Banned-by-default labels
Do not use these unless the project's core matches them. They are commonly added for shallow reasons.
- "Engineering" — too generic. Use a specific domain (Construction / Manufacturing / Software / Aerospace) instead.
- "Finance" — only if the project's core is finance (banking, investment, insurance, fundraising) or involves non-trivial financial-instrument structuring. A budget or tax line does not qualify.
- "Construction" — only if a generic civil/buildings contractor is needed. Buildouts handled by Maritime, Aerospace, Manufacturing, etc., do NOT count.
- "Logistics" — only if logistics is a hard, planning-critical concern (cross-border, hostile geography, perishables, large-scale supply chain). Things-moving-around does NOT count.
- "Real Estate" — only if property acquisition / leasing / asset management is a real planning workstream.
- "Defense" / "Security" — only if actual military, national-security, or armed-protection expertise is required. "Needs discretion" or "has risks" does NOT count.
- "Government" / "Regulatory" — never alongside "Public Policy" (synonyms).
- "Medical" / "Clinical" — never alongside "Healthcare" (synonyms).

## Rule 4 — Vocabulary
Open-ended Title Case English labels, 1-3 words. Examples (NOT exhaustive): Research, Education, Manufacturing, Event Planning, Personal, Software, Construction, Healthcare, Agriculture, Logistics, Energy, Hospitality, Public Policy, Finance, Defense, Media Production, Transportation, Real Estate, Non-profit, Retail, Maritime, Aerospace, Robotics, Linguistics, Environmental, Archiving. Be specific enough to be useful but not so narrow that no expert fits ("Pediatric Cardiology" is too narrow; "Stuff" is too broad).

## Rule 5 — Picking the primary
The primary is the project's CENTER OF GRAVITY — the domain whose expertise will drive most of the planning. Common edge cases:
- Individual's life, hobby, health, household, relationships → "Personal".
- Academic study / scientific experiment → "Research".
- One-time gathering (concert, conference, wedding, festival) → "Event Planning".
- Producing physical goods at scale → "Manufacturing".
- Teaching / curricula / schools → "Education".
- Project that uses a building/yacht/rocket/etc — pick the operating domain (Hospitality / Maritime / Aerospace), not Construction.

## Confidence
- "high": prompt clearly fits one well-defined primary.
- "medium": concrete details, but primary is an interpretation, OR the project genuinely spans 2-3 domains without a single lead.
- "low": too vague to classify, or plausibly many different things.

Respond ONLY with valid JSON: primary_domain, secondary_domains, confidence, rationale.
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
    from worker_plan_api.planexe_dotenv import PlanExeDotEnv

    PlanExeDotEnv.load().update_os_environ()

    llm = get_llm("openrouter-gemini-2.0-flash-001")

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    # Diverse sample: mix lengths so we exercise short, medium, and long prompts.
    sorted_items = sorted(all_items, key=lambda x: len(x.prompt), reverse=True)
    sample_size = min(20, len(sorted_items))
    if sample_size < len(sorted_items):
        step = len(sorted_items) / sample_size
        sample_items = [sorted_items[int(i * step)] for i in range(sample_size)]
    else:
        sample_items = sorted_items

    print(f"=== Domain classification on {len(sample_items)} catalog prompts ===")
    for idx, item in enumerate(sample_items, start=1):
        print(f"\n[{idx}/{len(sample_items)}] Prompt ID: {item.id} (length: {len(item.prompt)} chars)")
        print(f"Preview: {item.prompt[:160].replace(chr(10), ' ')}...")
        try:
            result = ClassifyDomain.execute(llm, item.prompt)
            json_response = result.to_dict(
                include_system_prompt=False,
                include_user_prompt=False,
                include_metadata=False,
            )
            print(f"Result: {json.dumps(json_response, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
