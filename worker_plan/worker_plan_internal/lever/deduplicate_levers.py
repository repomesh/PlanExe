"""
The identify_potential_levers.py script creates a list of levers, some of which are duplicates.
This script deduplicates the list using a single batch LLM call.

Each lever is classified as:
  primary   — essential strategic decision, kept
  secondary — useful but supporting, kept
  remove    — redundant or overlapping, discarded

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
prioritized set. The surviving levers (primary + secondary) should be
distinct, grounded, and actionable — ready for enrichment and scenario
generation downstream.

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
- Blanket-primary. Weak models classify nearly every lever as primary,
  performing zero removals. Watch for runs where remove count is 0.
- Over-inclusion. Mid-tier models keep 10-12 of 15 levers instead of
  the expected 5-8. Check the classification distribution.
- Hierarchy-direction errors. Models remove the general lever and keep
  the narrow one — reversed from correct behavior. The more general
  lever should survive; the specific one should be removed.
- Chain absorption. When lever A overlaps B and B overlaps C, all
  three end up removed except C. Check that the surviving lever is
  the most general.
- Calibration capping. Narrow calibration ranges act as stopping
  signals — models stop removing once they hit a threshold.
- Definition mirroring. Weak models copy the classification definition
  verbatim into every justification, producing content-free boilerplate.
  The model loses the ability to distinguish levers from each other,
  which also suppresses remove decisions. Fix: use conditional question
  tests rather than reusable dictionary definitions.
"""

# --- Pydantic Models ---

class LeverClassificationDecision(BaseModel):
    """Classification decision for a single lever in the batch."""
    lever_id: str = Field(description="The lever_id being classified.")
    classification: Literal["primary", "secondary", "remove"] = Field(
        description=(
            "primary: essential strategic decision, "
            "secondary: useful but supporting, "
            "remove: redundant, overlapping with another lever, or irrelevant to this plan."
        )
    )
    justification: str = Field(
        description="Concise justification for the classification (~40 words)."
    )

class BatchDeduplicationResult(BaseModel):
    """Complete deduplication result for all levers in a single call."""
    decisions: List[LeverClassificationDecision] = Field(
        description="One classification per input lever. Must cover every lever_id from the input."
    )

class LeverDecision(BaseModel):
    """Stored decision for each lever (used in response output)."""
    lever_id: str
    classification: Literal["primary", "secondary", "remove"]
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


DEDUPLICATE_SYSTEM_PROMPT = """
You are deduplicating a set of strategic levers for a project plan. Your task
is to classify every lever and provide a justification. You see all levers at
once — compare them against each other before making decisions.

**Classifications:**

- **primary**: This lever is an essential strategic decision for the plan.
  Ask: "If this lever were handled badly, would the project fail or succeed
  in a fundamentally different way?" If yes, classify as primary.

- **secondary**: This lever addresses a real concern in the plan but is not
  a top-level strategic choice. It matters for delivery but does not gate the
  project's core outcome.

- **remove**: This lever should be discarded — either because it overlaps
  with or is a subset of another lever, its concern is already covered, or
  it is irrelevant to this specific plan. When two levers overlap, keep the
  one that better captures the strategic decision and remove the other.

**Rules:**

- Classify every lever in the input. Do not skip any.
- Each justification must explain your reasoning for this specific lever.
- When uncertain between primary and secondary, prefer primary — a false
  positive is recoverable downstream.
- When uncertain between removing and keeping, prefer secondary over remove
  to avoid discarding a potentially important lever.
- Expect to remove 25-50% of the input levers. If you classify everything as
  primary or secondary, reconsider — the input almost always contains
  near-duplicates and overlap.
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

        All levers are classified simultaneously as primary, secondary, or remove.
        Primary and secondary levers are kept; removed levers are discarded.
        """
        try:
            input_levers = [InputLever(**lever) for lever in raw_levers_list]
        except ValidationError as e:
            raise ValueError(f"Invalid input lever data: {e}")

        if not input_levers:
            raise ValueError("No input levers to deduplicate.")

        logger.info(f"Starting deduplication for {len(input_levers)} levers (single batch call).")

        levers_json = json.dumps([lever.model_dump() for lever in input_levers], indent=2)

        system_prompt = DEDUPLICATE_SYSTEM_PROMPT.strip()

        # Build the single prompt with all levers.
        user_prompt = (
            f"**Project Context:**\n{project_context}\n\n"
            f"**Levers to classify ({len(input_levers)} total):**\n{levers_json}\n\n"
            f"Classify every lever as primary, secondary, or remove."
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

        # Build decisions from the batch result, guarding against duplicate lever_ids.
        decisions: List[LeverDecision] = []
        input_lever_ids = {lever.lever_id for lever in input_levers}
        seen_ids: set[str] = set()

        if batch_result is not None:
            for decision in batch_result.decisions:
                if decision.lever_id not in input_lever_ids:
                    logger.warning(f"LLM returned classification for unknown lever_id: '{decision.lever_id}'. Skipping.")
                    continue
                if decision.lever_id in seen_ids:
                    logger.warning(f"LLM returned duplicate lever_id: '{decision.lever_id}'. Keeping first entry.")
                    continue
                seen_ids.add(decision.lever_id)
                decisions.append(LeverDecision(
                    lever_id=decision.lever_id,
                    classification=decision.classification,
                    justification=decision.justification,
                ))

        # Handle missing decisions — any lever not classified defaults to secondary.
        classified_ids = {d.lever_id for d in decisions}
        for lever in input_levers:
            if lever.lever_id not in classified_ids:
                logger.warning(f"Lever {lever.lever_id}: not classified by LLM. Defaulting to secondary.")
                decisions.append(LeverDecision(
                    lever_id=lever.lever_id,
                    classification="secondary",
                    justification="Not classified by LLM. Keeping as secondary to avoid data loss.",
                ))

        # Build output levers (keep primary + secondary).
        decisions_by_id = {d.lever_id: d for d in decisions}
        output_levers = []
        for lever in input_levers:
            lever_decision = decisions_by_id[lever.lever_id]
            if lever_decision.classification == "remove":
                continue

            deduplication_justification = lever_decision.justification.strip()
            if len(deduplication_justification) == 0:
                deduplication_justification = "Empty explanation. Keeping this lever."

            output_lever = OutputLever(
                **lever.model_dump(),
                classification=lever_decision.classification,
                deduplication_justification=deduplication_justification,
            )
            output_levers.append(output_lever)

        # Minimum lever count warning.
        min_expected = max(3, len(input_levers) // 4)
        if len(output_levers) < min_expected:
            logger.warning(
                f"Only {len(output_levers)} levers survived deduplication "
                f"(expected at least {min_expected} from {len(input_levers)} inputs). "
                f"Downstream steps may receive a degenerate input."
            )

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
