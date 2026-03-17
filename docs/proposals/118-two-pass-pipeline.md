# Proposal: Two-Pass Pipeline with Structured Adversarial Refinement

**Status:** Draft  
**Date:** 2026-03-16  
**Relates to:** `redline_gate.py`, `premise_attack.py`, `docs/proposals/56-adversarial-red-team-reality-check-for-plans.md`

---

## Observation

When given a deliberately unviable premise — a startup commercializing faster-than-light cargo delivery using Einstein-Rosen bridges stabilized by exotic matter, seeking $50M Series A, promising first delivery in 36 months — the pipeline behaves interestingly:

**PremiseAttackTask** correctly identifies the fatal flaw:

> *"The premise is fundamentally non-viable because it conflates theoretical mathematical solutions with engineering reality while ignoring the insurmountable physical constraints of exotic matter and energy requirements. The proposal ignores that stabilizing an Alcubierre drive requires negative energy densities equivalent to the mass-energy of Jupiter, a resource magnitude impossible to source or contain within a $50M budget."*  
> — PremiseAttack output, REJECT verdict

**Downstream tasks absorb this finding and pivot:** `MakeAssumptionsTask` reframes the entire company around a quantum logistics spin-off, explicitly calling FTL "physically impossible" throughout. `ProjectPlan` follows suit — "WarpDrive Quantum Logistics LLC", "Impossibility Certification report", abandoning FTL as the primary product. `SWOTTask` lists "Fundamental Physical Impossibility" as the first weakness.

The pipeline is already doing significant self-correction via implicit context propagation. PremiseAttack findings reach downstream tasks because all tasks receive accumulated prior context.

---

## Problem

The implicit self-correction works — but it has two limitations:

**1. The pivot is user-invisible.** A user who asked for an FTL startup plan receives a quantum logistics company plan instead, with no explicit notification that the plan was revised due to adversarial findings. The executive summary may present the pivoted plan as if it were the original intent.

**2. The correction is implicit, not auditable.** There is no record of *which* assumptions were revised because of PremiseAttack findings, *which* risks were added, or *which* sections of the plan changed between the "naive" run and the adversarially-informed version. A reviewer cannot easily distinguish "the model planned this because it's a good idea" from "the model planned this because PremiseAttack told it the original idea was impossible."

A two-pass model makes the correction explicit, auditable, and user-visible — without changing the fact that Pass 1 runs unconstrained.

---

## Proposed Solution: Two-Pass Model

### Pass 1 — Unconstrained Generation (current pipeline, unchanged)

The full pipeline runs as today. `PremiseAttackTask` fires early and records its findings. All downstream tasks complete normally. The implicit context propagation continues to work as observed.

**Goal:** Preserve creative output and the existing implicit correction behavior. Do not block or gate on PremiseAttack findings.

### Pass 2 — Structured Adversarial Refinement (new)

A second, lightweight pass that produces an explicit record of adversarially-motivated changes:

- Which assumptions were flagged as invalidated by PremiseAttack
- Which risks were added to the risk register specifically because of PremiseAttack findings
- A revised executive summary that explicitly acknowledges the adversarial finding and the pivot it triggered
- A diff between Pass 1 and Pass 2 outputs for the affected sections

Pass 2 does not re-run the full pipeline. It re-runs only:
- `MakeAssumptionsTask` — produce a marked version (which assumptions are adversarially-informed)
- `IdentifyRisksTask` — add risks explicitly flagged by PremiseAttack
- `ExecutiveSummaryTask` — produce a version that names the adversarial finding and the resulting pivot

### Output

Pass 2 writes to a `/refined/` subdirectory. The original Pass 1 output is preserved unchanged. Both are available to the user.

---

## Benefits

1. **Makes implicit correction explicit** — Users see why the plan differs from what they submitted, not just that it does.
2. **Auditable** — Reviewers can identify which parts of the plan were adversarially motivated vs. organically generated.
3. **No disruption to Pass 1** — The existing implicit propagation continues to work. Pass 2 is additive.
4. **Graceful degradation** — If PremiseAttack produces no significant findings, Pass 2 is a no-op.

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
