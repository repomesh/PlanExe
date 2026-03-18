"""
ResponsesAPILLM: llama_index LLM class that calls /v1/responses (OpenAI Responses API).

Works with:
- Direct OpenAI: base_url="https://api.openai.com"
- OpenRouter:    base_url="https://openrouter.ai/api"

Key differences from Chat Completions:
- Uses `input` param (not `messages`)
- Uses `text.format` for structured output (not `response_format`)
- Output is in `output[N].content[0].text` (not `choices[0].message.content`)
- Token fields: `input_tokens` / `output_tokens` (not prompt_tokens / completion_tokens)

Usage in llm_config/<profile>.json:
    {
        "class": "ResponsesAPILLM",
        "arguments": {
            "model": "openai/gpt-5.4-nano",
            "api_key": "${OPENROUTER_API_KEY}",
            "base_url": "https://openrouter.ai/api",
            "temperature": 1,
            "timeout": 120.0,
            "max_output_tokens": 16384,
            "reasoning_effort": "low"
        }
    }

PROMPT> python -m worker_plan_internal.llm_util.responses_api_llm
"""
import json
import logging
from typing import Any, Dict, Generator, Iterator, Optional, Sequence, Type

import httpx
from pydantic import Field

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.llms.callbacks import llm_chat_callback, llm_completion_callback
from llama_index.core.llms.llm import LLM
from llama_index.core.prompts import PromptTemplate
from llama_index.core.types import Model

logger = logging.getLogger(__name__)


def _patch_schema_for_strict(schema: dict) -> dict:
    """
    Recursively ensure every object in the schema has additionalProperties: false.
    Required for strict mode in the Responses API.
    """
    schema = dict(schema)
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
        if "properties" in schema:
            schema["properties"] = {
                k: _patch_schema_for_strict(v)
                for k, v in schema["properties"].items()
            }
    if "items" in schema:
        schema["items"] = _patch_schema_for_strict(schema["items"])
    if "$defs" in schema:
        schema["$defs"] = {
            k: _patch_schema_for_strict(v)
            for k, v in schema["$defs"].items()
        }
    return schema


def _extract_text(data: dict) -> str:
    """Extract text from a Responses API response dict."""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content["text"]
    raise ValueError(f"Could not extract text from Responses API response: {data}")


def _messages_to_input(messages: Sequence[ChatMessage]) -> list:
    """Convert llama_index ChatMessage list to Responses API input array."""
    result = []
    for msg in messages:
        role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        result.append({"role": role, "content": msg.content or ""})
    return result


class ResponsesAPILLM(LLM):
    """
    LLM implementation that uses the OpenAI Responses API (/v1/responses).

    Supports direct OpenAI and OpenRouter. For structured output, uses
    text.format.json_schema with strict:true (not response_format).
    """

    model: str = Field(description="Model name, e.g. 'openai/gpt-5.4-nano'")
    api_key: str = Field(description="API key (OpenAI or OpenRouter)")
    base_url: str = Field(
        default="https://api.openai.com",
        description="Base URL. For OpenRouter use 'https://openrouter.ai/api'",
    )
    temperature: float = Field(default=1.0, description="Sampling temperature")
    timeout: float = Field(default=120.0, description="HTTP timeout in seconds")
    max_output_tokens: int = Field(default=16384, description="Max output tokens")
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="Reasoning effort: 'low', 'medium', 'high'. None = disabled.",
    )
    additional_kwargs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra arguments passed to httpx (e.g. extra headers)",
    )

    @classmethod
    def class_name(cls) -> str:
        return "ResponsesAPILLM"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=128000,
            num_output=self.max_output_tokens,
            is_chat_model=True,
            model_name=self.model,
        )

    def _build_headers(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Support extra_headers passed via additional_kwargs
        extra = self.additional_kwargs.get("extra_headers", {})
        headers.update(extra)
        return headers

    def _build_payload(self, input_: Any) -> dict:
        payload: dict = {
            "model": self.model,
            "input": input_,
            "store": False,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        return payload

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/v1/responses"

    def _call_api(self, payload: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                self._endpoint(),
                headers=self._build_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def _acall_api(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._endpoint(),
                headers=self._build_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # complete / stream_complete
    # ------------------------------------------------------------------

    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        payload = self._build_payload(prompt)
        data = self._call_api(payload)
        text = _extract_text(data)
        usage = data.get("usage", {})
        return CompletionResponse(
            text=text,
            raw=data,
            additional_kwargs={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        )

    @llm_completion_callback()
    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseGen:
        # Non-streaming fallback: call complete() and yield the single result
        response = self.complete(prompt, formatted=formatted, **kwargs)
        yield response

    # ------------------------------------------------------------------
    # chat / stream_chat
    # ------------------------------------------------------------------

    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        input_ = _messages_to_input(messages)
        payload = self._build_payload(input_)
        data = self._call_api(payload)
        text = _extract_text(data)
        usage = data.get("usage", {})
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=text),
            raw=data,
            additional_kwargs={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        )

    @llm_chat_callback()
    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        # Non-streaming fallback
        response = self.chat(messages, **kwargs)
        yield response

    # ------------------------------------------------------------------
    # async variants
    # ------------------------------------------------------------------

    @llm_completion_callback()
    async def acomplete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        payload = self._build_payload(prompt)
        data = await self._acall_api(payload)
        text = _extract_text(data)
        usage = data.get("usage", {})
        return CompletionResponse(
            text=text,
            raw=data,
            additional_kwargs={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        )

    @llm_completion_callback()
    async def astream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseAsyncGen:
        response = await self.acomplete(prompt, formatted=formatted, **kwargs)
        async def _gen():
            yield response
        return _gen()

    @llm_chat_callback()
    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        input_ = _messages_to_input(messages)
        payload = self._build_payload(input_)
        data = await self._acall_api(payload)
        text = _extract_text(data)
        usage = data.get("usage", {})
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=text),
            raw=data,
            additional_kwargs={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        )

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseAsyncGen:
        response = await self.achat(messages, **kwargs)
        async def _gen():
            yield response
        return _gen()

    # ------------------------------------------------------------------
    # structured_predict — uses text.format.json_schema (Responses API native)
    # ------------------------------------------------------------------

    def structured_predict(
        self,
        output_cls: Type[Model],
        prompt: PromptTemplate,
        llm_kwargs: Optional[Dict[str, Any]] = None,
        **prompt_args: Any,
    ) -> Model:
        """
        Structured prediction using Responses API text.format.json_schema.

        This is the correct path for Responses API — NOT response_format.
        Auto-patches schema to add additionalProperties:false for strict mode.
        """
        messages = list(prompt.format_messages(**prompt_args))
        input_ = _messages_to_input(messages)

        raw_schema = output_cls.model_json_schema()
        patched_schema = _patch_schema_for_strict(raw_schema)

        # Sanitize schema name: only [A-Za-z0-9_-] allowed
        schema_name = output_cls.__name__.replace(" ", "_")

        payload = self._build_payload(input_)
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": patched_schema,
            }
        }

        data = self._call_api(payload)
        text = _extract_text(data)

        try:
            return output_cls.model_validate_json(text)
        except Exception as e:
            logger.warning(
                "ResponsesAPILLM.structured_predict: model_validate_json failed (%s), "
                "trying json.loads + model_validate...",
                e,
            )
            parsed = json.loads(text)
            return output_cls.model_validate(parsed)

    async def astructured_predict(
        self,
        output_cls: Type[Model],
        prompt: PromptTemplate,
        llm_kwargs: Optional[Dict[str, Any]] = None,
        **prompt_args: Any,
    ) -> Model:
        messages = list(prompt.format_messages(**prompt_args))
        input_ = _messages_to_input(messages)

        raw_schema = output_cls.model_json_schema()
        patched_schema = _patch_schema_for_strict(raw_schema)
        schema_name = output_cls.__name__.replace(" ", "_")

        payload = self._build_payload(input_)
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": patched_schema,
            }
        }

        data = await self._acall_api(payload)
        text = _extract_text(data)

        try:
            return output_cls.model_validate_json(text)
        except Exception as e:
            logger.warning(
                "ResponsesAPILLM.astructured_predict: model_validate_json failed (%s), "
                "trying json.loads + model_validate...",
                e,
            )
            parsed = json.loads(text)
            return output_cls.model_validate(parsed)


if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO)

    llm = ResponsesAPILLM(
        model="openai/gpt-5.4-nano",
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api",
        timeout=30.0,
        max_output_tokens=200,
    )
    result = llm.complete("What is 2+2? Reply with just the number.")
    print(f"Result: {result.text}")
    print("SUCCESS")
