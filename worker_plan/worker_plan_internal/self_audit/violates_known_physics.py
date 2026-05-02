"""
Dedicated check for "Violates Known Physics" (self-audit item 1).

Why this lives in its own module
--------------------------------
The shared self-audit batch path produced unreliable verdicts on this
item. Iterations of the shared system prompt addressed several
false-positive modes (regulatory laws confused with physics laws,
"missing fundamentals" treated as physics gaps, surface-keyword
latching on words like "physical"), but small/medium models still
occasionally rate medium/high while the justification cites a
non-physics concern (governance, change-control, currency hedging,
linguistic detail).

Isolating the check lets us:
  - keep the system prompt focused on a single mechanical question
    ("which named law of physics is broken, and what physical quantity
    does the violation involve?") without the rest of the audit's
    rubric crowding it.
  - run a deterministic safety net: if the LLM rates >= medium but the
    justification names no physics law, force the rating back to "low"
    and replace the mitigation with a template. The HARD GATE in the
    instruction asks the model to do this; the code enforces it when
    the model fails.
  - extend the response shape later (confidence score, list of
    detected physics laws, telemetry flags) without disturbing the
    shared ChecklistAnswer schema in self_audit.py.

The result is consumed by self_audit.SelfAudit.execute, which splices
it in as the first entry of checklist_answers_cleaned.
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

logger = logging.getLogger(__name__)

CHECKLIST_INDEX = 1
CHECKLIST_TITLE = "Violates Known Physics"
CHECKLIST_SUBTITLE = (
    "Does the plan's success require breaking a known law of physics "
    "(e.g., thermodynamics, conservation of energy, speed-of-light "
    "limit, causality)?"
)

# Substrings checked against the lowercased justification when level is
# medium/high. If none match, the rating is downgraded to "low". Keep
# this list aligned with the named laws cited in SYSTEM_PROMPT.
PHYSICS_LAW_KEYWORDS: tuple[str, ...] = (
    "thermodynamics",
    "second law",
    "entropy",
    "perpetual motion",
    "conservation of energy",
    "energy conservation",
    "conservation of momentum",
    "momentum conservation",
    "reactionless",
    "speed of light",
    "speed-of-light",
    "faster than light",
    "faster-than-light",
    "ftl",
    "causality",
    "closed timelike",
    "time travel",
    "pauli exclusion",
    "uncertainty principle",
    "relativity",
    "conservation of mass",
    "mass-energy",
    "mass energy",
)

LOW_FALLBACK_MITIGATION = (
    "Project Manager: During scope reviews, confirm no plan element "
    "requires violating a named law of physics — no further action "
    "required."
)

SYSTEM_PROMPT = """\
You assess one yes/no question about a project plan: does the plan's success literally require breaking a specific named law of physics?

Default answer: NO. The vast majority of real-world plans — even ambitious, expensive, regulated, or technically novel ones — do NOT break any law of physics, and your default rating is "low".

Rate "high" ONLY when ALL of the following hold:
1. You can name a specific law of physics that the plan would have to break. Examples include: second law of thermodynamics, conservation of energy, conservation of momentum, speed-of-light limit, causality, Pauli exclusion principle, conservation of mass-energy.
2. You can describe in one sentence the physical-quantity violation: what is being created from nothing, destroyed, or transmitted faster than physics allows.
3. The violation is required for plan success — the plan cannot succeed without it.

Rate "medium" only if the plan invokes a physical effect that is consistent with known physics in principle but unproven at the required scale, AND the plan has no fallback. Use sparingly.

Otherwise rate "low".

Out of scope — these are NOT physics violations and MUST stay "low":
- Regulatory, permitting, licensing, safety-handling, or authorisation gaps.
- Missing implementation details, undefined parameters, vague deliverables, "Missing Information" items.
- Ambitious timelines, budget concerns, currency or financial risk.
- Governance, staffing, change-control, or organisational gaps.
- Linguistic, social, or policy design.
- Real-world materials, including radioisotopes.
- Surface-level keyword cues such as the words "physical", "fundamental", "science", "law", or "physical location" appearing in the plan.

Output a JSON object with three fields, in this order:
- justification: 1-2 sentences. If level is "low", state plainly that no plan element requires breaking a named law of physics. If level is "medium" or "high", you MUST name the specific physics law and describe the physical-quantity violation; if you cannot, level is "low".
- mitigation: one assignable task, ~30 words, with role/team + verb + relative timeframe (e.g., "within 14 days", "within 3 months"). Never use absolute calendar dates. When level is "low", the mitigation must stay on the physics-violation topic, e.g., "Project Manager: During scope reviews, confirm no plan element requires violating a named law of physics — no further action required."
- level: one of "low", "medium", "high". Must agree with the justification — if the justification does not name a specific physics law, level MUST be "low".
"""


class _LLMResponse(BaseModel):
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
    """Result of the dedicated physics-violation check.

    `justification` / `mitigation` / `level` are the post-fallback
    values that should be surfaced in the audit output. The `llm_*`
    fields preserve the original LLM verdict for telemetry and
    debugging — useful when investigating whether the deterministic
    fallback is firing too often.
    """

    plan_prompt: str
    system_prompt: str
    justification: str
    mitigation: str
    level: str
    llm_justification: str
    llm_mitigation: str
    llm_level: str
    fallback_applied: bool
    metadata: dict

    @classmethod
    def execute(cls, llm: LLM, plan_prompt: str) -> "ViolatesKnownPhysics":
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(plan_prompt, str):
            raise ValueError("Invalid plan_prompt.")

        system_prompt = SYSTEM_PROMPT.strip()
        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=plan_prompt),
        ]

        sllm = llm.as_structured_llm(_LLMResponse)
        start_time = time.perf_counter()
        try:
            chat_response = sllm.chat(chat_message_list)
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.error(
                f"physics check LLM failed [{llm_error.error_id}]",
                exc_info=True,
            )
            raise llm_error from e
        duration = int(ceil(time.perf_counter() - start_time))

        raw: _LLMResponse = chat_response.raw
        if raw is None:
            raise ValueError(
                "LLM returned empty structured response (chat_response.raw is None)."
            )

        llm_level = raw.level.lower().strip()
        llm_justification = raw.justification.strip()
        llm_mitigation = raw.mitigation.strip()

        level = llm_level
        justification = llm_justification
        mitigation = llm_mitigation
        fallback_applied = False

        if level in ("medium", "high") and not _justification_names_physics_law(
            llm_justification
        ):
            logger.warning(
                "Physics check downgraded to 'low': llm_level=%s but "
                "justification names no physics law: %r",
                llm_level,
                llm_justification,
            )
            level = "low"
            justification = (
                "Rated LOW because the justification did not name a "
                f"specific law of physics. Auto-downgraded — original "
                f"LLM verdict was '{llm_level}' but cited a non-physics "
                "concern."
            )
            mitigation = LOW_FALLBACK_MITIGATION
            fallback_applied = True

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration"] = duration
        metadata["fallback_applied"] = fallback_applied

        return cls(
            plan_prompt=plan_prompt,
            system_prompt=system_prompt,
            justification=justification,
            mitigation=mitigation,
            level=level,
            llm_justification=llm_justification,
            llm_mitigation=llm_mitigation,
            llm_level=llm_level,
            fallback_applied=fallback_applied,
            metadata=metadata,
        )


def _justification_names_physics_law(text: str) -> bool:
    haystack = text.lower()
    return any(kw in haystack for kw in PHYSICS_LAW_KEYWORDS)
