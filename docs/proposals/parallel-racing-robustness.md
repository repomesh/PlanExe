<!-- Author: Claude Sonnet 4.6 (Bubba) | Date: 27-March-2026 -->
# Proposal: Parallel Model Racing for Pipeline Robustness

**Date:** 27-March-2026  
**Authors:** Bubba (Claude Sonnet 4.6) + Egon  
**Status:** For Simon's review

---

## Background

PlanExe is used as a **diagnostic instrument** — the quality and completeness of the decomposition document is the measurement. When the pipeline stalls because a model produces incomplete output or refuses a task, the instrument fails to give a reading.

During research on 27-March-2026, we evaluated [G0DM0D3](https://github.com/VoynichLabs/G0DM0D3) (elder-plinius), which consistently produces complete decomposition outputs on inputs that break PlanExe. The key mechanism: **parallel model racing**.

---

## The Key Finding

In `redline_gate.py`, Simon has already noted:

```
# IDEA: ensemble. multiple perspectives of the same prompt using 3 or 5 system prompts.
```

G0DM0D3 is an implementation of this idea. It sends the same prompt to 5–51 models in parallel, scores each response on a composite metric, and returns the highest-scoring result.

In a live test, Claude-3.5-sonnet **failed** (3.9s timeout) and Claude-sonnet-4 **refused** (13.1s). The system automatically routed to `llama-3.1-8b-instruct`, which answered the question. PlanExe on the same input would have returned nothing.

---

## The Architecture Gap

PlanExe already has the infrastructure:
- `llm_config/` has 10+ model definitions (Gemini Flash, Qwen3, GPT-5-nano, Kimi-k2.5, etc.)
- `LLMExecutor` has a sequential `llm_models` fallback list (tries next on error)
- `luigi_workers` controls per-model parallelism

What's missing: **task-level parallel racing**. Currently the model is selected once per run. The fallback is sequential (only triggers on error, not quality). G0DM0D3 races models simultaneously and selects the best output.

---

## Three Options for Simon's Consideration

### Option A: Quality-Threshold Fallback (Low complexity)
If a task output falls below a minimum quality threshold (response too short, high refusal signal), retry with the next model in a priority list. Extends existing `LLMExecutor` fallback.

**What it reveals:** Which models fail on which task types.

### Option B: Parallel Task Execution (Medium complexity)
Run each Luigi task against 2–3 models simultaneously. Score outputs, keep the best. Closest to G0DM0D3's approach. `luigi_workers` and OpenRouter routing suggest this is architecturally feasible.

**What it reveals:** Quality ceiling for each task when unconstrained by model choice.

### Option C: Prompt Variant Racing (Low cost)
Same model, multiple system prompt framings per task, keep highest-quality output. No additional API costs for different models — just varied prompts.

**What it reveals:** How much failure is prompt-sensitive vs. model-architecture-sensitive.

---

## `RedlineGateTask` — Highest Priority Target

The `RedlineGateTask` runs first. One model, one system prompt (SYSTEM_PROMPT_25 by default), one verdict. If it REFUSEs, the entire pipeline stops before it starts. This is the single most impactful place to implement ensemble/racing.

Applying Option A or B at `RedlineGateTask` specifically — with 3 prompt variants or 3 model choices — would address the most common complete pipeline failures with minimal changes elsewhere.

---

## Reference

- G0DM0D3 source (VoynichLabs fork): https://github.com/VoynichLabs/G0DM0D3
- ULTRAPLINIAN scoring: `S_completeness = length(25) + structure(20) + anti_refusal(25) + directness(15) + relevance(15)`
- Existing PlanExe model configs: `llm_config/baseline.json`, `frontier.json`, `premium.json`
