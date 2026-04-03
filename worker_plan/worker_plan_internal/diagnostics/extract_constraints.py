"""
Extract constraints from user prompt.

LLM-based extraction of explicit constraints from user prompts before plan
generation. Classifies each constraint as positive (things the user wants)
or negative (things the user wants to avoid). Output is a flat list of
self-contained, bullet-point-ready constraint items.

PROMPT> python -m worker_plan_internal.diagnostics.extract_constraints
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


class ConstraintItem(BaseModel):
    """A single constraint extracted from the user's prompt."""
    classification: Literal["positive", "negative"] = Field(
        description=(
            "'positive' for things the user wants (goals, features, locations, budgets, timelines, technologies to use). "
            "'negative' for things the user wants to avoid (banned words, technologies to exclude, non-goals, hard limits)."
        )
    )
    constraint_text: str = Field(
        description=(
            "A short, self-contained bullet-point item describing the constraint. "
            "Must be understandable without the original prompt. "
            "For negative constraints, phrase as 'Do not use X' or 'Avoid X'."
        )
    )


class ConstraintExtractionResult(BaseModel):
    """Structured output for constraint extraction."""
    constraints: list[ConstraintItem] = Field(
        description="List of all explicit constraints found in the user's prompt. Empty list if none found."
    )


EXTRACT_CONSTRAINTS_SYSTEM_PROMPT = """
You are an expert at analyzing project descriptions to extract explicit constraints. Your job is to identify every constraint the user has stated in their prompt and classify it as positive or negative.

POSITIVE constraints are things the user WANTS in their project:
- Goals and objectives (e.g., "solar farm", "escape room")
- Locations (e.g., "Denmark", "Shanghai", "Silicon Valley")
- Target audiences (e.g., "kids aged 8-14")
- Budgets (e.g., "Budget: $200K", "$40 million USD")
- Timelines (e.g., "6 months", "24 months")
- Technologies or approaches to use (e.g., "open protocol")
- Specific requirements (e.g., "4 rooms", "60-90 min sessions")

NEGATIVE constraints are things the user wants to AVOID:
- Banned words or technologies (e.g., "Banned words: AR/VR/NFT/blockchain")
- Explicit prohibitions (e.g., "Don't use blockchain", "Don't use DAO")
- Non-goals (e.g., "MVP non-goals: multi-bloc federation, physical data centers")
- Hard limits not to violate (e.g., "No generic ROI fluff")
- Things to exclude (e.g., "avoid aggressive scenarios")

EXTRACTION RULES:
- Only extract constraints that are EXPLICITLY stated in the prompt. Do not infer or guess.
- For comma-separated lists like "Banned words: AR/VR/NFT/blockchain", extract each item as a SEPARATE negative constraint.
- Each constraint_text must be a short, self-contained bullet-point item that can be passed verbatim to another LLM as a checklist.
- For negative constraints, phrase as "Do not use X" or "Avoid X" so the intent is unambiguous.
- For positive constraints, use a short descriptive phrase.
- If the prompt contains no identifiable constraints, return an empty list.

Respond ONLY with a valid JSON object matching the ConstraintExtractionResult schema.
"""


@dataclass
class ExtractConstraints:
    """
    Extract and classify constraints from a user's project prompt.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str

    @classmethod
    def execute(cls, llm: LLM, user_prompt: str) -> "ExtractConstraints":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")

        logger.debug(f"User Prompt:\n{user_prompt}")

        system_prompt = EXTRACT_CONSTRAINTS_SYSTEM_PROMPT.strip()

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(ConstraintExtractionResult)
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

        pydantic_instance: ConstraintExtractionResult = chat_response.raw
        if pydantic_instance is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")
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
    def convert_to_markdown(extraction_result: ConstraintExtractionResult) -> str:
        if not isinstance(extraction_result, ConstraintExtractionResult):
            raise ValueError("Response must be a ConstraintExtractionResult object.")

        constraints = extraction_result.constraints
        if not constraints:
            return "No constraints identified."

        positive = [c for c in constraints if c.classification == "positive"]
        negative = [c for c in constraints if c.classification == "negative"]

        parts = []
        if positive:
            parts.append("## Positive Constraints\n")
            for c in positive:
                parts.append(f"- {c.constraint_text}")
            parts.append("")
        if negative:
            parts.append("## Negative Constraints\n")
            for c in negative:
                parts.append(f"- {c.constraint_text}")
            parts.append("")

        return "\n".join(parts)

    def save_markdown(self, file_path: str) -> None:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.markdown)


if __name__ == "__main__":
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_api.prompt_catalog import PromptCatalog

    llm = get_llm("ollama-llama3.1")

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()

    # Test with Minecraft escape-room prompt (has banned words)
    item = prompt_catalog.find("f717e0c0-73b4-4e12-8d1d-8ec426966122")
    if item:
        print(f"=== Prompt: {item.prompt[:80]}... ===")
        result = ExtractConstraints.execute(llm, item.prompt)
        json_response = result.to_dict(include_system_prompt=False, include_user_prompt=False, include_metadata=False)
        print(f"Response: {json.dumps(json_response, indent=2)}")
        print(f"\nMarkdown:\n{result.markdown}")

    # Test with simple prompt (no negative constraints)
    item = prompt_catalog.find("4dc34d55-0d0d-4e9d-92f4-23765f49dd29")
    if item:
        print(f"\n=== Prompt: {item.prompt} ===")
        result = ExtractConstraints.execute(llm, item.prompt)
        json_response = result.to_dict(include_system_prompt=False, include_user_prompt=False, include_metadata=False)
        print(f"Response: {json.dumps(json_response, indent=2)}")
        print(f"\nMarkdown:\n{result.markdown}")
