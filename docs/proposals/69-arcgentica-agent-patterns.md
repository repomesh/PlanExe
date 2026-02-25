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

Simon recently added `task_retry` to the MCP layer — tasks can now be retried. The wiring between ReviewPlan's critique output and `task_retry` doesn't exist yet.

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

### Adaptation 2: Wire ReviewPlan Signals to `task_retry`

ReviewPlan already classifies failure signals by question block. The existing `task_retry` MCP tool already retries tasks. The missing piece is the bridge.

```python
# New module: worker_plan_internal/diagnostics/review_retry_bridge.py

SIGNAL_TO_TASK_GROUP = {
    "critical_issues":     ["MakeAssumptions", "ReviewAssumptions"],
    "showstopper_risks":   ["GovernancePhase4", "GovernancePhase5"],
    "timeline_dependency": ["CreateWBSLevel3", "EstimateWBSTaskDurations", "ProjectSchedulePopulator"],
    "data_uncertainty":    ["DataCollection", "FilterDocumentsToFind"],
    "stakeholder_gaps":    ["FindTeamMembers", "ReviewTeam"],
}

def parse_review_signals(review_plan_path: Path) -> list[dict]:
    """Extract actionable signals from review_plan.md."""
    text = review_plan_path.read_text()
    signals = []
    for category, tasks in SIGNAL_TO_TASK_GROUP.items():
        if is_flagged(text, category):
            signals.append({"category": category, "tasks": tasks, "severity": extract_severity(text, category)})
    return signals

def trigger_retries(run_id: str, signals: list[dict], budget: RetryBudget):
    """Call task_retry for each flagged task group, respecting budget."""
    for signal in signals:
        if signal["severity"] < budget.severity_threshold:
            continue
        for task_name in signal["tasks"]:
            if budget.can_retry():
                task_retry(run_id=run_id, task_name=task_name, context=signal["category"])
                budget.consume()
```

`RetryBudget` caps total retries per run (default: 3 task groups, 2 retries each) to prevent runaway costs.

### Adaptation 3: Typed Output Contracts

arcgentica agents return typed objects, not raw strings:

```python
result = await agent.call(FinalSolution, task, examples=examples)
# FinalSolution is a TypedDict — parsing failure raises immediately, not 20 tasks later
```

PlanExe tasks write markdown. Structural failures are discovered late. Adding Pydantic output validation to high-risk tasks catches them at the task boundary:

```python
from pydantic import BaseModel, validator

class AssumptionsOutput(BaseModel):
    assumptions: list[str]
    risks: list[str]
    confidence: float  # 0.0-1.0

    @validator('assumptions')
    def at_least_three(cls, v):
        if len(v) < 3:
            raise ValueError('Need at least 3 assumptions')
        return v

class MakeAssumptions(luigi.Task):
    def run(self):
        raw = self.llm.execute(self.prompt)
        try:
            parsed = AssumptionsOutput.model_validate_json(raw)
        except ValidationError as e:
            # Fail loudly at this task, not 30 tasks later
            raise TaskOutputError(f"MakeAssumptions output failed validation: {e}")
        self.output().open('w').write(parsed.model_dump_json())
```

This requires prompts to request JSON output — a prompt change, not an architecture change. The JSON structure becomes the contract between tasks.

**Where to start:** `MakeAssumptions` → `AssumptionsOutput`. Single task, high leverage, easy to validate.

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

## Implementation Priority

Start small. Each adaptation is independent:

| Priority | Adaptation | Effort | Risk |
|----------|-----------|--------|------|
| 1 | ReviewPlan → task_retry bridge | Low | Low — uses existing task_retry |
| 2 | Soft self-eval on MakeAssumptions | Medium | Low — bounded, isolated to one task |
| 3 | Typed output for MakeAssumptions | Medium | Medium — requires prompt change |
| 4 | PlanComplexityAssessor | High | Low — purely additive |

Adaptation 1 has the highest value/effort ratio. Simon already built `task_retry` — we're just connecting ReviewPlan output to it. No new infrastructure, no prompt changes, no Luigi restructuring.

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
