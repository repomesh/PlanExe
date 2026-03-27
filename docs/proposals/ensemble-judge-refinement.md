# Proposal: Ensemble + Judge-Refinement Loop for Early Pipeline Tasks

**Author:** Egon (HejEgonBot)
**Date:** 2026-03-27
**Status:** Draft — for Simon's review

---

## Problem

Early pipeline tasks (particularly `PremiseAttackTask` and `RedlineGateTask`) run a single model with a single system prompt. The quality of these early outputs determines everything downstream — a weak premise attack or incorrect redline verdict propagates through the entire plan.

The current sequential fallback in `LLMExecutor` (try model A, on failure try model B) only handles errors, not quality. There's no mechanism to evaluate whether a successful response was actually good, or to improve it.

---

## Proposed Design: Three-Stage Judge-Refinement Loop

### Stage 1: Parallel Candidate Generation
Run N non-reasoning models simultaneously on the same task.

- Each model produces a full response independently
- Models are cheap and fast — running 3–5 in parallel costs little more than running 1
- Implemented via Luigi parallel task scheduling (existing `--workers` parameter controls concurrency)
- For `PremiseAttackTask`: each of the 5 lenses could run on a different model

### Stage 2: Reasoning Model Judgment
A single reasoning model (e.g. `claude-sonnet-4-6-thinking`, `o3`) evaluates all N candidates and produces:

- A short score per candidate (not full responses — reasoning models are expensive, keep output minimal)
- A brief hint identifying what's missing or weak in each response
- An overall quality verdict: PASS / RETRY

Reasoning models are expensive, so the judgment output should be constrained — just scores and gap hints, not rewritten responses.

### Stage 3: Conditional Retry
If the best score from Stage 2 falls below a threshold:

- Re-run the non-reasoning models with the gap hint injected into the prompt
- The `validation_feedback` mechanism in `LLMExecutor` already handles this pattern for schema errors — this extends it to quality-based retries

If scores pass the threshold, the best candidate proceeds downstream.

---

## Where to Apply It

Early pipeline tasks where quality has the highest leverage:

| Task | Why it matters |
|------|----------------|
| `PremiseAttackTask` | 5 independent lenses, already structured for parallelism |
| `RedlineGateTask` | Gate failure stops the entire pipeline; false positives are the core diagnostic problem |
| `ProjectPlanTask` | Core decomposition — everything downstream builds on this |

Lower-priority tasks (WBS level 2/3, team enrichment, governance phases) don't need this — their outputs are less foundational.

---

## Implementation Sketch

### New config fields in `llm_config`

```json
{
  "openrouter-gemini-2.0-flash": {
    "priority": 1,
    "role": "candidate"
  },
  "openrouter-mixtral-8x22b": {
    "priority": 2,
    "role": "candidate"
  },
  "anthropic-claude-sonnet-4-6-thinking": {
    "priority": 1,
    "role": "judge"
  }
}
```

A `role` field distinguishes candidate models (cheap, parallel) from judge models (expensive, sequential).

### New `LLMExecutor` method

```python
def run_with_judge(
    self,
    execute_function: Callable[[LLM], Any],
    judge_function: Callable[[LLM, list[Any]], JudgmentResult],
    pass_threshold: float = 0.7,
    max_retries: int = 1
) -> Any:
    """
    Run candidate models in parallel, judge results, retry if below threshold.
    """
```

### Luigi task decomposition for `PremiseAttackTask`

```
PremiseAttackTask
├── requires: [PremiseAttackLensTask(lens_index=0, model=candidate_models[0]), ...]
│   └── 5 lens tasks run in parallel up to --workers limit
└── run_inner: collect lens outputs, run judge, retry if needed
```

---

## Cost Model

| Scenario | API calls | Cost estimate |
|----------|-----------|---------------|
| Current (1 model, 1 system prompt) | 1 | baseline |
| Stage 1 only (3 candidates, no judge) | 3 | ~3x |
| Full loop (3 candidates + judge, no retry) | 4 | ~4x + judge overhead |
| Full loop with 1 retry | 7 | ~7x |

For local/Ollama setups: `role: "candidate"` models run sequentially (workers=1), judge step skipped if no judge model configured. Backward-compatible.

---

## What This Is Not

- Not a jailbreak mechanism
- Not a refusal-bypass layer
- Not a replacement for the existing sequential fallback (that stays for error handling)

This is a **quality improvement loop** for tasks where the output quality directly determines the value of everything downstream.

---

## Open Questions for Simon

1. Should `role` be a config field per model, or a separate `judge_model` key at the config root?
2. What's the right `pass_threshold` — hard-coded, or configurable per task?
3. Should the judge produce a structured score (Pydantic schema) or free-form text hints?
4. Is `PremiseAttackTask` the right first implementation target, or `RedlineGateTask`?

---

## References

- `worker_plan_internal/llm_util/llm_executor.py` — `max_validation_retries` pattern (lines ~130–160)
- `worker_plan_internal/diagnostics/premise_attack.py` — 5 independent sequential lenses
- `worker_plan_internal/diagnostics/redline_gate.py` — IDEA: ensemble comment
- PR #393 — previous parallel racing proposal (merged)
