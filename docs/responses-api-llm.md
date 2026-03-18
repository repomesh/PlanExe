# ResponsesAPILLM — Design & Maintenance Guide

**File:** `worker_plan/worker_plan_internal/llm_util/responses_api_llm.py`  
**Added:** 2026-03-18  
**PR:** #347  

---

## Why This Exists

OpenAI's Responses API (`/v1/responses`) is a separate endpoint from Chat Completions (`/v1/chat/completions`). It's the required or preferred API for:

- **GPT-5 family** — gpt-5-nano, gpt-5.4-nano, gpt-5.4-mini, gpt-5.4, gpt-5.4-pro
- **Reasoning models** — o3, o4-mini (reasoning effort control)
- **Structured output** — uses `text.format.json_schema` instead of `response_format`

The Responses API differs from Chat Completions in request format, response structure, and how structured output is specified. `ResponsesAPILLM` adapts PlanExe's llama_index-based pipeline to call this endpoint without modifying any existing code paths.

### What it replaces (nothing)

This class is **additive**. All existing LLM classes (`OpenRouter`, `OpenAI`, `Anthropic`, `OpenAILike`, `LMStudio`, `ThinkingAwareOpenAILike`, `StructuredOutputOpenRouter`) continue to work unchanged. `ResponsesAPILLM` is a new option you select via `"class": "ResponsesAPILLM"` in your llm_config JSON.

---

## How It Works

### Request translation

llama_index calls `chat()` or `structured_predict()` with `ChatMessage` objects. `ResponsesAPILLM` translates these to the Responses API format:

| llama_index concept | Responses API equivalent |
|---|---|
| `ChatMessage` list → `messages` param | `input` array of `{role, content}` dicts |
| `response_format` with `json_schema` | `text.format` with `json_schema` |
| `choices[0].message.content` | `output[N].content[0].text` where `type == "output_text"` |
| `usage.prompt_tokens` | `usage.input_tokens` |
| `usage.completion_tokens` | `usage.output_tokens` |

### Schema patching for strict mode

The Responses API with `strict: true` requires every object in the JSON schema to have `additionalProperties: false`. Pydantic-generated schemas don't include this by default.

`_patch_schema_for_strict()` recursively walks the schema and adds `additionalProperties: false` to every object type, including nested objects, array items, and `$defs` references.

### HTTP layer

Uses `httpx` directly (not the OpenAI Python SDK, not llama_index's internal HTTP client). This gives full control over the request format without fighting abstraction layers that assume Chat Completions.

---

## Configuration

In any `llm_config/<profile>.json`:

```json
{
    "my-gpt5-model": {
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
}
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `model` | str | required | Model name (OpenRouter format: `openai/gpt-5.4-nano`) |
| `api_key` | str | required | API key (supports `${ENV_VAR}` syntax via llm_config loader) |
| `base_url` | str | `https://api.openai.com` | API base. Use `https://openrouter.ai/api` for OpenRouter |
| `temperature` | float | 1.0 | Sampling temperature |
| `timeout` | float | 120.0 | HTTP timeout in seconds |
| `max_output_tokens` | int | 16384 | Maximum output tokens |
| `reasoning_effort` | str/None | None | `"none"`, `"low"`, `"medium"`, `"high"`, or `None` to omit |
| `additional_kwargs` | dict | `{}` | Extra kwargs — supports `extra_headers` for OpenRouter app info |

### Where `base_url` points

- Direct OpenAI: `https://api.openai.com` → endpoint becomes `https://api.openai.com/v1/responses`
- OpenRouter: `https://openrouter.ai/api` → endpoint becomes `https://openrouter.ai/api/v1/responses`

---

## Fragile Points & Known Risks

### 1. Schema patching may miss edge cases

`_patch_schema_for_strict()` handles `properties`, `items`, and `$defs` recursion. It does **not** currently handle:
- `anyOf` / `oneOf` / `allOf` combinators (Pydantic uses these for `Optional` fields and union types)
- `prefixItems` (tuple types)

**Impact:** If a Pydantic output model uses `Optional[SomeModel]` or `Union[A, B]`, the generated schema will contain `anyOf` blocks. The patching won't recurse into those, and the Responses API may reject the schema in strict mode.

**Mitigation:** Test any new Pydantic output model that uses Optional/Union fields. If it fails, extend `_patch_schema_for_strict()` to walk `anyOf`/`oneOf`/`allOf` arrays.

### 2. Streaming is not implemented (non-streaming fallback)

`stream_chat()` and `stream_complete()` call the non-streaming variants and yield a single result. This is functionally correct but means:
- No token-by-token output for progress tracking
- No early reasoning capture from SSE events
- Higher perceived latency on long responses

**When to fix:** If PlanExe adds real-time progress UI, or if response chaining (Phase 2) requires capturing `response.id` from early stream events.

### 3. `store: false` means no response chaining

All requests currently set `store: false`. This means `previous_response_id` cannot be used for multi-turn reasoning chain caching. This is intentional for Phase 1.

**Phase 2 work:** Add `store` as a configurable parameter. Thread `response.id` from each call back through `llm_executor.py` so sequential tasks in the same chain can pass `previous_response_id`. This would benefit GovernancePhase1→6 and ExpertReview rounds.

### 4. OpenRouter Responses API is in beta

As of March 2026, OpenRouter's `/api/v1/responses` endpoint is documented as beta. Breaking changes are possible.

**Mitigation:** Keep Chat Completions classes as the default fallback. Only use `ResponsesAPILLM` when you specifically need Responses API features (GPT-5 family, reasoning effort control).

### 5. `structured_predict()` bypasses llama_index's `as_structured_llm()`

llama_index's default `structured_predict()` path goes through `as_structured_llm()` → Chat Completions with `response_format`. Our override intercepts before that and calls the Responses API directly.

**Risk:** If llama_index changes the `structured_predict()` signature or adds required return metadata, the override may need updating.

**Mitigation:** Pin llama_index version in requirements. Test after any llama_index upgrade.

### 6. Error messages from Responses API differ from Chat Completions

The Responses API returns errors in a different format. `httpx.raise_for_status()` will catch HTTP errors, but application-level errors (e.g., `status: "failed"` in the response body with HTTP 200) are not currently checked.

**When to fix:** If you see silent failures where the response status is `"failed"` or `"incomplete"` but no exception is raised.

---

## Maintenance Checklist

When modifying this file:

1. **Test with a real API call** — don't trust unit tests alone. The Responses API format is not in most LLM testing mocks.
2. **Test `structured_predict()`** — use a Pydantic model with nested objects to verify schema patching works.
3. **Check `_extract_text()`** — if OpenAI changes the output array structure, this is the first thing to break.
4. **Don't add Chat Completions fallback** — this class is intentionally Responses-API-only. If you need Chat Completions, use the existing `OpenRouter` or `OpenAI` classes.

### Quick smoke test

```bash
cd /path/to/PlanExe
source .venv/bin/activate
python3 -c "
import os
from worker_plan_internal.llm_util.responses_api_llm import ResponsesAPILLM
llm = ResponsesAPILLM(
    model='openai/gpt-5.4-nano',
    api_key=os.environ['OPENROUTER_API_KEY'],
    base_url='https://openrouter.ai/api',
    timeout=30.0,
    max_output_tokens=200,
)
result = llm.complete('What is 2+2? Reply with just the number.')
print(f'Result: {result.text}')
"
```

Expected: `Result: 4` (or similar short number answer).

---

## Future Work (Phase 2)

1. **Response chaining** — `previous_response_id` support for sequential task chains
2. **Streaming** — real SSE streaming for progress tracking
3. **Reasoning capture** — extract and store `reasoning_tokens` and reasoning summaries
4. **`anyOf`/`oneOf` schema patching** — handle Optional/Union Pydantic fields in strict mode
5. **Response status checking** — detect `status: "failed"` / `"incomplete"` in response body
