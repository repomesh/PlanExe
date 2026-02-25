# Simon's Critical Feedback on PlanExe Architecture (2026-02-25)

**Date:** February 25, 2026  
**From:** Simon Strandgaard  
**Critical:** YES — Architectural constraints for all future work

---

## Context

During feedback on Proposal 69 (Arcgentica Agent Patterns), Simon clarified three **non-negotiable architectural constraints** that must be understood before any work on PlanExe's retry, task orchestration, or output validation systems.

---

## 1. Task Retry Logic Lives in `llm_executor.py`, Not MCP

### The Mistake
We assumed `task_retry` (the MCP interface) could be called from within `run_plan_pipeline.py` as a fallback mechanism when ReviewPlan detects failures.

### Simon's Correction
**Task_retry is MCP-only.** The actual retry logic is internal to `llm_executor.py` in each Luigi task. Using MCP `task_retry` inside `run_plan_pipeline.py` would:
- Cause recursive calls (the task calls the pipeline, the pipeline calls the task)
- Corrupt the database (duplicate writes, state inconsistency)
- Create an unreliable fallback mechanism

### What This Means
- **DO NOT** use MCP task_retry as a fallback from ReviewPlan or any orchestration layer
- **DO** improve retry logic directly within individual task's `LLMExecutor` calls
- The retry mechanism is **task-local**, not pipeline-global
- Any cross-task retry coordination must happen through Luigi's existing task dependencies and resume logic, not through MCP

### Where This Applies
- Proposal 69, Adaptation 2 ("ReviewPlan → task_retry bridge") — **INVALID**
- Any future attempt to add global retry coordination
- Any work touching `run_plan_pipeline.py` retry logic

---

## 2. Structured Output Validation Is Systemic, Not Task-Specific

### The Mistake
We suggested adding Pydantic output validation to specific high-risk tasks (e.g., `MakeAssumptions`) as a new pattern.

### Simon's Correction
**PlanExe already uses structured output validation systemically across the entire codebase.**

Structured output is enforced in files including:
- `premise_attack.py`
- `identify_potential_levers.py`
- `premortem.py`
- **Many other files**

### The Pattern
Results are saved **dual-format**:
1. **JSON:** Full system prompt, user prompt, input data, LLM response (for troubleshooting)
2. **Markdown:** Pretty-printed essential parts only (for human review)

Each task validates its JSON output **before writing**. Downstream tasks can trust the structure because of this validation at the task boundary.

### What This Means
- **DO NOT** add task-level Pydantic validation as a new pattern — it already exists
- **DO** follow the existing dual-format (JSON + Markdown) pattern for new tasks
- **DO** inspect the JSON/Markdown structure in existing tasks as your reference implementation
- The structured output pattern is the contract between tasks

### Where This Applies
- Proposal 69, Adaptation 3 ("Typed Output Contracts") — **ALREADY IMPLEMENTED**, no changes needed
- Any new task development — follow existing structured output pattern
- Output validation improvements must build on the dual-format system, not replace it

---

## 3. Quality Signal: Quantitative Grounding (Numbers Must Be Bounded)

### The Real Problem
Plans fail when **estimates are off by 2 orders of magnitude.** The root cause is ungrounded numbers with no bounds.

### Simon's Criteria
A good estimate has:
- **Lower bound** (e.g., $100k minimum)
- **Upper bound** (e.g., $500k maximum)
- **Ratio < 100x** (if the range is wider, it's a guess, not an estimate)
- **Evidence** (what justifies this range? Industry data? Physical constants? Analogy?)

Ungrounded estimates (no bounds, no evidence) are the failure mode Simon wants to prevent.

### What This Means
- **DO** require all quantitative claims in plans to have bounds and evidence
- **DO** flag any estimate where `upper/lower > 100x` as "ungrounded"
- **DO NOT** accept estimates that cite no evidence
- **DO** build this validation into FermiSanityCheck or similar task (Proposal 69, Adaptation 5)

### Where This Applies
- `MakeAssumptions` output (require bounded estimates with evidence)
- `ReviewPlan` input (check for ungrounded quantitative claims)
- Any task producing quantitative output
- This is the **highest-priority quality signal** for Simon

---

## Summary Table

| Constraint | Impact | Action |
|-----------|--------|--------|
| Task retry is local, not global | MCP task_retry can't be used for cross-task coordination | Fix: Use llm_executor.py retry logic; don't call MCP from pipeline |
| Structured output is systemic | JSON + Markdown pattern already used everywhere | Fix: Follow existing pattern; don't add task-level Pydantic validation as new |
| Quantitative grounding matters most | Ungrounded estimates cause 2-order-of-magnitude failures | Fix: Require bounds and evidence on all numerical claims |

---

## References

- **Proposal 69:** Hardening PlanExe with Arcgentica Agent Patterns (docs/proposals/69-arcgentica-agent-patterns.md)
- **Implementation:** See Adaptation 5 (Fermi Sanity Check) for quantitative grounding validation
- **Feedback source:** Simon Strandgaard, 2026-02-25, Discord #openclaw-bots

---

## For Future Developers

When working on PlanExe retry logic, output validation, or task orchestration:

1. **Read this file first.** It contains non-negotiable constraints.
2. **Check premise_attack.py, identify_potential_levers.py, premortem.py** for the structured output pattern.
3. **Do NOT use MCP task_retry as a fallback mechanism** — it will break the database.
4. **Require bounds and evidence on all quantitative claims** — this is Simon's quality signal.

---

**Last updated:** 2026-02-25  
**Updated by:** Larry (VoynichLabs)  
**Status:** Active — apply to all future PlanExe work
