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
            "The single most representative domain for this project. A short, "
            "human-readable Title Case label (1-3 words) such as 'Research', "
            "'Education', 'Manufacturing', 'Event Planning', 'Personal', "
            "'Software', 'Healthcare', 'Construction', 'Agriculture', "
            "'Hospitality', 'Public Policy'. "
            "Use 'Unclear' (with confidence='low') when the prompt is too "
            "vague to identify a domain — better than guessing."
        )
    )
    secondary_domains: list[str] = Field(
        default_factory=list,
        description=(
            "Up to 3 additional domain labels in priority order. Empty list "
            "is the right answer for most single-domain projects. Must not "
            "include the primary_domain. Always empty when primary_domain "
            "is 'Unclear'."
        )
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "'high' when the prompt clearly belongs to one domain. "
            "'medium' when there are concrete details but the domain is an "
            "interpretation. "
            "'low' when the prompt is too vague or spans many domains "
            "without a clear lead — pair with primary_domain='Unclear'."
        )
    )
    rationale: str = Field(
        description=(
            "1-2 sentences explaining the choice. When primary_domain is "
            "'Unclear', state what specific information is missing."
        )
    )


CLASSIFY_DOMAIN_SYSTEM_PROMPT = """
You classify a project prompt for a planning pipeline.

Return JSON with:
- primary_domain: one short domain label, Title Case, 1-3 words.
- secondary_domains: up to 3 additional domain labels.
- confidence: low, medium, or high.
- rationale: 1-2 sentences.

Pick the primary domain by the project deliverable, not by incidental means.
Ask: when the project succeeds, what exists or happens?

Examples:
- app/library/script/system -> Software
- school/curriculum/learner outcomes -> Education
- scientific study/paper/experiment -> Research
- wedding/conference/festival/state funeral -> Event Planning
- bridge/tunnel/dam/building handed over to operate -> Construction
- shop/hotel/casino/cafe as an operating business -> Hospitality or Retail
- personal household/life/hobby issue -> Personal
- policy/regulation/government reorganization -> Public Policy

Secondary domains should be rare. Include one only if:
1. A distinct expert/team would be needed, and
2. Removing that lens would miss a concrete planning risk, stakeholder, regulator, or template.

Avoid generic labels like Engineering, Technology, Business, Operations, Management unless they are truly the core domain.

If the prompt is too vague, use primary_domain = "Unclear", confidence = "low", and explain what is missing.
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

        # Defensive cleanup: drop the primary from secondary if the model put it there,
        # and force empty secondaries when primary is "Unclear".
        primary = pydantic_instance.primary_domain.strip()
        if primary.lower() == "unclear":
            deduped_secondary: list[str] = []
        else:
            cleaned_secondary = [
                d.strip() for d in pydantic_instance.secondary_domains
                if d.strip() and d.strip().lower() != primary.lower()
            ]
            # Deduplicate while preserving order.
            seen: set[str] = set()
            deduped_secondary = []
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
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from dataclasses import dataclass
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_internal.utils.planexe_llmconfig import PlanExeLLMConfig
    from worker_plan_api.prompt_catalog import PromptCatalog
    from worker_plan_api.planexe_dotenv import PlanExeDotEnv

    PlanExeDotEnv.load().update_os_environ()

    LLM_NAME = "openrouter-llama-3.1-8b-instruct-nitro"

    # Read luigi_workers from the profile config so we run the same level of
    # parallelism the pipeline would use.
    try:
        cfg_dict = PlanExeLLMConfig.load().llm_config_dict.get(LLM_NAME, {})
        max_workers = max(1, int(cfg_dict.get("luigi_workers", 1)))
    except Exception:
        max_workers = 1

    # One LLM per worker thread. llama_index LLM clients are not guaranteed
    # to be thread-safe, so each worker lazily builds its own instance on
    # first use and reuses it across the prompts it handles.
    _thread_local = threading.local()

    def get_thread_llm():
        llm = getattr(_thread_local, "llm", None)
        if llm is None:
            llm = get_llm(LLM_NAME)
            _thread_local.llm = llm
        return llm

    @dataclass
    class TestPrompt:
        id: str
        prompt: str

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    sorted_items = sorted(all_items, key=lambda x: len(x.prompt), reverse=True)
    sample_size = min(20, len(sorted_items))
    if sample_size < len(sorted_items):
        step = len(sorted_items) / sample_size
        catalog_sample = [sorted_items[int(i * step)] for i in range(sample_size)]
    else:
        catalog_sample = sorted_items

    # Synthetic vague prompts to verify "Unclear" handling.
    vague_prompts = [
        TestPrompt("vague-help", "Help me make a plan for my project."),
        TestPrompt("vague-thing", "I want to do a thing."),
        TestPrompt("vague-improve", "Improve things."),
    ]

    sample_items = list(catalog_sample) + vague_prompts

    print(
        f"=== Domain classification on {len(sample_items)} prompts "
        f"({len(catalog_sample)} catalog + {len(vague_prompts)} vague) "
        f"using {LLM_NAME} (max_workers={max_workers}) ==="
    )

    def classify_one(idx: int, item) -> tuple[int, str, str, dict | None, Exception | None]:
        try:
            result = ClassifyDomain.execute(get_thread_llm(), item.prompt)
            return idx, item.id, item.prompt, result.to_dict(
                include_system_prompt=False,
                include_user_prompt=False,
                include_metadata=False,
            ), None
        except Exception as exc:
            return idx, item.id, item.prompt, None, exc

    results: dict[int, tuple[str, str, dict | None, Exception | None]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(classify_one, idx, item)
            for idx, item in enumerate(sample_items, start=1)
        ]
        for future in as_completed(futures):
            idx, prompt_id, prompt_text, json_response, exc = future.result()
            results[idx] = (prompt_id, prompt_text, json_response, exc)
            if exc is None:
                print(f"  ✓ [{idx}/{len(sample_items)}] {prompt_id}", flush=True)
            else:
                print(f"  ✗ [{idx}/{len(sample_items)}] {prompt_id}: {exc}", flush=True)

    print()
    for idx in sorted(results):
        prompt_id, prompt_text, json_response, exc = results[idx]
        print(f"\n[{idx}/{len(sample_items)}] Prompt ID: {prompt_id} (length: {len(prompt_text)} chars)")
        print(f"Preview: {prompt_text[:160].replace(chr(10), ' ')}...")
        if exc is not None:
            print(f"Error: {exc}")
        else:
            print(f"Result: {json.dumps(json_response, indent=2)}")
