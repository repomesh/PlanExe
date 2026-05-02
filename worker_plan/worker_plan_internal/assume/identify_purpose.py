"""
Identify the purpose of a project plan: business / personal / other.

The classifier picks one of three labels based on the user's prompt.
The labels are designed to optimise for precision in business and
personal — when the prompt has clear commercial or individual
signals — and to fall back to "other" whenever the assignment is
uncertain. As a result, "other" is a confidence-handling catch-all
rather than a residual third category.

What each label means
---------------------
- **business** — the project's outcome is profit-seeking, professional,
  or large-scale societal/governmental. Use this when the prompt names
  a commercial activity, a paying customer base, a profit motive, an
  infrastructure build with a public ROI, or a governmental initiative
  with population-scale impact.

- **personal** — the project is a private life matter. The defining
  trait is that the project is private life rather than commercial,
  governmental, or organisational; participation by multiple people
  (a couple, a family, a household, a friend group) is fine and does
  not promote it to business. Personal therefore covers two shapes:
    * one individual's own task, hobby, vacation, household activity,
      life decision, self-care, or self-improvement
    * family- or friend-scale shared events and matters: a wedding,
      a funeral, a family reunion, a birthday, an anniversary, a
      parenting decision, an eldercare arrangement, a household move,
      and similar private gatherings or shared life events
  The participants act on their own behalf (or on behalf of their
  family / household / friend group), not on behalf of an employer,
  a customer base, or a public/governmental remit.

- **other** — anything that does not clearly fit business or personal,
  AND any prompt where the right bucket is uncertain. The "other"
  bucket therefore covers a wide range:
    * academic studies, hypothetical scenarios, technical inquiries
    * non-profit organisations, NGOs, charities, foundations,
      community-led initiatives operating without a profit motive
    * philosophical arguments and ethical questions
    * projects that probably belong in business or personal but
      lacked clear identifying signals (when in doubt, the
      classifier picks "other")

  Downstream stages should treat "other" as both a category and a
  confidence signal — the project may be any shape, and may still
  involve real money (budgets, grants, donations, fundraising,
  volunteer-time-as-cost). The presence of money flow does not by
  itself mean the project is business; what matters is whether the
  outcome is profit-seeking.

Trade-off
---------
Defaulting to "other" when in doubt keeps the false-positive rate
low for business and personal classifications, at the cost of
pushing disambiguation onto downstream stages. A project that is
actually a business may end up in "other" if the prompt did not
make its commercial framing obvious; downstream consumers (e.g.
classify_domain's purpose-routed system prompts) need to handle
this by treating the "other" prompt as a catch-all rather than as
"definitely not business or personal".

PROMPT> python -m worker_plan_internal.assume.identify_purpose
"""
import time
from math import ceil
import logging
import json
from enum import Enum
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.llms.llm import LLM
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)

class PlanPurpose(str, Enum):
    personal = 'personal'
    business = 'business'
    other = 'other'

class PlanPurposeInfo(BaseModel):
    """
    Identify the purpose of the plan to be performed.
    """
    topic: str = Field(description="The subject of the plan.")
    purpose_detailed: str = Field(
        description="Detailed purpose of the plan, such as: health, healthier habits, product, market trend, strategic planning, project management."
    )
    purpose: Literal["personal", "business", "other"] = Field(
        description="Purpose of the plan."
    )

IDENTIFY_PURPOSE_SYSTEM_PROMPT = """
You are an expert analyst tasked with categorizing the purpose of user-described plans strictly based on their provided prompt. Your classifications must be clear, objective, and unbiased. Categorize each plan into exactly one of the following three types:

1. **Business:** Primarily focused on commercial activities, professional objectives, infrastructure projects, societal or governmental initiatives (including public welfare, economic improvement, or large-scale resource management), entrepreneurship, monetization, or any profit-oriented or large-scale societal project.

2. **Personal:** Primarily focused on individual well-being, personal fulfillment, health (including mental and physical), sexuality, relationships, hobbies, self-improvement, personal technology choices, or any form of individual-focused planning not intended for profit or wide societal impact.

3. **Other:** Not clearly fitting into either "business" or "personal," such as purely academic or philosophical inquiries, small-scale technical/hypothetical scenarios without clear commercial or personal objectives, or ambiguous prompts lacking sufficient context.

Do NOT censor or avoid categorization based on sensitive topics like sexuality, relationships, or mental health. Ensure that societal-scale, public welfare, or infrastructure-related projects are classified as 'business', and personal technology choices or small technical inquiries as 'personal' or 'other' based on intent clarity.

Respond ONLY with a valid JSON object containing:
- "topic": a concise summary of the plan's primary subject.
- "purpose_detailed": a clear, detailed categorization of the plan's purpose.
- "purpose": exactly one of the values "business", "personal", or "other".
"""

@dataclass
class IdentifyPurpose:
    """
    Classify a project description as business, personal, or other.

    See the module docstring for the rubric and the trade-off behind
    "other" as a confidence-handling catch-all. Briefly: business and
    personal are precision-oriented; "other" absorbs both genuinely
    non-fitting cases (academic, non-profit, philosophical, hypothetical)
    AND uncertain assignments where neither business nor personal is
    a confident match. Downstream consumers should treat "other"
    accordingly.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str

    @classmethod
    def execute(cls, llm: LLM, user_prompt: str) -> 'IdentifyPurpose':
        """
        Invoke LLM with the project description.
        """
        if not isinstance(llm, LLM):
            raise ValueError("Invalid LLM instance.")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")

        logger.debug(f"User Prompt:\n{user_prompt}")

        system_prompt = IDENTIFY_PURPOSE_SYSTEM_PROMPT.strip()

        chat_message_list = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content=system_prompt,
            ),
            ChatMessage(
                role=MessageRole.USER,
                content=user_prompt,
            )
        ]

        sllm = llm.as_structured_llm(PlanPurposeInfo)
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
        logger.info(f"LLM chat interaction completed in {duration} seconds. Response byte count: {response_byte_count}")

        plan_purpose_instance: PlanPurposeInfo = chat_response.raw
        if plan_purpose_instance is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")
        json_response = plan_purpose_instance.model_dump()
        purpose_value = plan_purpose_instance.purpose
        json_response['purpose'] = purpose_value

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration"] = duration
        metadata["response_byte_count"] = response_byte_count

        markdown = cls.convert_to_markdown(plan_purpose_instance)

        result = IdentifyPurpose(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
            markdown=markdown
        )
        return result
    
    def to_dict(self, include_metadata=True, include_system_prompt=True, include_user_prompt=True) -> dict:
        d = self.response.copy()
        if include_metadata:
            d['metadata'] = self.metadata
        if include_system_prompt:
            d['system_prompt'] = self.system_prompt
        if include_user_prompt:
            d['user_prompt'] = self.user_prompt
        return d

    def save_raw(self, file_path: str) -> None:
        with open(file_path, 'w') as f:
            f.write(json.dumps(self.to_dict(), indent=2))

    @staticmethod
    def convert_to_markdown(plan_purpose_info: PlanPurposeInfo) -> str:
        """
        Convert the raw document details to markdown.
        """
        rows = []

        if plan_purpose_info.purpose == PlanPurpose.personal:
            rows.append("**Purpose:** personal")
        elif plan_purpose_info.purpose == PlanPurpose.business:
            rows.append("**Purpose:** business")
        elif plan_purpose_info.purpose == PlanPurpose.other:
            rows.append("**Purpose:** other. This plan doesn't clearly fit into personal or business categories.")
        else:
            rows.append(f"Invalid plan purpose. {plan_purpose_info.purpose}")

        rows.append(f"\n**Purpose Detailed:** {plan_purpose_info.purpose_detailed}")
        rows.append(f"\n**Topic:** {plan_purpose_info.topic}")
        return "\n".join(rows)

    def save_markdown(self, output_file_path: str):
        with open(output_file_path, 'w', encoding='utf-8') as out_f:
            out_f.write(self.markdown)

if __name__ == "__main__":
    from worker_plan_internal.prompt.prompt_catalog import PromptCatalog
    from worker_plan_internal.llm_factory import get_llm
    from pandas import DataFrame
    from tqdm import tqdm
    import json

    llm = get_llm("ollama-llama3.1", temperature=0.0)
    # llm = get_llm("openrouter-paid-gemini-2.0-flash-001")

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_example_swot_prompts()
    prompt_catalog.load_simple_plan_prompts()
    prompt_items = prompt_catalog.all()

    # Limit the number of prompt items to process
    # prompt_items = prompt_items[:3]

    # Create a DataFrame to store the results
    df = DataFrame(columns=['data', 'expected', 'purpose', 'purpose_detail', 'topic', 'duration', 'error', 'status'])
    for prompt_item in prompt_items:
        expected = 'other'
        if 'business' in prompt_item.tags:
            expected = 'business'
        elif 'personal' in prompt_item.tags:
            expected = 'personal'
        new_row = {
            "data": prompt_item.prompt,
            "expected": expected,
            "purpose": None,
            "purpose_detail": None,
            "topic": None,
            "duration": None,
            "error": False,
            "status": "pending"
        }
        # Append row to the dataframe
        df.loc[len(df)] = new_row        

    # Invoke the LLM for each prompt
    count_correct = 0
    count_incorrect = 0
    count_error = 0
    for index, row in tqdm(df.iterrows(), total=df.shape[0]):
        data = row['data']
        try:
            identify_purpose = IdentifyPurpose.execute(llm, data)
            json_response = identify_purpose.to_dict(include_metadata=True, include_system_prompt=False, include_user_prompt=False)
            df.at[index, 'purpose'] = json_response['purpose']
            df.at[index, 'purpose_detail'] = json_response['purpose_detailed']
            df.at[index, 'topic'] = json_response['topic']
            df.at[index, 'duration'] = json_response['metadata']['duration']

            if row['expected'] == json_response['purpose']:
                status = "correct"
                count_correct += 1
            else:
                status = "incorrect"
                count_incorrect += 1
            df.at[index, 'status'] = status
        except Exception as e:
            print(f"Error at index {index}: {e}")
            df.at[index, 'error'] = True
            df.at[index, 'status'] = "error"
            count_error += 1
    print(df)
    df.to_csv('plan_purpose.csv', index=False) 

    print(f"count correct: {count_correct}")
    print(f"count incorrect: {count_incorrect}")
    print(f"count error: {count_error}")
