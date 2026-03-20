"""
The identify_potential_levers.py script creates a list of levers, some of which are duplicates.
This script deduplicates the list using a single-call Likert scoring approach.

Each lever is scored on a 5-point scale:
  2 = primary (essential strategic decision)
  1 = secondary (useful but supporting)
  0 = borderline
 -1 = overlapping (absorbed by another lever)
 -2 = irrelevant (fully redundant)

Levers scoring >= 1 are kept; levers scoring <= 0 are removed.

PROMPT> python -m worker_plan_internal.lever.deduplicate_levers

"""
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Literal
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from pydantic import BaseModel, Field, ValidationError
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested

logger = logging.getLogger(__name__)

OPTIMIZE_INSTRUCTIONS = """\
Goal: consolidate a brainstormed list of levers into a deduplicated,
prioritized set by scoring each lever on a Likert scale (-2 to +2).
The surviving levers (score >= 1) should be distinct, grounded, and
actionable — ready for enrichment and scenario generation downstream.

Pipeline context
----------------
This step (DeduplicateLevers) is part of a 6-step solution-space
exploration pipeline inside run_plan_pipeline.py:

  1. IdentifyPotentialLevers  — brainstorms 15-20 raw levers
  2. DeduplicateLevers        ← you are here
  3. EnrichLevers             — adds description, synergy, and conflict text
  4. FocusOnVitalFewLevers    — filters down to 4-6 high-impact levers
  5. ScenarioGeneration       — builds 3 scenarios (aggressive, medium, safe)
  6. ScenarioSelection        — picks the best-fitting scenario

Step 1 intentionally over-generates. This step's job is to remove
near-duplicates and tag each surviving lever as primary (strategic) or
secondary (operational). Over-removal is worse than over-inclusion —
step 4 handles further filtering. The classification field (primary/
secondary) is consumed by downstream steps for prioritization.

Known problems to guard against
--------------------------------
- Blanket-primary. Weak models score nearly every lever as 2,
  performing zero removals. Watch for runs where all scores are >= 1.
- Over-inclusion. Mid-tier models keep 10-12 of 15 levers instead of
  the expected 5-8. Check the score distribution.
- Hierarchy-direction errors. Models score -1 on the general lever
  and keep the narrow one — reversed from correct behavior. The more
  general lever should survive; the specific one should be removed.
- Chain absorption. When lever A overlaps B and B overlaps C, all
  three end up removed except C. Check that the surviving lever is
  the most general.
- Calibration capping. Narrow calibration ranges act as stopping
  signals — models stop scoring negatively once they hit a threshold.
- Definition mirroring. Weak models copy the score definition verbatim
  into every justification (e.g. "addresses a real concern but does
  not gate the core outcome"), producing content-free boilerplate.
  The model loses the ability to distinguish levers from each other,
  which also suppresses negative scores. Fix: the prompt uses a
  conditional question test ("If this lever were handled wrong, would
  the project fail?") rather than a reusable dictionary definition.
"""

# --- Pydantic Models ---

class LeverScoreDecision(BaseModel):
    """Score decision for a single lever."""
    lever_id: str = Field(description="The lever_id being scored.")
    score: Literal[-2, -1, 0, 1, 2] = Field(
        description=(
            "Relevance score: "
            "2 (primary — essential strategic decision that gates the project's success), "
            "1 (secondary — addresses a real concern but not a top-level strategic choice), "
            "0 (borderline — marginal value, could go either way), "
            "-1 (overlapping — significantly overlaps another lever, state which lever_id in justification), "
            "-2 (irrelevant — fully redundant, removing it loses nothing)."
        )
    )
    justification: str = Field(
        description=(
            "Concise justification for the score (~40-80 words). "
            "For score -1, state which lever_id absorbs this one and why. "
            "For score 2, explain why this lever is essential. "
            "Do not reuse the score definition as your justification."
        )
    )

class BatchDeduplicationResult(BaseModel):
    """Complete deduplication result for all levers in a single call."""
    decisions: List[LeverScoreDecision] = Field(
        description="One score decision per input lever. Must cover every lever_id from the input."
    )

class LeverDecision(BaseModel):
    """Stored decision for each lever (used in response output)."""
    lever_id: str
    score: Literal[-2, -1, 0, 1, 2]
    justification: str

class InputLever(BaseModel):
    """Represents a single lever loaded from the initial brainstormed file."""
    lever_id: str
    name: str
    consequences: str
    options: List[str]
    review: str

class OutputLever(InputLever):
    """A lever that survived deduplication, with its classification and justification."""
    classification: Literal["primary", "secondary"]
    deduplication_justification: str


def _score_to_classification(score: int) -> Literal["primary", "secondary", "remove"]:
    """Map a Likert score to a classification label."""
    if score >= 2:
        return "primary"
    elif score >= 1:
        return "secondary"
    else:
        return "remove"


DEDUPLICATE_SYSTEM_PROMPT = """
You are evaluating a set of strategic levers for a project. Your task is to score
every lever on a 5-point Likert scale and provide a justification.

**Scoring scale:**

- **2** (primary): Lever is an essential strategic decision — it directly gates
  the project's success or failure. Ask: "If this lever were handled wrong,
  would the project fail in a fundamentally different way?" If yes, score 2.

- **1** (secondary): Lever addresses a real project concern but does not gate
  the core outcome. It matters for delivery quality but is not a top-level
  strategic choice.

- **0** (borderline): Marginal value. Could be kept or removed without
  significant impact. Use sparingly — most levers should have a clear
  positive or negative score.

- **-1** (overlapping): Lever significantly overlaps with another lever.
  State the lever_id it overlaps with in your justification. When two levers
  overlap, score -1 on the more specific one, keeping the more general one.

- **-2** (irrelevant): Fully redundant. Removing this lever loses no meaningful
  detail. The concern it raises is already fully covered elsewhere.

**Rules:**

- Score every lever in the input. Do not skip any.
- Each justification must name the specific lever and explain your reasoning.
  Do not reuse the score definition text as your justification.
- When uncertain between keeping and removing, prefer keeping (score 1 over 0).
- Expect to score 25-50% of levers at 0 or below. If you score everything
  1 or 2, reconsider — the input almost always contains near-duplicates.
- Compare all levers against each other before assigning scores. You see the
  full list at once — use that global view.
"""

@dataclass
class DeduplicateLevers:
    """Holds the results of the deduplication."""
    user_prompt: str
    system_prompt: str
    response: List[LeverDecision]
    deduplicated_levers: List[OutputLever]
    metadata: List[Dict[str, Any]]

    @classmethod
    def execute(cls, llm_executor: LLMExecutor, project_context: str, raw_levers_list: List[dict]) -> 'DeduplicateLevers':
        """
        Executes the deduplication process using a single batch LLM call.

        All levers are scored simultaneously on a Likert scale (-2 to +2).
        Levers scoring >= 1 are kept as primary (2) or secondary (1).
        Levers scoring <= 0 are removed.
        """
        try:
            input_levers = [InputLever(**lever) for lever in raw_levers_list]
        except ValidationError as e:
            raise ValueError(f"Invalid input lever data: {e}")

        if not input_levers:
            raise ValueError("No input levers to deduplicate.")

        logger.info(f"Starting deduplication for {len(input_levers)} levers (single-call scoring).")

        levers_json = json.dumps([lever.model_dump() for lever in input_levers], indent=2)

        system_prompt = DEDUPLICATE_SYSTEM_PROMPT.strip()

        # Build the single prompt with all levers.
        user_prompt = (
            f"**Project Context:**\n{project_context}\n\n"
            f"**Levers to score ({len(input_levers)} total):**\n{levers_json}\n\n"
            f"Score every lever on the Likert scale (-2 to +2) with a justification."
        )

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        def execute_function(llm: LLM) -> dict:
            sllm = llm.as_structured_llm(BatchDeduplicationResult)
            chat_response = sllm.chat(chat_message_list)
            return {"chat_response": chat_response, "metadata": dict(llm.metadata)}

        # Single LLM call.
        batch_result: BatchDeduplicationResult | None = None
        metadata_list: List[dict] = []
        try:
            result = llm_executor.run(execute_function)
            batch_result = result["chat_response"].raw
            metadata_list.append(result.get("metadata", {}))
        except PipelineStopRequested:
            raise
        except Exception as e:
            logger.error(f"Batch deduplication call failed: {e}")

        # Build decisions from the batch result.
        decisions: List[LeverDecision] = []
        input_lever_ids = {lever.lever_id for lever in input_levers}

        if batch_result is not None:
            for score_decision in batch_result.decisions:
                if score_decision.lever_id not in input_lever_ids:
                    logger.warning(f"LLM returned score for unknown lever_id: '{score_decision.lever_id}'. Skipping.")
                    continue
                decisions.append(LeverDecision(
                    lever_id=score_decision.lever_id,
                    score=score_decision.score,
                    justification=score_decision.justification,
                ))

        # Handle missing decisions — any lever not scored defaults to primary.
        scored_ids = {d.lever_id for d in decisions}
        for lever in input_levers:
            if lever.lever_id not in scored_ids:
                logger.warning(f"Lever {lever.lever_id}: not scored by LLM. Defaulting to primary (score 2).")
                decisions.append(LeverDecision(
                    lever_id=lever.lever_id,
                    score=2,
                    justification="Not scored by LLM. Keeping as primary to avoid data loss.",
                ))

        # Build output levers (keep score >= 1).
        decisions_by_id = {d.lever_id: d for d in decisions}
        output_levers = []
        for lever in input_levers:
            lever_decision = decisions_by_id[lever.lever_id]
            if lever_decision.score < 1:
                continue

            deduplication_justification = lever_decision.justification.strip()
            if len(deduplication_justification) == 0:
                deduplication_justification = "Empty explanation. Keeping this lever."

            output_lever = OutputLever(
                **lever.model_dump(),
                classification=_score_to_classification(lever_decision.score),
                deduplication_justification=deduplication_justification,
            )
            output_levers.append(output_lever)

        logger.info(
            f"Deduplication complete: {len(output_levers)} kept, "
            f"{len(input_levers) - len(output_levers)} removed."
        )

        return cls(
            user_prompt=project_context,
            system_prompt=system_prompt,
            response=decisions,
            deduplicated_levers=output_levers,
            metadata=metadata_list,
        )

    def to_dict(self, include_response=True, include_deduplicated_levers=True, include_metadata=True, include_system_prompt=True, include_user_prompt=True) -> dict:
        d = {}
        if include_response:
            d["response"] = [item.model_dump() for item in self.response]
        if include_deduplicated_levers:
            d['deduplicated_levers'] = [lever.model_dump() for lever in self.deduplicated_levers]
        if include_metadata:
            d['metadata'] = self.metadata
        if include_system_prompt:
            d['system_prompt'] = self.system_prompt
        if include_user_prompt:
            d['user_prompt'] = self.user_prompt
        return d

    def save_raw(self, file_path: str) -> None:
        Path(file_path).write_text(json.dumps(self.to_dict(), indent=2))

    def save_clean(self, file_path: Path) -> None:
        """Saves the final, deduplicated list of levers to a JSON file."""
        output_data = [lever.model_dump() for lever in self.deduplicated_levers]
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2)
            logger.info(f"Successfully saved {len(output_data)} deduplicated levers to {file_path!r}.")
        except IOError as e:
            logger.error(f"Failed to write output to {file_path!r}: {e}")

if __name__ == "__main__":
    from worker_plan_internal.prompt.prompt_catalog import PromptCatalog
    from worker_plan_internal.llm_util.llm_executor import LLMModelFromName

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()

    prompt_id = "19dc0718-3df7-48e3-b06d-e2c664ecc07d"
    # prompt_id = "b9afce6c-f98d-4e9d-8525-267a9d153b51"
    prompt_item = prompt_catalog.find(prompt_id)
    if not prompt_item:
        raise ValueError("Prompt item not found.")
    project_context = prompt_item.prompt

    # This file is created by identify_potential_levers.py
    input_file = os.path.join(os.path.dirname(__file__), 'test_data', f'identify_potential_levers_{prompt_id}.json')
    with open(input_file, 'r', encoding='utf-8') as f:
        raw_levers_data = json.load(f)

    output_file = f"deduplicate_levers_{prompt_id}.json"

    model_names = ["ollama-llama3.1"]
    llm_models = LLMModelFromName.from_names(model_names)
    llm_executor = LLMExecutor(llm_models=llm_models)

    # --- Run Deduplication ---
    result = DeduplicateLevers.execute(
        llm_executor=llm_executor,
        project_context=project_context,
        raw_levers_list=raw_levers_data
    )

    d = result.to_dict(include_response=True, include_deduplicated_levers=True, include_metadata=True, include_system_prompt=False, include_user_prompt=False)
    d_json = json.dumps(d, indent=2)
    logger.info(f"Deduplication result: {d_json}")
    logger.info(f"Lever count after deduplication: {len(result.deduplicated_levers)}.")

    # --- Save Output ---
    result.save_clean(output_file)
