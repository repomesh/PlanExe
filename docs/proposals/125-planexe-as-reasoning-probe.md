---
title: "PlanExe as a Reasoning Probe: Structured Decomposition Beyond Business Planning"
date: 2026-03-26
status: Proposal
author: EgonBot
---

# PlanExe as a Reasoning Probe: Structured Decomposition Beyond Business Planning

**Author:** EgonBot  
**Date:** 2026-03-26  
**Status:** Proposal  
**Tags:** `reasoning`, `diagnostics`, `arc-agi`, `abstraction`, `meta-planning`

---

## Pitch

PlanExe's 63-task pipeline is not primarily a plan generator — it is an instrument for studying how language models reason about complex, ambiguous problems. This proposal reframes PlanExe's development around its diagnostic capability and proposes extending it toward exploration planning, connecting Simon's ARC work with PlanExe's structured decomposition.

## Problem

PlanExe is currently framed as a business/project planning tool. This framing undersells what it actually does and misdirects development toward "better plans" rather than the more valuable outcome: **better understanding of where and how model reasoning breaks down.**

Observations:

- Simon runs different models (GLM, Qwen, Claude) through the same pipeline and compares outputs — this is empirical research, not product usage.
- Tasks like `ReviewPlanTask` (16 Q&A turns) and `PremiseAttackTask` stress-test specific reasoning capabilities; the plan output is secondary to the diagnostic signal.
- The pipeline's value scales with model diversity, not with plan quality. A "perfect" plan from Claude is less interesting than a revealing failure from a local model.
- ARC-AGI (1, 2, 3) and PlanExe share the same deep structure: measure the efficiency with which a system converts ambiguous input into structured output.

## The Thread Through Simon's Work

| Project | Input | Output | Core Operation |
|---------|-------|--------|----------------|
| LODA | Integer sequence | Minimal assembly program | Program synthesis via search |
| ARC tasks | Grid examples | Transformation rule | Abstraction from examples |
| ARC-Interactive | 117 puzzles + human data | Human reasoning patterns | Measuring human abstraction |
| PlanExe | Vague natural language goal | 63-task structured plan | Decomposition of ambiguity |

The common operation: **find the minimal structured description that captures the full problem.** Chollet's intelligence metric — skill acquisition efficiency — measures exactly this capability.

## What ARC-AGI-3 Revealed

On March 25-26, 2026, two AI agents (Bubba and Egon) attempted three ARC-AGI-3 games blind. Results:

- **RE86:** ~200 actions, 0 levels. Mapped controls but could not identify win condition.
- **VC33:** 13 actions, 2/7 levels. Partially understood the bar-adjustment mechanic.
- **S5I5:** ~50 actions, 0 levels. Mapped two-piece control system, could not trigger completion.
- Human baseline for RE86 Level 1: **28 actions.**

### Why the agents failed

1. **No exploration structure.** Actions were chosen reactively, not to maximize information gain.
2. **Redundant experiments.** Multiple actions tested the same hypothesis; no disambiguation strategy.
3. **State tracking loss.** Piece positions were forgotten between observations.
4. **Confirmation bias.** Both agents agreed on wrong hypotheses and reinforced each other's errors instead of challenging them.

These are failures of **meta-planning** — the agents could not plan their own learning process. They had tools (full API access, grid state data) but no structured approach to using them.

## Proposal

### 1. Formalize PlanExe's Diagnostic Role

Add pipeline instrumentation that captures WHERE models struggle:

- **Per-task difficulty scoring:** measure response time, retry count, and output coherence for each of the 63 tasks across models.
- **Failure taxonomy:** classify HOW each task fails (hallucination, logical contradiction, scope drift, structural collapse, etc.).
- **Cross-model comparison views:** standardized output that shows the same prompt's decomposition across 3+ models side-by-side.

This makes explicit what Simon already does informally: use the pipeline as a diagnostic instrument.

### 2. Exploration Planning Mode

Add a new pipeline mode — `--mode explore` — that generates a structured exploration protocol instead of a business plan:

- **Input:** description of an unknown system (environment, API, dataset, codebase)
- **Output:** structured sequence of experiments designed to maximize information gain with minimum actions

The exploration pipeline would include tasks like:

- `InventoryTask` — enumerate observable elements before taking any action (cost: 0 actions)
- `ActionMappingTask` — design minimum-cost experiments to determine what each action does
- `HypothesisGenerationTask` — generate competing hypotheses from observations
- `DisambiguationTask` — for each hypothesis pair, find the single experiment that distinguishes them
- `WorldModelTask` — maintain and update a structured representation of the system

### 3. Lever Identification for Exploration

Apply Simon's lever identification concept to the exploration process itself:

- **Which experiment eliminates the most uncertainty?** (maximum information gain per action)
- **Which unknown, if resolved, would unlock the most downstream progress?** (dependency-aware exploration)
- **Which hypothesis, if wrong, would waste the most future actions?** (risk-weighted disambiguation)

This directly connects PlanExe's lever work to Chollet's intelligence-as-efficiency framework.

## Feasibility

**Phase 1 (diagnostic instrumentation):** Low risk. Adds logging and comparison views to existing pipeline. No architectural changes. Can ship incrementally.

**Phase 2 (exploration mode):** Medium risk. Requires new task definitions but uses existing pipeline infrastructure. The ARC-AGI-3 toolkit provides a ready-made test environment.

**Phase 3 (lever identification for exploration):** High risk, research-grade. Requires formalizing "information gain per action" in a way that works across domains. Active learning literature provides prior art.

**Hard dependency:** Phase 2 requires a feedback loop (take action → observe → update plan). PlanExe currently generates plans but does not execute them. MCP integration or agent-loop wrapper needed.

## Success Metrics

- **Phase 1:** Per-task failure taxonomy covering ≥80% of observed failure modes. Cross-model comparison for ≥3 model families.
- **Phase 2:** Structured exploration protocol that, when executed against ARC-AGI-3 games, achieves first-level completion in fewer actions than ad-hoc play. Baseline: our March 25-26 session data.
- **Phase 3:** Information-gain-per-action metric that correlates with exploration efficiency (r > 0.5) across ≥3 different unknown environments.

## Risks

- **Over-abstraction:** The "PlanExe as instrument" framing could lead to building dashboards nobody uses. Mitigation: every diagnostic feature must be motivated by a specific question Simon has asked about model behavior.
- **Exploration mode scope creep:** "Plan your own learning" is a PhD thesis, not a feature. Mitigation: Phase 2 is bounded to the ARC-AGI-3 game format (finite actions, grid state, clear win condition). Generalization is Phase 3.
- **Chollet framework mismatch:** Intelligence-as-efficiency may not map cleanly to planning tasks. Mitigation: define PlanExe-specific efficiency metrics before claiming Chollet alignment.

## Connection to ARC-AGI-3

If Phase 2 succeeds, PlanExe becomes a tool for generating exploration strategies that could be tested against ARC-AGI-3 games. This creates a concrete, measurable link between PlanExe's structured decomposition and the ARC Prize Foundation's benchmark — the same benchmark Simon has contributed to since ARC-AGI-1.

The experiment: give PlanExe's exploration mode an ARC-AGI-3 game description ("unknown grid environment, 5 available actions, 64x64 state, goal unknown"). Execute the generated protocol. Compare actions-to-first-level against human baselines and our ad-hoc attempts.

---

## Open Questions for Simon

1. Is the diagnostic/instrument framing accurate to how you think about PlanExe, or are we projecting?
2. Does the exploration planning mode align with where you see PlanExe going?
3. Which of the three phases is most interesting to you?
4. Are there aspects of your motivation for PlanExe that we're completely missing?
