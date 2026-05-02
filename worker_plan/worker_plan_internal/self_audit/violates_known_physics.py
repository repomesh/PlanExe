"""
Detect plans whose success literally requires breaking a named law of
physics.

The check is self-contained: it owns its system prompt, response
schema, and result dataclass, and knows nothing about how it is
embedded in any larger pipeline. Callers receive a
`ViolatesKnownPhysics` instance with `justification`, `mitigation`,
`level`, and `metadata`, and decide where (if anywhere) to splice it
into a downstream report.

Why this lives in its own module
--------------------------------
A shared multi-rubric batch prompt produced unreliable verdicts here:
small/medium models latched onto regulatory gaps, missing details,
governance issues, or surface-keyword cues (the words "physical",
"fundamental", "law") and rated medium/high without ever naming a
physics law in the justification. Splitting the check out lets the
system prompt focus on a single mechanical question — "which named
law of physics is broken, and what physical quantity does the
violation involve?" — without the rest of an audit's rubric crowding
it. The dataclass is also free to grow new fields later (confidence
score, second-pass verifier output, telemetry flags) without
touching anything else.

Note on safety nets: an earlier draft used a keyword list against the
justification (thermodynamics / FTL / causality / etc.) to downgrade
spurious medium/high verdicts. That was removed — plans arrive in
many languages (e.g. "tidsrejse" for time travel) so any keyword set
is fragile by design. The check relies on the focused system prompt
and the schema's justification-before-level field order; a future
guard, if needed, should be language-agnostic (e.g. a second LLM
verifier) rather than a keyword filter.
"""
import logging
import time
from math import ceil
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from worker_plan_internal.llm_util.llm_errors import LLMChatError
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You assess one yes/no question about a project plan: does the plan's success literally require breaking a specific named law of physics?

Default answer: NO. The vast majority of real-world plans — even ambitious, expensive, regulated, or technically novel ones — do NOT break any law of physics, and your default rating is "low".

Rate "high" ONLY when ALL of the following hold:
1. You can name a specific law of physics that the plan would have to break. Examples include: second law of thermodynamics, conservation of energy, conservation of momentum, speed-of-light limit, causality, Pauli exclusion principle, conservation of mass-energy.
2. You can describe in one sentence the physical-quantity violation: what is being created from nothing, destroyed, or transmitted faster than physics allows.
3. The violation is required for plan success — the plan cannot succeed without it.

Otherwise rate "low". Use "medium" only for genuine borderline cases where the plan presupposes a physical phenomenon that, if real, would itself redefine known physics; this should be very rare.

R&D is NOT a physics violation. A project whose stated purpose is to investigate, develop, or scale up an effect that is consistent with known physics but currently unproven — for example, building a better battery, developing a new material or alloy, demonstrating a quantum-computing capability, improving solar-cell efficiency — is LEGITIMATE RESEARCH and stays "low". The fact that the effect has not been demonstrated at the required scale yet is exactly what R&D exists to investigate; that gap is not a physics issue. Concerns about empirical evidence, proven-at-scale claims, or feasibility of unproven technology belong to other audit items (e.g., "No Real-World Proof"), not to this one.

Out of scope — these are NOT physics violations and MUST stay "low":
- Regulatory, permitting, licensing, safety-handling, or authorisation gaps.
- Missing implementation details, undefined parameters, vague deliverables, "Missing Information" items.
- Ambitious timelines, budget concerns, currency or financial risk.
- Governance, staffing, change-control, or organisational gaps.
- Linguistic, social, or policy design.
- Real-world materials, including radioisotopes.
- R&D toward unproven-at-scale effects that are consistent with known physics.
- Surface-level keyword cues such as the words "physical", "fundamental", "science", "law", or "physical location" appearing in the plan.

The plan may be written in any language. Assess the plan's actual mechanism, not the words used to describe it.

Output a JSON object with three fields, in this order:
- justification: 1-2 sentences. If level is "low", state plainly that no plan element requires breaking a named law of physics. If level is "medium" or "high", you MUST name the specific physics law and describe the physical-quantity violation; if you cannot, level is "low".
- mitigation: one assignable task, ~30 words, with role/team + verb + relative timeframe (e.g., "within 14 days", "within 3 months"). Never use absolute calendar dates. When level is "low", the mitigation must stay on the physics-violation topic, e.g., "Project Manager: During scope reviews, confirm no plan element requires violating a named law of physics — no further action required."
- level: one of "low", "medium", "high". Must agree with the justification — if the justification does not name a specific physics law, level MUST be "low".
"""


class PhysicsCheck(BaseModel):
    # Field order matters: the structured-output model commits to the
    # first emitted field, then writes the rest. Justification first
    # forces the reasoning onto the page before the level is locked in.
    justification: str = Field(
        description=(
            "Why this level. 1-2 sentences. If medium/high, MUST name a "
            "specific physics law and describe the physical-quantity "
            "violation."
        )
    )
    mitigation: str = Field(
        description=(
            "One concrete action, ~30 words, role + verb + relative "
            "timeframe (no absolute calendar dates)."
        )
    )
    level: Literal["low", "medium", "high"] = Field(
        description=(
            "low / medium / high. If justification does not name a "
            "specific physics law, MUST be 'low'."
        )
    )


@dataclass
class ViolatesKnownPhysics:
    """Result of the dedicated physics-violation check."""

    plan_prompt: str
    system_prompt: str
    justification: str
    mitigation: str
    level: str
    metadata: dict

    @classmethod
    def execute(
        cls,
        llm_executor: LLMExecutor,
        plan_prompt: str,
    ) -> "ViolatesKnownPhysics":
        if not isinstance(llm_executor, LLMExecutor):
            raise ValueError("Invalid LLMExecutor instance.")
        if not isinstance(plan_prompt, str):
            raise ValueError("Invalid plan_prompt.")

        system_prompt = SYSTEM_PROMPT.strip()
        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=plan_prompt),
        ]

        # Closure variables capture the LLM-side outputs from inside
        # llm_executor.run so we don't have to thread them back out
        # through a temporary dict.
        captured_raw: PhysicsCheck | None = None
        captured_metadata: dict = {}

        def chat_with_llm(llm: LLM) -> None:
            nonlocal captured_raw, captured_metadata
            sllm = llm.as_structured_llm(PhysicsCheck)
            start_time = time.perf_counter()
            chat_response = sllm.chat(chat_message_list)
            duration = int(ceil(time.perf_counter() - start_time))

            captured_raw = chat_response.raw
            captured_metadata = dict(llm.metadata)
            captured_metadata["llm_classname"] = llm.class_name()
            captured_metadata["duration"] = duration

        try:
            llm_executor.run(chat_with_llm)
        except PipelineStopRequested:
            raise
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.debug(
                f"physics check LLM failed [{llm_error.error_id}]: {e}"
            )
            logger.error(
                f"physics check LLM failed [{llm_error.error_id}]",
                exc_info=True,
            )
            raise llm_error from e

        if captured_raw is None:
            raise ValueError(
                "LLM returned empty structured response (chat_response.raw is None)."
            )

        return cls(
            plan_prompt=plan_prompt,
            system_prompt=system_prompt,
            justification=captured_raw.justification.strip(),
            mitigation=captured_raw.mitigation.strip(),
            level=captured_raw.level.lower().strip(),
            metadata=captured_metadata,
        )
