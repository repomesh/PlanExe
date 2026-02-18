---
title: Prompt Optimizing with A/B Testing
date: 2026-02-18
status: proposal
author: Simon Strandgaard
---

# Prompt Optimizing with A/B Testing

**Author:** Simon Strandgaard  
**Date:** 2026-02-18  
**Status:** Proposal  
**Tags:** `prompting`, `ab-testing`, `evaluation`, `quality`, `automation`

---

## Pitch
Build a repeatable A/B testing system for system-prompt optimization so PlanExe can improve prompts with evidence, not manual taste.

The target is small, controlled prompt edits, measured against baseline across many plan prompts and multiple LLMs, then automatic promotion only when improvements are consistent.

## Problem
Prompt tuning is currently manual and expensive:

- A human creates prompt variants (often via ChatGPT, Gemini, Grok), runs attempts, and inspects outputs.
- `worker_plan_internal/diagnostics/redline_gate.py` already shows this pattern: multiple candidate system prompts, pairwise comparisons, and manual selection.
- Humans cannot reliably detect which prompt variant consistently wins across many tasks and model providers.
- A variant that looks better on one run can regress quality on other domains.

Result: prompt changes are hard to trust, hard to reproduce, and slow to iterate.

## Feasibility
This is feasible with existing building blocks:

- Prompt corpora already exist (`simple_plan_prompts.jsonl` and MCP prompt examples).
- PlanExe pipeline already emits many intermediate artifacts that can be scored.
- Redline-gate code already demonstrates multi-prompt evaluation mechanics.
- Existing diagnostics/self-audit modules can provide objective checks.

Constraints:

- Full-plan runs are costly; experiments must support stratified sampling.
- Model variance is high; evaluation must run across multiple providers/models.
- Promotion must be conservative to avoid silent quality regressions.

## Proposal
Add a **Prompt Experiment Harness** for controlled A/B tests.

Core rules:

- Change one system prompt at a time (single-variable experiments).
- Keep baseline prompt fixed and versioned in git.
- Run paired A/B on identical input sets.
- Evaluate with objective checks first, then judge-model scoring.
- Promote only if win criteria are met across domains and models.

## Experiment Workflow
1. Select target prompt in pipeline (earliest stage linked to observed weakness).
2. Define baseline prompt version and one candidate variant.
3. Build test set:
   - curated prompt suite (easy/medium/hard, multiple domains)
   - stress tests and edge cases
4. Run A/B matrix:
   - same inputs
   - same config
   - multiple LLMs/reasoning models
5. Score outcomes with fixed rubric.
6. Compute win/loss/draw and confidence.
7. Promote candidate only when thresholds pass.
8. Store artifacts and decision log in repo.

## Scoring Framework
Use a weighted composite score per run:

- realism/feasibility
- internal consistency (no contradictions between summary, schedule, risks)
- constraint adherence (budget, timeline, location)
- safety/compliance behavior
- actionability (clear next steps and ownership)

Recommended approach:

- Objective checks: schema validity, contradiction flags, missing-core-sections.
- Judge scoring: LLM-as-judge with fixed rubric and pairwise comparison.
- Tie-breakers: lower hallucination risk and better constraint fidelity.

Also include an Elo-based relative quality signal (see `docs/proposals/07-elo-ranking.md`) so we measure whether a candidate prompt shifts plan quality up or down against corpus peers, not only against one baseline pair.

## Elo Integration
Use Elo as a secondary decision layer for prompt promotion.

How:

- For each A/B run, rank produced plans with the existing pairwise KPI-to-Elo method.
- Compute `elo_delta` for candidate-generated plans versus baseline-generated plans.
- Track short-term experiment win rate and medium-term Elo trend.

Promotion guard:

- Candidate must win the local A/B matrix.
- Candidate must also show non-negative (preferably positive) Elo movement on holdout slices.
- Any persistent negative Elo drift blocks promotion even if small-sample A/B looks positive.

## Redline-Gate-Inspired Pattern
Adopt the proven pattern from `worker_plan_internal/diagnostics/redline_gate.py`:

- Keep several system-prompt candidates.
- Run the same user prompts against each candidate.
- Compare outcomes in bulk, not one-by-one.

Generalize this pattern to the full planning pipeline:

- not only safety classification prompts
- also planning, assumptions, lever selection, and review prompts

## Candidate Generation
Support assisted prompt drafting while keeping evaluation strict.

Allowed sources for new variants:

- human-written edits
- AI-assisted edits (ChatGPT, Gemini, Grok, etc.)
- templated rewrites from internal rules

Requirement:

- each candidate must include a short changelog (what changed and intended effect)
- no promotion without A/B evidence

## Integration Points
- Prompt definitions in `worker_plan_internal/*` modules.
- Diagnostics harness under `worker_plan_internal/diagnostics/`.
- Prompt datasets in `worker_plan/worker_plan_api/prompt/data/`.
- Report/log layer for experiment metadata and decisions.
- Elo ranking components and data flow described in `docs/proposals/07-elo-ranking.md`.

Suggested artifacts:

- `experiments/prompt_ab/<experiment_id>/config.json`
- `experiments/prompt_ab/<experiment_id>/runs.jsonl`
- `experiments/prompt_ab/<experiment_id>/scores.jsonl`
- `experiments/prompt_ab/<experiment_id>/decision.md`
- `experiments/prompt_ab/<experiment_id>/elo_summary.json`

## Promotion Policy
Promote candidate prompt only when all pass:

- net positive win rate over baseline on full test matrix
- no critical regressions on safety/compliance checks
- consistent gains on at least two model families
- statistically credible margin (configured confidence threshold)
- non-negative Elo trend on holdout and benchmark slices

If not promoted:

- keep baseline
- log failure mode
- schedule next micro-iteration for the same weakness

## Phased Implementation
### Phase A: Minimal Harness
- A/B runner for one prompt target.
- Paired inputs and simple win/loss metrics.
- Manual review report output.

### Phase B: Multi-Model Robustness
- Add cross-model matrix and stratified prompt sets.
- Add confidence intervals and regression guards.

### Phase C: Promotion Automation
- Auto-create candidate branches/PR notes with experiment summary.
- Require explicit promotion gate before baseline replacement.

### Phase D: Continuous Improvement Loop
- Weekly or per-release prompt experiment batch.
- Track long-term drift and rollback when needed.

## Success Metrics
- Higher average plan quality score versus baseline across benchmark suite.
- Lower variance in quality across models/providers.
- Reduced manual time spent on prompt trial-and-error.
- Fewer regressions after prompt updates.
- Faster cycle time from weakness discovery to tested prompt improvement.
- Positive median `elo_delta` after prompt promotion windows.

## Risks
- Overfitting to benchmark prompts instead of real traffic.
- Judge-model bias or instability.
- High experiment cost (tokens, runtime).
- Metric gaming (improving score without real output quality gains).

Mitigations:

- Keep hidden holdout sets and periodically refresh benchmarks.
- Use multiple judges and objective checks together.
- Start with low-cost slices before full-matrix runs.
- Include human spot-check audits on promoted variants.

## Open Questions
- Which score dimensions should be hard gates vs soft preferences?
- How much statistical confidence is required for promotion?
- Should promotions be fully automatic or always human-approved?
- What Elo horizon should be used for rollback (for example 7-day vs 30-day drift)?
