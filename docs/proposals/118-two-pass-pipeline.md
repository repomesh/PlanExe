# Proposal: Two-Pass Pipeline with Adversarial Refinement

**Status:** Draft  
**Date:** 2026-03-16  
**Relates to:** `redline_gate.py`, `premise_attack.py`, `docs/proposals/56-adversarial-red-team-reality-check-for-plans.md`

---

## Problem

`PremiseAttackTask` runs early in the pipeline and produces adversarial findings — identifying physically impossible premises, unvalidated assumptions, and high-risk framing. These findings are recorded in the output but have no downstream effect. The rest of the pipeline runs identically regardless of how damning the adversarial verdict is.

### Observed behavior: red-team prompt

When given a deliberately unviable premise — a startup commercializing faster-than-light cargo delivery using Einstein-Rosen bridges stabilized by exotic matter, seeking $50M Series A, promising first delivery in 36 months — `PremiseAttackTask` correctly identifies the fatal flaw:

> *"The premise is fundamentally non-viable because it conflates theoretical mathematical solutions with engineering reality while ignoring the insurmountable physical constraints of exotic matter and energy requirements. The proposal ignores that stabilizing an Alcubierre drive requires negative energy densities equivalent to the mass-energy of Jupiter, a resource magnitude impossible to source or contain within a $50M budget."*  
> — PremiseAttack output, REJECT verdict

Despite this, the downstream pipeline continues and produces a 60-task business plan: market sizing, Series A structure, team composition, patent strategy, WBS, Gantt chart. However — and this is the interesting finding — `MakeAssumptionsTask` does absorb the adversarial context and responds to it:

> *"Given the physical impossibility of exotic matter, what is the specific financial contingency plan to pivot the $50M Series A into viable adjacent technologies (e.g., quantum logistics) before capital exhaustion?"*  
> **Assumption:** The company will immediately allocate 60% of the Series A funding to a spin-off entity focused on quantum computing for logistics optimization, treating the FTL project as a long-term R&D incubator rather than an immediate product launch.

This shows partial propagation: `MakeAssumptionsTask` acknowledges the impossibility and pivots its assumptions to a quantum computing framing. But the executive summary, risk register, and WBS continue to plan the original FTL product without this correction. The adversarial finding reached one task and not others.

### Observed behavior: prompt misread

When a prompt describes an indirect thermal coupling architecture (laptop waste heat → absorber plate → water reservoir → incubator chamber), downstream tasks have been observed building a plan for a different device entirely — one with direct chip-to-egg heat transfer — without referencing the architecture described in the prompt. The PremiseAttack output correctly identified the mismatch, but subsequent tasks did not have this correction in context.

In both cases, adversarial findings exist in the output directory but are not consumed by the tasks that follow.

---

## Proposed Solution: Two-Pass Model

### Pass 1 — Unconstrained Generation (current pipeline, unchanged)

The full pipeline runs as today. `PremiseAttackTask` fires early and records its findings. All downstream tasks complete normally. No blocking, no gating.

**Goal:** Preserve creative output. `PremiseAttackTask` is intentionally harsh — it will find problems with any plan. Blocking the pipeline on its output would prevent legitimate plans from completing.

### Pass 2 — Targeted Adversarial Refinement (new)

A second, lightweight pass that ingests:
- The full Pass 1 output directory
- `PremiseAttackTask` findings
- `RedlineGate` findings (when implemented)

Pass 2 re-runs only the tasks most implicated by adversarial findings. Tasks that are structural (Gantt, document lists, schedule) are skipped. Tasks that depend on assumptions flagged as invalid are re-run with adversarial context prepended.

**Candidate tasks for re-run in Pass 2:**
- `MakeAssumptionsTask` — re-run with PremiseAttack output in context
- `IdentifyRisksTask` — extend risk register with PremiseAttack-flagged risks
- `ExecutiveSummaryTask` — revise to acknowledge key adversarial findings
- `QuestionsAndAnswersTask` — add entries addressing rejection criteria

**Tasks that do NOT re-run:**
- WBS, Gantt, schedule (structural)
- Team composition
- Document lists
- Financial model (unless PremiseAttack specifically flags financial assumptions)

### Expected output for the warp drive example

**Pass 1 executive summary (current behavior):**
> *"WarpDrive Inc. is positioned to capture significant share of the time-sensitive cargo market. With a $50M Series A and a 12-person physics team, first commercial deliveries are projected within 36 months..."*

**Pass 2 executive summary (proposed):**
> *"WarpDrive Inc.'s premise rests on a physics assumption — stable exotic matter — that has no known production pathway. Adversarial review flagged this as a fundamental blocker, not an engineering risk. The following plan is framed as a 10-year research roadmap contingent on exotic matter discovery, not a 36-month commercialization timeline. Key assumptions marked UNVALIDATED should be treated as research targets, not business inputs."*

---

## Implementation Sketch

```python
# Conceptual only — not a PR-ready implementation

class Pass2RefinementPipeline:
    """
    Runs targeted task re-execution using Pass 1 outputs + adversarial findings.
    Only re-runs tasks implicated by premise_attack_score or redline_gate_score.
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

## Benefits

1. **Preserves creativity** — Pass 1 runs unconstrained. Legitimate plans are not blocked by an adversarial agent that is intentionally harsh on all input.
2. **Gives adversarial findings teeth** — Pass 2 ensures rejection signals reach the assumptions register, risk register, and executive summary.
3. **Efficient** — Pass 2 re-runs 3–5 tasks, not the full pipeline. Runtime overhead is small.
4. **Auditable** — Pass 1 output is preserved unchanged. Reviewers can compare before/after refinement.
5. **Graceful degradation** — If PremiseAttack produces no unanimous rejections, Pass 2 is a no-op.

---

## Open Questions

1. Should Pass 2 be a separate `planexe` subcommand (e.g., `./planexe refine_plan --run-id-dir ...`) or an automatic second phase of `create_plan`?
2. What threshold triggers Pass 2? Unanimous REJECT only, or any REJECT score above a configurable threshold?
3. Should `redline_gate.py` findings also feed Pass 2, or only `premise_attack.py`?
4. Is a `/refined/` subdirectory the right output structure, or a separate run dir with a `_refined` suffix?
5. Should the list of "assumption-dependent tasks" be hardcoded, or derived dynamically from the task graph (e.g., any task whose `requires()` includes `MakeAssumptionsTask` output)?

---

## Related Files

- `worker_plan/worker_plan_internal/diagnostics/premise_attack.py`
- `worker_plan/worker_plan_internal/diagnostics/redline_gate.py` (when implemented)
- `docs/proposals/56-adversarial-red-team-reality-check-for-plans.md`
- `docs/optimizer_roadmap.md`
- `docs/proposals/117-system-prompt-optimizer.md`
