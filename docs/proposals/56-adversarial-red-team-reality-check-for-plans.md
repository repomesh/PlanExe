---
title: Adversarial Red-Team Reality Check for Plans
date: 2026-02-18
status: proposal
author: Simon Strandgaard
---

# Adversarial Red-Team Reality Check for Plans

**Author:** Simon Strandgaard  
**Date:** 2026-02-18  
**Status:** Proposal  
**Tags:** `red-team`, `verification`, `anti-sycophancy`, `quality`, `governance`

## Pitch
After PlanExe generates a draft plan, send it to a panel of external models that aggressively challenge assumptions, feasibility, timelines, costs, and hidden constraints. The goal is not polite feedback; the goal is stress testing under hostile scrutiny and measuring whether the original planner can defend valid reasoning or collapses into sycophantic agreement.

## Problem
A single-model plan can look coherent while being fragile.

Common failure modes:

- The planner overcommits with optimistic assumptions.
- The planner misses obvious real-world constraints.
- The planner folds too easily when challenged, or agrees with contradictory criticism.
- Users receive smooth prose instead of resilient plans.

Current outputs are under-tested against adversarial critique.

## Feasibility
This is feasible with existing PlanExe architecture:

- We already have structured artifacts and intermediate files.
- We already run multi-step workflows and can add post-generation stages.
- We can gate this feature behind speed/detail mode or an explicit parameter.

Constraints:

- Extra model calls increase cost and latency.
- Prompt design must avoid toxic output while preserving adversarial rigor.
- We need deterministic scoring so users can trust the result.

## Proposal
Add a post-generation red-team stage with 3 roles:

1. **Planner (Original):** the model that created the plan.
2. **Red Team Panel (External):** multiple different models/providers that challenge the plan.
3. **Judge (Arbiter):** a separate model that scores arguments for factual grounding, internal consistency, and realism.

Core behavior:

- Red-team prompts should explicitly include hard challenge language (for example, direct claims that the plan is unrealistic or unworkable) to trigger non-sycophantic behavior.
- The planner must respond with evidence-backed defense, partial concession, or revision proposals.
- The judge scores each exchange and records whether the planner:
  - defended correctly,
  - conceded correctly,
  - or agreed incorrectly (sycophancy failure).

## Workflow

1. Generate baseline plan (existing flow).
2. Build challenge packet:
   - assumptions
   - budget/timeline/resource claims
   - risk register summary
3. Run adversarial roundtable:
   - N red-team critiques (diverse models)
   - planner rebuttal to each critique
4. Run judge pass:
   - score each critique/rebuttal pair
   - identify collapses, contradictions, and unsupported agreement
5. Produce outputs:
   - revised plan sections (if needed)
   - red-team report
   - anti-sycophancy score

## Output Artifacts

- `redteam/challenges.json`
- `redteam/rebuttals.json`
- `redteam/judgments.json`
- `redteam/summary.md`
- `redteam/anti_sycophancy_score.json`

Include a user-facing summary in the report:

- “Most severe realism failures”
- “Where the planner stood firm and was correct”
- “Where the planner caved and was incorrect”
- “Required revisions before execution”

## Scoring Model

Suggested metrics:

- `realism_failure_count`
- `critical_assumption_invalidated_count`
- `unsupported_agreement_count` (primary anti-sycophancy metric)
- `defensible_pushback_count`
- `revision_impact_score` (how much of plan changed after challenge)

Aggregate:

- `plan_resilience_score` (0-100)
- `anti_sycophancy_score` (0-100)

## Integration Points

- Post-processing stage in `worker_plan_internal.plan.run_plan_pipeline`.
- Optional config in task parameters (for example: `redteam_mode`).
- Report generation pipeline to include red-team findings.
- MCP/file outputs for download and auditability.

## Phased Implementation

### Phase A: Minimal Red-Team Pass

- Add one external model challenge + one rebuttal + one judge.
- Emit basic summary and anti-sycophancy score.

### Phase B: Multi-Model Panel

- Expand to 3-5 challengers from different providers.
- Add disagreement clustering and contradiction detection.

### Phase C: Enforcement Mode

- Add optional gate: plans with resilience score below threshold are marked “needs revision” before user export.

## Success Metrics

- Reduction in downstream plan corrections after user review.
- Increase in detected unrealistic assumptions before execution.
- Stable anti-sycophancy metric across repeated adversarial prompts.
- User-rated trust improvement in final plans.

## Risks

- Overly aggressive red-team prompts may degrade quality if not controlled.
- Judge model can introduce bias or inconsistent scoring.
- Added latency may reduce usability for fast iterations.

Mitigations:

- Keep challenge style aggressive but policy-safe.
- Add rubric-based judging with structured outputs.
- Make red-team intensity configurable (`off`, `standard`, `aggressive`).

