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
You assess one question about a project plan: does the plan put it at odds with the laws of physics? There are two ways this can happen — flag either.

Default answer: NO. The vast majority of real-world plans — even ambitious, expensive, regulated, or technically novel ones — do NOT clash with the laws of physics, and your default rating is "low".

Rate "high" when EITHER (A) or (B) holds. The justification MUST name the specific physics law or directly-observable physical fact that the plan contradicts.

(A) IMPOSSIBLE-ENGINEERING — the plan's success literally requires breaking a specific named law of physics. ALL of these must hold:
1. You can name a specific law of physics that would have to break. Examples include: second law of thermodynamics, conservation of energy, conservation of momentum, speed-of-light limit, causality, Pauli exclusion principle, conservation of mass-energy.
2. You can describe in one sentence the physical-quantity violation: what is being created from nothing, destroyed, or transmitted faster than physics allows.
3. The violation is required for plan success — the plan cannot succeed without it.

(B) PROPAGATING-FALSEHOOD — the plan's stated mechanism, success criteria, billing model, or constructed infrastructure depends on customers, students, citizens, or institutional partners accepting as true either:
  (B.1) a claim that directly contradicts a named law of physics or a well-established empirical observation about the physical world (e.g., conservation laws, speed-of-light limit, basic mechanics, radiometric ages, geodesy and the observed structure of the planet, the standard model); OR
  (B.2) a causal mechanism that has no physical basis — the plan requires real-world outcomes (revenue, legal effect, scheduling decisions, measurable change in objects or events) to be produced or constrained by something physics does not describe and that has no empirical basis. Physics describes the causal mechanisms by which physical objects and events influence each other; a plan whose load-bearing mechanism is non-physical is asserting a physics-incompatible claim, regardless of which cultural, religious, or traditional framework the mechanism is drawn from. Important: software, parsers, contracts, curricula, financial flows, supply chains, organisational processes, regulatory frameworks, and other engineering or institutional artifacts ARE physical mechanisms in the relevant sense — they exist as information running on hardware or as documented agreements implemented through human action, all of which is described by physics. "Load-bearing engineering deliverable required for plan success" is NOT (B.2). (B.2) only triggers when the load-bearing mechanism itself is something physics simply does not describe.

ALL of these must hold for HIGH:
1. The plan asserts the claim as true — to students, customers, citizens, or via constructed infrastructure — not as a hypothesis under investigation, not as a survey of fringe views, not as a documentary about other people's beliefs. Marketing or product descriptions that present the mechanism as producing real effects count as assertion; the operators' private belief is irrelevant.
2. The claim is load-bearing for the plan: it appears in the stated mechanism, success criteria, billing model, output, constructed infrastructure, or value proposition to the audience — not merely as an aside or cultural backdrop.
3. You can identify the specific physics law, empirical fact, or absent-physical-mechanism the plan invokes.

A plan that surveys, studies, or critically examines a fringe claim is doing legitimate inquiry and stays "low". A cultural, religious, or contemplative practice offered for community, identity, or personal value with no claim of measurable physical outcome stays "low".

Where the line falls under (B.2): the question is structural, not cultural. Cultural framing, religious tradition, or widespread practice of the mechanism does NOT exempt a plan from HIGH. Subjective success metrics (client self-report, customer satisfaction with absence of negative events) do NOT exempt a plan if the metric is operationalized as evidence the mechanism worked. Use this test: would the plan's billing model, success criteria, legal authority, or institutional structure still make sense if the non-physical mechanism is acknowledged to have no causal power? If no — if the plan only "works" because the non-physical mechanism is treated as actually producing real-world effects — that is load-bearing non-physical causation and the rating is HIGH.

Concrete operational tests for (B.2):
- Does the plan's revenue model require customers to pay because the non-physical mechanism produces a real-world change?
- Does the plan publish a success metric measuring a real-world outcome (commercial, behavioural, audit-measured, statistical correlation, or self-reported absence of phenomena) and attribute that outcome to the non-physical mechanism?
- Does the plan's legal or institutional structure grant the non-physical mechanism authority that binds real-world decisions?
If yes to any, HIGH.

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
- justification: 1-2 sentences. If level is "low", state plainly that the plan does not require breaking a named law of physics and does not depend on a physics-incompatible claim as a load-bearing mechanism. If level is "medium" or "high", you MUST identify exactly which trigger fires — (A) impossible-engineering, (B.1) contradicts-named-law / observable-fact, or (B.2) non-physical-causation — and either name the specific physics law or empirical fact the plan contradicts (B.1) or describe the non-physical mechanism the plan depends on and the real-world outcome it claims to produce (B.2). If you cannot, level is "low".
- mitigation: when level is "medium" or "high", give one assignable task, ~30 words, with role/team + verb + relative timeframe (e.g., "within 14 days", "within 3 months"). Never use absolute calendar dates. When level is "low", do NOT manufacture a fake action; instead, briefly acknowledge that no physics-related mitigation applies, in the form "No physics-related action required — the plan does not invoke physics-incompatible mechanisms." Do not invent scope reviews, confirmation steps, audits, or other busywork tasks just to satisfy the assignable-task shape; LOW means there is nothing to mitigate.
- level: one of "low", "medium", "high". Must agree with the justification — if the justification does not name a specific physics law / empirical fact the plan contradicts, or a non-physical mechanism the plan's success load-bearing-depends on, level MUST be "low".
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
    SAMPLE_SEED = 1400
    SAMPLE_SIZE = 30

    # Catalog IDs the check is expected to flag HIGH. Run on every
    # smoke invocation regardless of SAMPLE_SEED so each run validates
    # the expected-HIGH set against the current system prompt. Any ID
    # that comes back not-HIGH is reported as a canary failure in the
    # summary. The dict value is the short label printed at runtime;
    # the per-entry comment block above each line explains why the
    # case is in this set and which trigger it should fire under.
    EXPECTED_HIGH_IDS: dict[str, str] = {
        # Curriculum that asserts a flat Earth as taught fact, directly
        # contradicting the observed shape of Earth and the laws governing
        # gravity, orbital mechanics, and geodesy. Trigger (B.1) — load-
        # bearing assertion of a claim that contradicts observed physical
        # fact. Should fire HIGH on every run.
        "2891ff5f-4d6e-4909-a6ac-64af1273275e": "flat-earth education curriculum",
        # Statutory office with binding muhurta certification over cabinet
        # action and procurement; success criteria publicly claim outcome
        # correlation between planetary alignment and policy success.
        # Trigger (B.2) — load-bearing non-physical causation on real-world
        # institutional decisions. Should fire HIGH.
        "16faf60a-c7d0-43e3-90fa-0a8cd7cea8d2": "OSAA — statutory astrological office",
        # B2B spirit-clearance firm with a published 85% no-recurrence
        # success metric and certificate-of-clearance accepted by
        # brokerages. Trigger (B.2) — revenue and KPIs depend on rituals
        # producing measurable real-world change. Should fire HIGH.
        "8e38db3d-01e7-4b22-b6df-b98f074778ff": "Phi-Free — spirit-clearance firm",
        # Cross-border supernatural-commerce platform with synthetic
        # AI-generated lore and sockpuppet community-seeding. Documented
        # scope-mismatch: operators are explicit cynics whose own success
        # metrics are commercial (GMV, ban rate, regulatory survival),
        # not "the rituals worked". The plan is load-bearing on commercial
        # deception, not on supernatural causation. Kept here because the
        # tags include "supernatural" and a future broadening might catch
        # it; the "misinformation about science" framing fits a separate
        # audit item, not this one. Currently expected to LOW under the
        # physics check; canary failure surfaces this at every run.
        "9865dc43-b400-480d-b75e-bc3af292456f": "Nyxa — synthetic supernatural commerce (known scope-mismatch; deception, not load-bearing supernatural causation)",
        # Sex-based federal device-ban policy. Documented scope-mismatch:
        # it is a discrimination / rights problem, not a physics-laws
        # problem (the plan does not assert physics-incompatible claims;
        # it imposes an unjust restriction). Properly attacked by
        # diagnostics/premise_attack.py, which targets fundamental,
        # unfixable flaws in a prompt's premise (including the
        # rights/dignity/consent critique). Do NOT broaden this rule to
        # catch it — that would over-flag a wide class of ideological /
        # political plans and dilute the physics check. Kept here as a
        # documented scope-mismatch canary; expected LOW.
        "7f8a2c4d-000e-4b2c-9466-25ca1641bf12": "ban women from computers (known scope-mismatch; discrimination/rights problem, routed to premise_attack.py)",
    }

    # Catalog IDs already exercised by earlier smoke runs (SEEDs 700,
    # 800, 900). Held out so subsequent runs evaluate the check on
    # prompts the system prompt has not been tuned against. Append
    # new IDs after each fresh smoke run.
    HELD_OUT_IDS: set[str] = {
        # SEED 700
        "79ef9ebf-3173-4b33-81f9-abbd3da7da6d",
        "0bb00fe6-711c-4612-8f83-a9a88e5c7958",
        "cdf7f29d-bbcb-478d-8b5a-e82e74ed8626",
        "d91f09cd-6658-48e7-ae87-1708f814661c",
        "3f8979e5-ac53-4b0b-967e-ee4b9dca34c2",
        "d70ced0b-d5c7-4b84-88d7-18a5ada2cfee",
        "4dc34d55-0d0d-4e9d-92f4-23765f49dd29",
        "96557141-4a70-45c3-84b9-0c56bdb384be",
        "27c733dc-4834-4742-aa2a-b432453aac32",
        "930c2abc-faa7-4c21-8ae1-f0323cbcd120",
        # SEED 800
        "d5a07988-d1e3-4f4f-9614-3ef6af398301",
        "b8aad23f-7c65-46f4-bc1b-9228bae94ab8",
        "1fa30e80-5213-4ed4-9057-5b578e9423b5",
        "2891ff5f-4d6e-4909-a6ac-64af1273275e",
        "22f35414-c01b-4b52-a229-7dc5a78e2b96",
        "23f2b090-98f0-4092-bdc4-3f2b6a5c9317",
        "1382d4a1-5eb0-42f3-b93a-74c066ae1c97",
        "552bb9bb-b515-47fd-a964-b2f4fac17a29",
        "f206f7e9-8ece-4e65-8e7f-5ac1b6777a62",
        "a6158408-3827-4f4f-8577-8844204c5c1f",
        # SEED 900 (new IDs only; overlaps with SEED 700 already listed)
        "061ef161-324c-4fad-8d60-28b8b53d5c90",
        "f717e0c0-73b4-4e12-8d1d-8ec426966122",
        "5c4b4fee-267a-409b-842f-4833d86aa215",
        "4befd126-4288-436a-a753-c2c1dda65fd8",
        "7972e5ab-a526-47ea-9b56-d9da4b9b76ef",
        "c2c45867-be60-4690-aac1-530627fc0818",
        "4060d2de-8fcc-4f8f-be0c-fdae95c7ab4f",
        # SEED 1000 (held-out 20-prompt evaluation)
        "eb516ecc-a097-4a0c-b734-ed5fa09aece0",
        "dcbe5aac-bc36-4beb-a704-c30873c5bad6",
        "9040f467-cce5-4e68-8686-48d4464c4d02",
        "39bc819c-ee86-44c8-b1d4-d6bf3117cb0e",
        "0863bc65-e24e-418d-a1e2-b9857ce31be5",
        "b9afce6c-f98d-4e9d-8525-267a9d153b51",
        "fc0f0be2-125d-42dd-aac3-2e5039fc7938",
        "f4988b26-a846-45b6-9555-52ede44d0238",
        "e9a73d5b-f274-4286-a619-4f0e1303cdc2",
        "cf90d1aa-33d1-4af4-87f0-ff1293e48ad1",
        "b27e6349-ba1d-4604-87bb-936dafc46aee",
        "aa4a78f3-32d7-45ca-9f5a-f3e264eb31d4",
        "f847a181-c9b8-419f-8aef-552e1a3b662f",
        "676cbca8-5d49-42a0-8826-398318004703",
        "62f48a04-6f2c-4e60-9e65-34686a13c95a",
        "b0a4c259-8f3a-46ab-881b-074280c9f6f7",
        "0ad5ea63-cf38-4d10-a3f3-d51baa609abd",
        "45763178-8ba8-4a86-adcd-63ed19d4d47b",
        "1fc46aed-60e2-430b-b524-71d0a2a57805",
        "fe853807-5bfe-4e5b-8071-d6db3c360279",
        # SEED 1100 (held-out 20-prompt evaluation)
        "487d6269-3b4c-4123-8a14-49a95713a77b",
        "a08915c5-2d22-4430-8f56-90565583b776",
        "a6bef08b-c768-4616-bc28-7503244eff02",
        "9eef67c3-ad3e-4a1d-bbb4-5ece12de4eea",
        "899e58f3-e2a6-44f3-b107-0dbca63a38ff",
        "a3479d4b-724f-4700-a4ba-21de3dee22b5",
        "3ca89453-e65b-4828-994f-dff0b679444a",
        "40a47989-0743-4d03-a152-8f7096dfcb5c",
        "307f7e0c-a160-4b7a-9e3c-76577164497e",
        "d52e2fe9-913a-405d-a81f-4290c8121c44",
        "04a91223-02f4-4ca0-b37d-1a353eb475dc",
        "670a390b-e6fd-4b63-a9dc-aa73eb957300",
        "c1a6c000-5641-4a47-9d7f-bbdd84dd5a64",
        "d3e10877-446f-4eb0-8027-864e923973b0",
        "9c74bb8a-1208-4183-9c08-24ec90f86dfd",
        "e543e384-45f0-4d89-8ed1-b424a7d6e8c3",
        "d00e694e-43b0-45ae-b55e-ab8184abf38d",
        "98a8c63e-4770-4ee1-aef8-693800deec0e",
        "19dc0718-3df7-48e3-b06d-e2c664ecc07d",
        "3deda46b-9c9d-4078-a72c-15299b70d915",
        # SEED 1200 (held-out 20-prompt evaluation)
        "6860b2ae-39f0-4517-b827-95befbf142ac",
        "0a61aae5-472d-4e63-8a4e-cf976cb5064b",
        "e6ddd953-939f-4d15-89ec-fd3988f79123",
        "50c0f31f-d9a3-442a-81b8-1d885db05623",
        "30499a0c-e3f8-4569-a169-470e32086ba0",
        "a4b90bc0-e640-4f64-a520-182be267ffd7",
        "eb1017f3-768c-4da4-8566-dd4b8139f1ce",
        "75f41b3c-ef63-4f32-9de8-e25d40403bc3",
        "a9f410c0-120e-45d6-b042-e88ca47b39bb",
        "daa0c969-86ce-4945-9318-00578608aabb",
        "3b2a1c24-5e47-4a89-b9a5-e96ea787adf6",
        "2eaa697a-0657-4de2-aadc-a6f314e88e98",
        "69d60cce-a0ee-4514-bc52-cbf60760b1c5",
        "4def0f4a-47e4-4cea-84db-867408829d52",
        "da8da7a6-954c-4f88-91c9-53f98a934868",
        "9fbb7ff9-5dc3-44f4-9823-dba3f31d3661",
        "87cbb86d-8ee1-4477-a71d-5e702bf6a887",
        "28289ed9-0c80-41cf-9d26-714bffe4e498",
        "2ef3b73b-1008-47a4-be0d-0ea624355c49",
        "ff7076a6-2db5-494c-8c48-9aff48e13e17",
    }

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    sorted_items = sorted(all_items, key=lambda x: x.id)
    fresh_items = [
        it for it in sorted_items
        if it.id not in HELD_OUT_IDS and it.id not in EXPECTED_HIGH_IDS
    ]

    rng = random.Random(SAMPLE_SEED)
    shuffled = list(fresh_items)
    rng.shuffle(shuffled)
    sample_items = shuffled[:SAMPLE_SIZE]

    llm = get_llm(LLM_NAME, temperature=0.0)
    llm_executor = LLMExecutor(llm_models=[LLMModelWithInstance(llm)])

    print(
        f"=== Violates Known Physics — {len(EXPECTED_HIGH_IDS)} canaries + "
        f"sample of {len(sample_items)} catalog prompts "
        f"(SAMPLE_SEED={SAMPLE_SEED}, model={LLM_NAME}) ==="
    )

    level_counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
    error_count = 0
    canary_results: list[tuple[str, str, str]] = []  # (id, label, level)

    print(f"\n--- Expected HIGH canaries ---")
    for prompt_id, label in EXPECTED_HIGH_IDS.items():
        item = prompt_catalog.find(prompt_id)
        if item is None:
            print(f"!! expected-HIGH prompt {prompt_id} ({label}) not in catalog")
            continue
        prompt_preview = item.prompt[:100].replace("\n", " ")
        print(f"\n[canary | {label}] {prompt_id}")
        print(
            f"  prompt: {prompt_preview}"
            f"{'...' if len(item.prompt) > 100 else ''}"
        )
        try:
            result = ViolatesKnownPhysics.execute(llm_executor, item.prompt)
        except Exception as exc:
            error_count += 1
            canary_results.append((prompt_id, label, "error"))
            print(f"  ERROR: {exc}")
            continue
        level_counts[result.level] = level_counts.get(result.level, 0) + 1
        canary_results.append((prompt_id, label, result.level))
        flag = "" if result.level == "high" else "  ⚠ canary failed (expected HIGH)"
        print(f"  level: {result.level} (expected: high){flag}")
        print(f"  justification: {result.justification}")
        print(f"  mitigation: {result.mitigation}")

    print(f"\n--- Random sample ---")
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

    canary_failures = [
        (pid, label, lvl) for (pid, label, lvl) in canary_results if lvl != "high"
    ]
    if canary_failures:
        print(f"\n=== Canary failures ({len(canary_failures)}/{len(canary_results)}) — expected HIGH ===")
        for pid, label, lvl in canary_failures:
            print(f"  {label}: got {lvl} ({pid})")
