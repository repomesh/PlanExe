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

R&D is NOT a physics violation. A project whose stated purpose is to investigate, develop, or scale up a phenomenon whose underlying mechanism is consistent with known physics — i.e. the mechanism has been observed somewhere in nature or in the laboratory, even if humans have not engineered it at the required scale, duration, or in the required materials — is LEGITIMATE RESEARCH and stays "low". The "no prior at that scale" gap is what R&D exists to investigate; it is an engineering/empirical-evidence question, not a physics-law question. Concerns about empirical evidence, proven-at-scale claims, materials availability, or feasibility of unproven technology are not physics violations and stay "low" here, no matter how ambitious the target.

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


if __name__ == "__main__":
    # Smoke harness for ViolatesKnownPhysics.
    #
    # Pulls a sample of N prompts from the simple-plan catalog and
    # runs the physics-violation check against each, printing the
    # rated level, the justification, and the suggested mitigation.
    # Bump SAMPLE_SEED to draw a different shuffle of the catalog;
    # the same seed produces the same sample so iterations on the
    # system prompt can be compared head-to-head.
    #
    # Run: python -m worker_plan_internal.self_audit.violates_known_physics
    import logging
    import random
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_internal.llm_util.llm_executor import LLMModelWithInstance
    from worker_plan_api.prompt_catalog import PromptCatalog
    from worker_plan_api.planexe_dotenv import PlanExeDotEnv

    PlanExeDotEnv.load().update_os_environ()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    LLM_NAME = "openrouter-gpt-oss-safeguard-20b-nitro"
    SAMPLE_SEED = 800
    SAMPLE_SIZE = 10

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    sorted_items = sorted(all_items, key=lambda x: x.id)

    rng = random.Random(SAMPLE_SEED)
    shuffled = list(sorted_items)
    rng.shuffle(shuffled)
    sample_items = shuffled[:SAMPLE_SIZE]

    llm = get_llm(LLM_NAME, temperature=0.0)
    llm_executor = LLMExecutor(llm_models=[LLMModelWithInstance(llm)])

    print(
        f"=== Violates Known Physics — sample of {len(sample_items)} "
        f"catalog prompts (SAMPLE_SEED={SAMPLE_SEED}, model={LLM_NAME}) ==="
    )

    level_counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    error_count = 0

    for idx, item in enumerate(sample_items, start=1):
        prompt_id = item.id
        prompt_preview = item.prompt[:100].replace("\n", " ")
        print(f"\n[{idx}/{len(sample_items)}] {prompt_id}")
        print(
            f"  prompt: {prompt_preview}"
            f"{'...' if len(item.prompt) > 100 else ''}"
        )
        try:
            result = ViolatesKnownPhysics.execute(llm_executor, item.prompt)
        except Exception as exc:
            error_count += 1
            print(f"  ERROR: {exc}")
            continue
        level_counts[result.level] = level_counts.get(result.level, 0) + 1
        print(f"  level: {result.level}")
        print(f"  justification: {result.justification}")
        print(f"  mitigation: {result.mitigation}")

    print("\n=== Summary ===")
    for lvl in ("low", "medium", "high"):
        print(f"  {lvl:6}: {level_counts.get(lvl, 0)}")
    if error_count:
        print(f"  errors: {error_count}")
