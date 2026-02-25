---
title: Hardening PlanExe with Arcgentica Agent Patterns
date: 2026-02-25
status: proposal
author: Larry (VoynichLabs)
---

# Proposal 69: Hardening PlanExe with Arcgentica Agent Patterns

**Author:** Larry (VoynichLabs)  
**Date:** 2026-02-25  
**Status:** Proposal  
**Tags:** `architecture`, `agent-orchestration`, `reliability`, `agentica`, `luigi`

---

## Context

We spent time reading two Symbolica AI repositories:

- [agentica-typescript-sdk](https://github.com/VoynichLabs/agentica-typescript-sdk)
- [arcgentica](https://github.com/VoynichLabs/arcgentica) — the ARC-AGI-2 solver built on agentica-python-sdk

arcgentica scores 85.28% on ARC-AGI-2 at $6.94/task using Claude Opus. Its architecture is fundamentally different from PlanExe's Luigi DAG in ways that are directly applicable to PlanExe's brittleness problems.

We also read `worker_plan_internal/plan/run_plan_pipeline.py` in full. PlanExe is already a sophisticated multi-agent system — 40+ Luigi tasks, each making its own LLMExecutor call with retry and resume built in. The orchestration layer is solid. The brittleness is not in the plumbing; it's in three specific gaps.

---

## The Three Brittleness Gaps

### Gap 1: One LLM call per task — no self-evaluation

Every Luigi task in PlanExe calls `LLMExecutor.execute()` once and writes the result to disk. If the model produces a malformed or low-quality output, the pipeline accepts it and moves on. The next 30 tasks process garbage silently.

arcgentica handles this differently. Agents evaluate their own output before returning:

```python
# From arcgentica solve.py
result = await agent.call(FinalSolution, task, examples=examples)
soft = soft_accuracy(result.transform_code, examples)
if soft < threshold:
    result = await agent.call(FinalSolution, task, examples=examples, hint=result)
```

The agent checks its own work. If `soft_accuracy` is below threshold, it retries with its first attempt as a hint. Two attempts max. This is not unlimited looping — it's bounded self-correction.

### Gap 2: ReviewPlan produces critiques that die at the task boundary

`ReviewPlan.execute()` asks 15 structured question blocks (critical issues, showstopper risks, assumptions, KPIs, etc.) and writes a structured critique to `review_plan.md`. That's where it stops. The critique never reaches the tasks that caused the problems.

⚠️ **CORRECTION (Simon Strandgaard, 2026-02-25):** task_retry is an MCP interface for restarting Luigi pipelines. The actual retry logic lives in `llm_executor.py` and is not exposed through MCP. Using MCP task_retry inside `run_plan_pipeline.py` would cause recursive calls and database manipulation, making it unsuitable as a fallback mechanism. Do not pursue the "ReviewPlan → task_retry bridge" pattern.

### Gap 3: Pipeline always runs all 40+ tasks regardless of input complexity

A two-sentence business idea goes through the same GovernancePhase 1-6, ExpertOrchestrator, full WBS Level 1-2-3, and CreateSchedule as a full enterprise plan. The `speed_vs_detail` parameter controls model choice but not task selection. This is expensive and produces bloated output for simple inputs.

---

## Four Adaptations from arcgentica

### Adaptation 1: Soft Self-Evaluation Loop for High-Stakes Tasks

For tasks where a bad output causes maximum downstream damage — `MakeAssumptions`, `ReviewAssumptions`, `CreateWBSLevel1` — wrap the `LLMExecutor` call in a bounded self-evaluation loop.

```python
class MakeAssumptions(luigi.Task):
    def execute_with_eval(self, prompt: str, max_attempts: int = 2) -> str:
        attempt = 0
        output = None
        while attempt < max_attempts:
            output = self.llm.execute(prompt)
            score = self.evaluate_assumptions(output)
            if score.passes_threshold:
                break
            # Re-prompt with self-critique as context
            prompt = f"{prompt}\n\nPrevious attempt:\n{output}\n\nIssues found:\n{score.issues}\n\nPlease correct:"
            attempt += 1
        return output

    def evaluate_assumptions(self, output: str) -> EvalResult:
        """Lightweight check: are all required sections present? Any contradictions?"""
        required = ["Market", "Timeline", "Budget", "Risks"]
        missing = [s for s in required if s not in output]
        return EvalResult(
            passes_threshold=len(missing) == 0,
            issues=f"Missing sections: {missing}" if missing else ""
        )
```

This adds one retry for the highest-risk tasks. Not 10 iterations — just 2. The `evaluate_assumptions` check is cheap (structural, not another LLM call).

**Where to apply:** `MakeAssumptions`, `CreateWBSLevel1`, `SelectScenario`, `ReviewPlan`

### Adaptation 2: ~~Wire ReviewPlan Signals to `task_retry`~~ [INVALID]

⚠️ **REJECTED (Simon Strandgaard, 2026-02-25):** The MCP `task_retry` interface is not suitable as a ReviewPlan fallback mechanism. The retry logic is internal to `llm_executor.py` in each task, not exposed through MCP. Using MCP task_retry inside `run_plan_pipeline.py` would cause recursive calls and database corruption. 

**Do not pursue this adaptation.** Instead, focus on Adaption 5 (Fermi Sanity Check) and improving task-level retry logic directly within `llm_executor.py`.

### Adaptation 3: Systemic Structured Output Validation (Already Implemented)

⚠️ **CORRECTION (Simon Strandgaard, 2026-02-25):** PlanExe **already uses structured output validation systemically**, not just at single task boundaries.

Across `premise_attack.py`, `identify_potential_levers.py`, `premortem.py`, and many other files, PlanExe enforces structured output by saving results as:
- **JSON:** Full system prompt, user prompt, input data, and LLM response (for troubleshooting)
- **Markdown:** Pretty-printed essential parts only (for human review)

This dual output pattern (JSON + Markdown) is the systemic contract between tasks. Each task validates its JSON output before writing, and downstream tasks can trust the structure.

**No change needed.** The typed output pattern is already built into PlanExe's core. Focus instead on improving task-level validation logic within existing structured output patterns.

### Adaptation 4: Complexity-Gated Task Selection

arcgentica's root agent decides dynamically how many sub-agents to spawn based on the problem. PlanExe can adapt this: an early `PlanComplexityAssessor` task gates which downstream task groups run.

```python
class PlanComplexityAssessor(luigi.Task):
    """
    Fast, cheap classification of plan complexity.
    Output: complexity.json with tier and skip_phases list.
    """
    def run(self):
        prompt_text = self.load_prompt()
        tier = self.llm.execute_cheap(COMPLEXITY_PROMPT.format(prompt=prompt_text))
        # Returns: "simple" | "medium" | "complex"
        
        skip_phases = {
            "simple":  ["GovernancePhase4", "GovernancePhase5", "GovernancePhase6",
                        "ExpertCriticism", "CreateWBSLevel3"],
            "medium":  ["GovernancePhase5", "GovernancePhase6"],
            "complex": [],
        }[tier]
        
        with self.output().open('w') as f:
            json.dump({"tier": tier, "skip_phases": skip_phases}, f)

class GovernancePhase4(luigi.Task):
    def requires(self):
        return [GovernancePhase3(), PlanComplexityAssessor()]
    
    def run(self):
        complexity = json.loads(self.input()[1].open().read())
        if "GovernancePhase4" in complexity["skip_phases"]:
            # Write empty output and mark complete
            self.output().open('w').write(json.dumps({"skipped": True, "reason": "complexity=simple"}))
            return
        # ... normal execution
```

`PlanComplexityAssessor` uses a cheap model (Haiku, Flash) for the classification — not the full pipeline model. Cost: one small LLM call per run. Benefit: skip 5-10 expensive tasks for simple plans.

---

## What Stays the Same

- The Luigi DAG structure. It's correct. Resume, retry, and flag-file-based progress tracking are solid.
- `LLMExecutor`. The fallback model chain and retry logic are good. We're wrapping it, not replacing it.
- The overall pipeline sequence. The task ordering is well-designed.

---

## Implementation Priority (REVISED)

⚠️ **UPDATE (Simon Strandgaard, 2026-02-25):** Adaptation 2 (ReviewPlan → task_retry bridge) is invalid. See corrections above.

**Valid adaptations, ranked by value/effort:**

| Priority | Adaptation | Effort | Risk | Notes |
|----------|-----------|--------|------|-------|
| 1 | Fermi Sanity Check (Adaptation 5) | Medium | Low | Simon's primary quality signal: quantitative grounding |
| 2 | Soft self-eval on MakeAssumptions | Medium | Low | Bounded, isolated to one task |
| 3 | ~~Typed output for MakeAssumptions~~ | N/A | N/A | Already systemic in PlanExe — no change needed |
| 4 | PlanComplexityAssessor | High | Low | Cost optimization, lower urgency |

**Start with Adaptation 5 (Fermi Sanity Check).** It directly addresses Simon's feedback on quantitative grounding and doesn't require architectural changes to Luigi or task_retry.

---

## Adaptation 5: Quantitative Grounding (Fermi Sanity Check)

*Added after direct feedback from Simon Strandgaard, 2026-02-25*

Simon's primary quality signal: **numbers off by 2 orders of magnitude are the real failure mode.** Plans must be grounded in current physical reality. Estimates without bounds are not estimates — they're guesses.

This is the highest-priority adaptation. It doesn't require arcgentica patterns — it requires a new task.

### New task: `FermiSanityCheck`

Runs after `MakeAssumptions` and before `ReviewPlan`. Extracts quantitative claims from the plan and checks them against physical plausibility.

```python
class QuantifiedClaim(BaseModel):
    description: str
    lower_bound: float
    upper_bound: float
    unit: str
    confidence: Literal["high", "medium", "low"]
    evidence: str  # what justifies this range

class FermiSanityResult(BaseModel):
    claims: list[QuantifiedClaim]
    flagged: list[str]  # claims where upper/lower ratio > 100x or evidence is empty
    grounded: bool       # False if any critical claim is flagged

class FermiSanityCheck(luigi.Task):
    """
    Extracts numerical claims from assumptions and validates order-of-magnitude plausibility.
    Fails loudly if critical estimates are ungrounded (no bounds) or implausible (>2 OOM spread).
    """
    def requires(self):
        return MakeAssumptions()

    def run(self):
        assumptions_text = self.input().open().read()
        result = self.llm.execute(
            FERMI_CHECK_PROMPT,
            context=assumptions_text,
            return_type=FermiSanityResult
        )

        flagged = [
            c for c in result.claims
            if c.lower_bound == 0
            or (c.upper_bound / max(c.lower_bound, 1e-9)) > 100
            or not c.evidence
        ]
        result.flagged = [c.description for c in flagged]
        result.grounded = len(flagged) == 0

        with self.output().open('w') as f:
            f.write(result.model_dump_json(indent=2))

        if not result.grounded:
            # Do not halt pipeline — log and flag for ReviewPlan to catch
            logger.warning(f"FermiSanityCheck: {len(flagged)} ungrounded claims")
```

**The prompt** (`FERMI_CHECK_PROMPT`) instructs the LLM to:
1. Extract every numerical claim from the assumptions (cost, timeline, market size, resource requirements, physical quantities)
2. Express each as lower/upper bounds with units
3. Cite what justifies the range (industry data, physical constants, analogous projects)
4. Flag any claim where the ratio `upper/lower > 100` or where no evidence is provided

**Integration:** `ReviewPlan` reads `fermi_sanity.json` as an additional input. Ungrounded claims in `flagged` are automatically promoted to the `critical_issues` signal category in the ReviewPlan → task_retry bridge (Adaptation 2).

### Final Priority Order (Updated 2026-02-25)

Based on Simon Strandgaard's feedback, the final implementation order is:

| Priority | Adaptation | Rationale |
|----------|-----------|-----------|
| 1 | **Fermi Sanity Check (Adaptation 5)** | Simon's primary quality signal; highest value/effort |
| 2 | Soft self-eval loop on high-stakes tasks | Incremental quality improvement; low risk |
| 3 | ~~ReviewPlan → task_retry bridge~~ | **INVALID** — do not pursue (see Gap 2 correction) |
| 4 | ~~Typed output contracts~~ | **Already systemic in PlanExe** (see Adaptation 3 correction) |
| 5 | Complexity-gated pipeline (Adaptation 4) | Cost optimization; lower urgency |

**Removed from scope:** Adaptations 2 and 3 as described are either invalid (MCP task_retry) or redundant (structured output). Focus on Adaptation 5 first.

---

## Open Questions for Simon

1. **What does a "good plan" look like to your actual users, and what's the most common complaint you hear?** We've speculated about which pipeline stages fail — it would be valuable to know what failure modes users actually notice.

2. **Is the Luigi DAG the architecture you want to extend for the next 12 months?** If there are plans to replace the orchestration layer, we should know before proposing deep integrations.

3. **Which of these four adaptations, if any, aligns with where you want PlanExe to go?** Specifically: are typed Pydantic output contracts an acceptable pattern given your codebase conventions?

---

## References

- [arcgentica source](https://github.com/VoynichLabs/arcgentica)
- [agentica-typescript-sdk](https://github.com/VoynichLabs/agentica-typescript-sdk)
- [PlanExe pipeline notes](https://github.com/VoynichLabs/swarm-coordination/blob/main/events/2026/feb/25/planexe-pipeline-notes.md)
- [Proposal 63: Luigi Agent Integration](./63-luigi-agent-integration.md) — complementary `@agent_meta` decorator approach
- [Proposal 59: A/B Testing for Prompt Optimization](./59-prompt-optimizing-with-ab-testing.md) — evaluation harness for validating any changes proposed here
