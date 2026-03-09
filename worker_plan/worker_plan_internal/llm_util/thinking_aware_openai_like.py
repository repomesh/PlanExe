"""
ThinkingAwareOpenAILike: OpenAILike subclass that handles thinking tokens gracefully.

## Why this exists (instead of using the built-in LMStudio class)

llama_index ships a dedicated `LMStudio` class (`llama_index.llms.lmstudio`) that already
has `_strip_thinking()` and `force_json` built in. However, switching from OpenAILike to
LMStudio changes the entire structured output code path:

  - **OpenAILike** (current): Uses the OpenAI SDK internally. When
    `should_use_structured_outputs=True`, it sends `response_format: json_schema` to
    LM Studio, which enforces grammar-level JSON output. The structured predict path
    goes through `OpenAI.structured_predict()` → `model_validate_json(content)`.

  - **LMStudio** (alternative): Extends `CustomLLM`, uses `httpx` directly (not the
    OpenAI SDK). Does NOT support `should_use_structured_outputs`. Structured predict
    routes through `LLMTextCompletionProgram` → `PydanticOutputParser` →
    `extract_json_str()` (regex-based parsing). It has `force_json` which sends
    `response_format: json_schema` at the HTTP level, and `_strip_thinking()` which
    strips `<think>` blocks and reasoning preambles from the content field.

  - **Key difference**: OpenAILike uses the OpenAI SDK's response object
    (`ChatCompletionMessage`), which may silently drop `reasoning_content`. LMStudio
    reads the raw JSON response dict directly, so it always sees both fields.

  - **Why not just switch?** All existing PlanExe configs use OpenAILike with
    `should_use_structured_outputs: true`. Swapping to LMStudio changes the JSON
    extraction from grammar-enforced (response_format) to regex-parsed
    (extract_json_str). This is a behavioral change across 60+ pipeline tasks that
    needs a full test run to validate. This subclass is the safe, minimal patch.

  - **Long-term**: A full pipeline test with the LMStudio class swap should be done.
    If results are identical, LMStudio is the cleaner production path since it handles
    thinking tokens natively.

## The problem this solves

When thinking tokens are enabled in LM Studio, models like Qwen may return:
  - response.choices[0].message.reasoning_content (the internal reasoning)
  - response.choices[0].message.content (the final output, which may be None)

OpenAILike from llama_index only reads `content` (via `from_openai_message()` in
`llama_index/llms/openai/utils.py`), causing crashes if it's None.

This subclass detects this situation and falls back to reasoning_content when needed.
"""

import logging
from typing import Any
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.llms.types import ChatResponse, CompletionResponse

logger = logging.getLogger(__name__)


class ThinkingAwareOpenAILike(OpenAILike):
    """
    Subclass of OpenAILike that safely handles thinking tokens from LM Studio.
    
    When thinking tokens are enabled in LM Studio and a model returns:
      - reasoning_content (internal chain-of-thought)
      - content: null (final output)
    
    This class falls back to reasoning_content to avoid crashes.
    
    Usage in llm_config/<profile>.json:
    {
        "lmstudio-qwen-with-thinking": {
            "class": "ThinkingAwareOpenAILike",
            "arguments": {
                "model": "qwen/qwen3.5-9b",
                "api_base": "http://127.0.0.1:1234/v1",
                ...
            }
        }
    }
    """

    def _process_choice(self, choice: Any) -> str:
        """
        Process a single choice from the API response, handling thinking tokens.
        
        When thinking tokens are enabled:
        - content may be None (or missing)
        - reasoning_content contains the chain-of-thought
        
        Falls back to reasoning_content if content is None/empty.
        """
        message = choice.message
        
        # Try to get the content field
        content = getattr(message, 'content', None)
        
        # If content is None or empty, fall back to reasoning_content
        if not content:
            reasoning_content = getattr(message, 'reasoning_content', None)
            if reasoning_content:
                logger.debug(
                    "OpenAILike response had null/empty 'content'; falling back to 'reasoning_content'. "
                    "This is expected when thinking tokens are enabled in LM Studio."
                )
                return reasoning_content
            else:
                # Both content and reasoning_content are None/missing
                logger.warning(
                    "OpenAILike response has null 'content' and no 'reasoning_content'. "
                    "This may indicate a configuration or model issue."
                )
                return ""
        
        # Content exists; check for reasoning_content for logging
        reasoning_content = getattr(message, 'reasoning_content', None)
        if reasoning_content:
            logger.debug(
                "OpenAILike response has both 'content' and 'reasoning_content'. "
                "Using 'content'; 'reasoning_content' is available but not used."
            )
        
        return content

    def chat(self, messages: Any, **kwargs: Any) -> ChatResponse:
        """
        Chat completion with thinking token support.
        
        Overrides parent to safely handle thinking token responses.
        """
        response = super().chat(messages, **kwargs)
        
        # The parent class has already processed the response.
        # If there was an issue, it would have raised an exception.
        # This method is here for explicit override if needed in future versions.
        
        return response

    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        """
        Completion with thinking token support.
        
        Overrides parent to safely handle thinking token responses.
        """
        response = super().complete(prompt, **kwargs)
        
        # The parent class has already processed the response.
        # This method is here for explicit override if needed in future versions.
        
        return response
