"""
Extract and count tokens from LLM provider responses.

Supports multiple provider types including OpenAI, OpenRouter, Ollama, and others.
Extracts input_tokens, output_tokens, and thinking_tokens when available.
"""
import logging
from typing import Optional, Any, Dict
from llama_index.core.llms import ChatResponse

logger = logging.getLogger(__name__)

__all__ = ["TokenCount", "extract_token_count"]

_USAGE_FIELD_NAMES = {
    "prompt_tokens",
    "input_tokens",
    "completion_tokens",
    "output_tokens",
    "reasoning_tokens",
    "thinking_tokens",
    "cache_creation_input_tokens",
    "total_tokens",
    "cost",
    "cost_details",
}


class TokenCount:
    """Container for token count information from an LLM response."""

    def __init__(
        self,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        thinking_tokens: Optional[int] = None,
        raw_usage_data: Optional[Dict[str, Any]] = None,
        upstream_provider: Optional[str] = None,
        upstream_model: Optional[str] = None,
        cost_usd: Optional[float] = None,
    ):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.thinking_tokens = thinking_tokens
        self.raw_usage_data = raw_usage_data or {}
        self.upstream_provider = upstream_provider
        self.upstream_model = upstream_model
        self.cost_usd = cost_usd

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens."""
        return (self.input_tokens or 0) + (self.output_tokens or 0) + (self.thinking_tokens or 0)

    def __repr__(self) -> str:
        return (
            f"TokenCount(input={self.input_tokens}, output={self.output_tokens}, "
            f"thinking={self.thinking_tokens}, total={self.total_tokens})"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "thinking_tokens": self.thinking_tokens,
            "total_tokens": self.total_tokens,
            "raw_usage_data": self.raw_usage_data,
            "upstream_provider": self.upstream_provider,
            "upstream_model": self.upstream_model,
            "cost_usd": self.cost_usd,
        }


def extract_token_count(response: Any) -> TokenCount:
    """
    Extract token counts from an LLM response.

    Handles multiple response types and providers:
    - llama_index ChatResponse (most common)
    - OpenAI usage objects
    - OpenRouter responses
    - Anthropic responses with cache_usage
    - Generic responses with usage attribute

    Args:
        response: The response object from an LLM call.

    Returns:
        TokenCount object with extracted token information.
    """
    if response is None:
        return TokenCount()

    raw_usage_data = {}
    input_tokens = None
    output_tokens = None
    thinking_tokens = None

    try:
        # Handle llama_index ChatResponse
        if isinstance(response, ChatResponse):
            return _extract_from_chat_response(response)

        # Handle raw payloads on response objects (common for OpenRouter/Ollama/OpenAI wrappers).
        raw_payload = getattr(response, "raw", None)
        if isinstance(raw_payload, dict):
            return _extract_from_dict(raw_payload)

        # Handle direct usage object (from some OpenAI-like calls)
        if hasattr(response, "usage"):
            return _extract_from_usage_object(response.usage)

        # Handle dict responses (e.g., from structured output)
        if isinstance(response, dict):
            return _extract_from_dict(response)

        # Fallback: try to extract common attributes
        if hasattr(response, "get"):
            # Dict-like interface
            input_tokens = response.get("input_tokens") or response.get("prompt_tokens")
            output_tokens = response.get("output_tokens") or response.get("completion_tokens")
            thinking_tokens = response.get("thinking_tokens") or response.get("cache_creation_input_tokens")

        logger.debug(f"Extracted token counts from response: input={input_tokens}, output={output_tokens}, thinking={thinking_tokens}")

    except Exception as e:
        logger.warning(f"Error extracting token counts from response: {e}")

    return TokenCount(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        raw_usage_data=raw_usage_data,
    )


def _extract_from_chat_response(response: ChatResponse) -> TokenCount:
    """Extract from llama_index ChatResponse."""
    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    raw_usage_data = {}
    upstream_provider = None
    upstream_model = None
    cost_usd = None

    # Try to get usage from response object
    if hasattr(response, "raw"):
        raw = response.raw
        if isinstance(raw, dict):
            usage = raw.get("usage")
            if isinstance(usage, dict):
                raw_usage_data = usage.copy()
                input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
                output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
                thinking_tokens = usage.get("reasoning_tokens") or usage.get("thinking_tokens")
                cost_usd = _extract_cost_from_usage(usage)
            upstream_provider, upstream_model = _extract_provider_and_model(raw)

    # Also check message for usage info
    if hasattr(response, "message") and hasattr(response.message, "usage"):
        usage = response.message.usage
        if hasattr(usage, "prompt_tokens"):
            input_tokens = input_tokens or usage.prompt_tokens
        if hasattr(usage, "completion_tokens"):
            output_tokens = output_tokens or usage.completion_tokens

    return TokenCount(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        raw_usage_data=raw_usage_data,
        upstream_provider=upstream_provider,
        upstream_model=upstream_model,
        cost_usd=cost_usd,
    )


def _extract_from_usage_object(usage: Any) -> TokenCount:
    """Extract from a usage object (OpenAI style)."""
    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    cost_usd = None
    raw_usage_data = {}

    try:
        if hasattr(usage, "prompt_tokens"):
            input_tokens = usage.prompt_tokens
        if hasattr(usage, "completion_tokens"):
            output_tokens = usage.completion_tokens
        if hasattr(usage, "reasoning_tokens"):
            thinking_tokens = usage.reasoning_tokens
        if hasattr(usage, "cache_creation_input_tokens"):
            # Anthropic cache tokens
            thinking_tokens = thinking_tokens or usage.cache_creation_input_tokens
        if hasattr(usage, "cost"):
            try:
                cost_usd = float(usage.cost)
            except (TypeError, ValueError):
                cost_usd = None

        # Capture raw data
        if hasattr(usage, "__dict__"):
            raw_usage_data = usage.__dict__.copy()
        elif isinstance(usage, dict):
            raw_usage_data = usage.copy()
            cost_usd = cost_usd if cost_usd is not None else _extract_cost_from_usage(usage)

    except Exception as e:
        logger.debug(f"Error extracting from usage object: {e}")

    return TokenCount(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        raw_usage_data=raw_usage_data,
        cost_usd=cost_usd,
    )


def _extract_from_dict(response: dict) -> TokenCount:
    """Extract from a dictionary response."""
    input_tokens = None
    output_tokens = None
    thinking_tokens = None
    upstream_provider, upstream_model = _extract_provider_and_model(response)
    cost_usd = None

    # Check for usage key
    usage = response.get("usage")
    if isinstance(usage, dict):
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        thinking_tokens = usage.get("reasoning_tokens") or usage.get("thinking_tokens")
        cost_usd = _extract_cost_from_usage(usage)
        return TokenCount(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            raw_usage_data=_build_usage_snapshot(usage, upstream_provider, upstream_model),
            upstream_provider=upstream_provider,
            upstream_model=upstream_model,
            cost_usd=cost_usd,
        )

    # Direct keys
    input_tokens = response.get("prompt_tokens") or response.get("input_tokens")
    output_tokens = response.get("completion_tokens") or response.get("output_tokens")
    thinking_tokens = response.get("reasoning_tokens") or response.get("thinking_tokens")

    return TokenCount(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        # Keep raw_usage_data usage-focused even when token fields are top-level.
        raw_usage_data=_build_usage_snapshot(
            _extract_usage_like_fields(response) if input_tokens or output_tokens or thinking_tokens else {},
            upstream_provider,
            upstream_model,
        ),
        upstream_provider=upstream_provider,
        upstream_model=upstream_model,
        cost_usd=cost_usd if cost_usd is not None else _extract_cost_from_usage(response),
    )


def _extract_usage_like_fields(response: dict) -> dict:
    """Extract only usage-like keys from a top-level response dict."""
    if not isinstance(response, dict):
        return {}
    return {key: value for key, value in response.items() if key in _USAGE_FIELD_NAMES}


def _build_usage_snapshot(usage: dict, provider: Optional[str], model: Optional[str]) -> dict:
    # Keep raw_usage_data usage-focused. Provider/model are captured in dedicated fields.
    _ = provider, model
    return usage.copy() if isinstance(usage, dict) else {}


def _extract_provider_and_model(payload: dict) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(payload, dict):
        return None, None

    provider = payload.get("provider") or payload.get("provider_name")
    model = payload.get("model") or payload.get("model_name") or payload.get("model_id")

    if isinstance(provider, dict):
        provider = provider.get("name") or provider.get("id")

    # Common nested locations in provider SDK responses.
    if (not provider or not model) and isinstance(payload.get("response"), dict):
        response_dict = payload["response"]
        provider = provider or response_dict.get("provider") or response_dict.get("provider_name")
        model = model or response_dict.get("model") or response_dict.get("model_name") or response_dict.get("model_id")
        if isinstance(provider, dict):
            provider = provider.get("name") or provider.get("id")

    if (not provider or not model) and isinstance(payload.get("raw"), dict):
        raw_dict = payload["raw"]
        provider = provider or raw_dict.get("provider") or raw_dict.get("provider_name")
        model = model or raw_dict.get("model") or raw_dict.get("model_name") or raw_dict.get("model_id")
        if isinstance(provider, dict):
            provider = provider.get("name") or provider.get("id")

    return str(provider) if provider else None, str(model) if model else None


def _extract_cost_from_usage(payload: Any) -> Optional[float]:
    if not isinstance(payload, dict):
        return None

    cost = payload.get("cost")
    if cost is None and isinstance(payload.get("cost_details"), dict):
        details = payload.get("cost_details") or {}
        cost = details.get("upstream_inference_cost")
        if cost is None:
            cost = details.get("total_cost")

    try:
        return float(cost) if cost is not None else None
    except (TypeError, ValueError):
        return None
