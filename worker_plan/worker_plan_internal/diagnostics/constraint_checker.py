"""
Check pipeline stage outputs for constraint violations.

Given the extracted constraints (from extract_constraints) and a pipeline stage's
JSON output, uses an LLM to check whether any constraints are violated. Focuses
on detecting negative constraints that have been misinterpreted as positive
(e.g., "Banned words: VR, Crypto" leading to VR/Crypto appearing in the plan).

PROMPT> python -m worker_plan_internal.diagnostics.constraint_checker
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


class ConstraintViolationItem(BaseModel):
    """Assessment of a single constraint against a pipeline stage output."""
    constraint_text: str = Field(
        description="The original constraint text being checked."
    )
    constraint_classification: Literal["positive", "negative"] = Field(
        description="Whether this is a positive or negative constraint."
    )
    status: Literal["satisfied", "violated", "unclear"] = Field(
        description=(
            "'satisfied' if the constraint is respected in the stage output. "
            "'violated' if the constraint is broken (e.g., a banned word appears as a recommendation). "
            "'unclear' if there is not enough information to determine."
        )
    )
    evidence: str = Field(
        description="A short quote or reference from the stage output that supports the status assessment."
    )
    explanation: str = Field(
        description="1-2 sentence explanation of why this constraint is satisfied, violated, or unclear."
    )


class ConstraintCheckResult(BaseModel):
    """Structured output for constraint checking of a pipeline stage."""
    constraint_violations: list[ConstraintViolationItem] = Field(
        description="Assessment of each constraint against the stage output."
    )
    overall_status: Literal["pass", "fail"] = Field(
        description=(
            "'pass' if no constraints are violated. "
            "'fail' if one or more constraints are violated."
        )
    )
    summary: str = Field(
        description="1-3 sentence summary of the constraint check results."
    )


CONSTRAINT_CHECKER_SYSTEM_PROMPT = """
You are an expert at verifying whether project plan outputs respect user-specified constraints. You will receive:

1. A list of CONSTRAINTS the user specified (each classified as "positive" or "negative")
2. The JSON output of a pipeline stage

Your job is to check each constraint against the stage output and determine if it is satisfied, violated, or unclear.

CONSTRAINT TYPES:
- **Positive constraints** are things the user WANTS. Check that the stage output is aligned with or supportive of them. A positive constraint is "satisfied" if the output doesn't contradict it. It is "violated" only if the output actively works against it.
- **Negative constraints** are things the user wants to AVOID. This is the critical check. A negative constraint is "violated" if the banned item appears in the output as a recommendation, option, lever, scenario element, or positive suggestion. The banned item should NOT appear in the plan at all except in explicit exclusion notes.

CHECKING RULES:
- For each constraint, look through the entire stage output for mentions of the constrained item.
- For negative constraints: if a banned word/technology/concept appears as a lever name, option, recommendation, or positive element, that is a VIOLATION.
- For negative constraints: if a banned item is mentioned only in the context of "this was excluded" or "this was avoided", that is NOT a violation.
- For positive constraints: only mark as "violated" if the output actively contradicts the constraint. If the constraint simply isn't mentioned, mark as "unclear" rather than "violated".
- Provide specific evidence (quote the relevant text from the stage output) for each assessment.

OVERALL STATUS:
- "pass" if zero constraints have status "violated"
- "fail" if one or more constraints have status "violated"

Respond ONLY with a valid JSON object matching the ConstraintCheckResult schema.
"""


@dataclass
class ConstraintChecker:
    """
    Check a pipeline stage's output against extracted constraints.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict

    @classmethod
    def execute(cls, llm: LLM, constraints_json: str, stage_output_json: str, stage_name: str) -> "ConstraintChecker":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")

        logger.debug(f"Checking constraints for stage: {stage_name}")

        system_prompt = CONSTRAINT_CHECKER_SYSTEM_PROMPT.strip()

        user_prompt = (
            f"## Constraints\n{constraints_json}\n\n"
            f"## Stage Output ({stage_name})\n{stage_output_json}"
        )

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(ConstraintCheckResult)
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
            f"Constraint check for '{stage_name}' completed in {duration} seconds. "
            f"Response byte count: {response_byte_count}"
        )

        pydantic_instance: ConstraintCheckResult = chat_response.raw
        if pydantic_instance is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")
        json_response = pydantic_instance.model_dump()

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration"] = duration
        metadata["response_byte_count"] = response_byte_count
        metadata["stage_name"] = stage_name

        return cls(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
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


if __name__ == "__main__":
    from worker_plan_internal.llm_factory import get_llm

    llm = get_llm("ollama-llama3.1")

    # Example: check a fake stage output against constraints
    constraints = json.dumps({
        "constraints": [
            {"classification": "positive", "constraint_text": "Minecraft themed escape-room"},
            {"classification": "positive", "constraint_text": "Shanghai"},
            {"classification": "negative", "constraint_text": "Do not use AR/VR"},
            {"classification": "negative", "constraint_text": "Do not use blockchain"},
        ]
    }, indent=2)

    stage_output = json.dumps({
        "levers": [
            {"name": "Technology Integration", "options": ["VR immersion rooms", "AR overlay guides", "Physical-only puzzles"]},
            {"name": "Venue Design", "options": ["Minecraft pixel art walls", "Standard escape room", "Hybrid digital-physical"]},
        ]
    }, indent=2)

    result = ConstraintChecker.execute(llm, constraints, stage_output, "potential_levers")
    print(json.dumps(result.to_dict(include_system_prompt=False, include_user_prompt=False), indent=2))
