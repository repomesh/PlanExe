# Proposal: Two-Pass Pipeline with Adversarial Refinement

**Status:** Draft  
**Author:** EgonBot, Bubba (VoynichLabs crew)  
**Date:** 2026-03-16  
**Relates to:** `redline_gate.py`, `premise_attack.py`

---

## Problem

`PremiseAttackTask` and `RedlineGate` run early in the pipeline as diagnostic signals. They produce useful adversarial findings — identifying physically impossible premises, financial red flags, or unvalidated assumptions. However, these findings have no downstream effect. The rest of the pipeline runs identically whether PremiseAttack produces 0 rejections or 5 unanimous rejections.

**Observed in testing (2026-03-16):**
- FTL_PremiseAttack_StressTest_v1: PremiseAttack produced 5/5 unanimous REJECTs citing Alcubierre metric exotic matter requirements, Theranos fraud archetype. The pipeline then generated a full 60-task business plan for WarpDrive Inc. without any reference to the physics impossibility.
- AIChickenIncubator runs v1/v2: PremiseAttack flagged the design correctly but downstream tasks built on misread architecture anyway.

The adversarial findings are advisory only. They do not feed back into MakeAssumptions, RiskRegister, ProjectPlan, or ExecutiveSummary.

---

## Proposed Solution: Two-Pass Model

### Pass 1 — Unconstrained Generation (current pipeline, unchanged)

The full pipeline runs as today. PremiseAttack and RedlineGate fire early and record their findings. All downstream tasks complete normally — WBS, scenarios, team, financials, everything. No blocking, no gating.

**Goal:** Preserve creative output. The pipeline generates the best plan it can given the prompt, without adversarial interference.

### Pass 2 — Targeted Adversarial Refinement (new)

A second, lightweight pass that ingests:
- The full Pass 1 output directory
- PremiseAttack findings (`002-4-premise_attack.md`)
- RedlineGate findings (when implemented)

Pass 2 runs a targeted subset of tasks — only those most implicated by the adversarial findings. Tasks that can run unconditionally (Gantt, document lists, team bios) are skipped. Tasks that depend on invalidated assumptions are re-run with the adversarial findings injected into their system prompts.

**Candidate tasks for re-run in Pass 2:**
- `MakeAssumptionsTask` — re-run with PremiseAttack output prepended to context
- `IdentifyRisksTask` — extend risk register with PremiseAttack-flagged risks
- `ExecutiveSummaryTask` — revise to acknowledge key adversarial findings
- `QuestionsAndAnswersTask` — add Q&A entries directly addressing rejection criteria

**Tasks that do NOT re-run:**
- WBS (structural, not premise-dependent)
- Gantt / schedule
- Team composition
- Document lists
- Financial model (unless PremiseAttack specifically flags financial assumptions)

### Output

Pass 2 writes to a `/refined/` subdirectory within the existing run dir, or to a new run dir with a `_refined` suffix. The original Pass 1 output is preserved unchanged.

---

## Implementation Sketch

```python
# Conceptual only — not a PR-ready implementation

class Pass2RefinementPipeline:
    """
    Runs targeted task re-execution using Pass 1 outputs + adversarial findings.
    Only re-runs tasks flagged by premise_attack_score or redline_gate_score.
    """
    
    def should_rerun(self, task_name: str, premise_attack_result: dict) -> bool:
        unanimous_reject = all(
            r.get('verdict') == 'REJECT' 
            for r in premise_attack_result.get('attacks', [])
        )
        if unanimous_reject and task_name in ASSUMPTION_DEPENDENT_TASKS:
            return True
        return False
    
    def inject_adversarial_context(self, system_prompt: str, findings: str) -> str:
        return f"""ADVERSARIAL FINDINGS FROM PREMISE REVIEW:
{findings}

Consider the above findings when generating your output. Where the findings 
identify physically impossible or financially unviable assumptions, acknowledge 
them explicitly and plan accordingly.

---

{system_prompt}"""
```

---

## Example: FTL Warp Drive

**Pass 1 output:** Full 60-task business plan for WarpDrive Inc. — funding strategy, team composition, logistics partnerships, patent filing strategy, Series A deck.

**PremiseAttack finding:** 5/5 REJECT — "Alcubierre metric requires exotic matter with negative energy density. No known mechanism exists for producing or stabilizing such matter. This is not an engineering challenge; it is a violation of known physics."

**Pass 2 output (expected):**
- `MakeAssumptions` revised: "Assumption: exotic matter synthesis pathway exists — **FLAGGED AS UNVALIDATED BY PREMISE REVIEW.** Risk: CRITICAL. Mitigation: reframe as speculative research roadmap, not commercial venture."
- `ExecutiveSummary` revised: "WarpDrive Inc. faces a fundamental physics barrier identified in premise review. The following plan is structured as a 10-year research roadmap contingent on exotic matter discovery, not a 36-month commercialization timeline."
- `IdentifyRisks` extended: adds "Physics impossibility" as highest-severity risk with zero mitigation path at current technology level.

---

## Benefits

1. **Preserves creativity** — Pass 1 runs unconstrained. Novel ideas aren't blocked by adversarial agents that may be overcritical (PremiseAttack is intentionally harsh on all plans).
2. **Gives adversarial findings teeth** — Pass 2 ensures rejection signals reach the assumptions, risk register, and executive summary.
3. **Efficient** — Pass 2 only re-runs 3-5 tasks, not the full 60-task pipeline. Runtime overhead is small.
4. **Auditable** — Original Pass 1 output preserved. Reviewers can compare before/after refinement.
5. **Graceful degradation** — If PremiseAttack produces no unanimous rejections, Pass 2 is a no-op (nothing to refine).

---

## Open Questions for Simon

1. Should Pass 2 be a separate `planexe` subcommand (e.g., `./planexe refine_plan --run-id-dir ...`) or an automatic second phase of `create_plan`?
2. What threshold triggers Pass 2? Unanimous REJECT only, or any REJECT score above a threshold?
3. Should `redline_gate.py` findings also feed Pass 2, or only `premise_attack.py`?
4. Is the `/refined/` subdirectory the right output structure, or a separate run dir with `_v2` suffix?

---

## Related Files

- `worker_plan/worker_plan_internal/diagnostics/premise_attack.py`
- `worker_plan/worker_plan_internal/diagnostics/redline_gate.py` (when implemented)
- `docs/optimizer_roadmap.md`
- `docs/proposals/117-system-prompt-optimizer.md`
