---
title: Costs and models
---

# Costs and models

PlanExe makes many LLM calls per plan. Model choice affects cost, speed, and quality.

---

## Guidance

- **Most reliable**: paid cloud models via OpenRouter.
- **Lowest cost**: older, smaller models (quality can drop).
- **Local models**: require strong hardware and are slower.
- **Speed matters**: tokens per second can be the difference between minutes and hours.

---

## Typical costs

Costs vary by model and prompt size. PlanExe can use 100+ calls per plan, so avoid expensive models unless you need the highest quality.

## Billing policy (hosted PlanExe)

- PlanExe charges a **1 USD platform fee** when a plan completes successfully.
- If PlanExe is unable to complete plan creation, the **1 USD platform fee is not charged**.
- The account must have sufficient balance to start creating a plan.
- If the account has less than **2 USD**, plan creation is likely to fail before starting.
- If a very expensive model is selected, the account may need higher upfront balance.
- If an account runs out of funds during processing, the plan can be resumed after topping up the balance.

## Self-hosted cost model

In self-hosted deployments, there is no platform fee paid to PlanExe.

- You run PlanExe on your own environment (local machine, private server, or your own cloud account).
- Cost shifts to your chosen model runtime:
  - pay-per-token providers such as OpenRouter (or other compatible hosted APIs)
  - local inference on your own hardware (GPU/CPU, power, and maintenance costs)
- If you use local models, you avoid provider token billing but may need significant hardware investment for speed and quality.
- If you use hosted model APIs from self-hosted PlanExe, provider charges still apply based on token usage.

## Speed and iteration

Fast models can complete a plan in roughly 10–20 minutes. Slow models may take hours. In practice, it is often better to iterate quickly and generate several candidate plans than to wait for one slow run.

---

## Choosing a provider

- **OpenRouter**: easiest path for most users.
- **Ollama / LM Studio**: good for local experimentation.

See the provider guides:
- [OpenRouter](ai_providers/openrouter.md)
- [Ollama](ai_providers/ollama.md)
- [LM Studio](ai_providers/lm_studio.md)
