# Presets

LM Studio preset files that configure local models for use with PlanExe.

## What are LM Studio presets?

LM Studio presets are JSON configs that tune model parameters (temperature, context length, max tokens, system prompt, thinking mode, etc.) for a specific use case. They can be published to the LM Studio Hub so users can apply them with one click.

## lmstudio-planexe.json

Optimizes any local LM Studio model for PlanExe's structured JSON pipeline:

- **Temperature 0.2** — deterministic, schema-compliant output.
- **Context window 32768 / max tokens 4096** — avoids llama_index's low defaults that silently truncate prompts.
- **System prompt** — instructs the model to return only valid JSON matching the requested schema, with no markdown fences or filler.
- **Thinking disabled** — turns off thinking/reasoning mode for models that support it (e.g. Qwen 3, GLM-4), since PlanExe needs raw JSON, not chain-of-thought.

This preset complements the `llm_config/local.json` config, which tells PlanExe *how to call* LM Studio (via `OpenAILike` with `should_use_structured_outputs: true` for grammar-enforced JSON). The preset tells LM Studio *how to run* the model.
