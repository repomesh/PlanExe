---
title: Autoresearch-Style Autonomous Prompt Optimization
date: 2026-03-09
status: proposal
author: Simon Strandgaard (with Claude)
related: 59-prompt-optimizing-with-ab-testing.md, 07-elo-ranking.md
inspiration: https://github.com/karpathy/autoresearch
---

# Autoresearch-Style Autonomous Prompt Optimization

**Author:** Simon Strandgaard (with Claude)
**Date:** 2026-03-09
**Status:** Proposal
**Tags:** `prompting`, `automation`, `autoresearch`, `ab-testing`, `autonomous-agent`

---

## Pitch

Adapt the autoresearch pattern (Karpathy, 2026) for PlanExe: an autonomous agent that loops overnight, modifying prompt templates one at a time, regenerating only the affected Luigi task output, scoring the result, and keeping or reverting. Wake up to hundreds of tested prompt variants and a log of what worked.

This proposal complements proposal 59 (Prompt Optimizing with A/B Testing) by adding an autonomous exploration phase that feeds pre-tested candidates into the structured promotion pipeline.

## Background: The Autoresearch Pattern

Autoresearch is a tight autonomous improvement loop for ML training:

1. Agent modifies one file (`train.py`)
2. Runs a fixed 5-minute training experiment
3. Evaluates against a single metric (`val_bpb`)
4. Keeps the change if improved, reverts if not
5. Logs the result and repeats indefinitely

Key properties: single metric, fixed time budget, single modification scope, git-based versioning, no human in the loop during exploration.

## Why This Fits PlanExe

PlanExe's Luigi pipeline makes this pattern unusually practical for a document-generation system:

- **Luigi resumability**: Delete one task's output, re-run the pipeline, and only that task regenerates. Upstream tasks are cached. This turns a 15-minute, 60+ LLM call pipeline into a 1-20 LLM call experiment taking seconds to minutes.
- **Isolated prompt templates**: Each Luigi task has a self-contained prompt template. Changing one prompt is a single-variable experiment by construction.
- **Structured output**: Task outputs are JSON/Markdown with predictable structure, making automated scoring feasible.
- **Existing infrastructure**: Prompt corpora (`simple_plan_prompts.jsonl`), diagnostics modules, and the redline-gate pattern already provide building blocks.

## Proposal

### Two-Mode System

**Mode 1: Autonomous Exploration (autoresearch-style)**

An agent loops autonomously, proposing and testing prompt modifications at high volume. This is fast, greedy, and optimizes for discovery. Runs overnight or over weekends.

**Mode 2: Structured Promotion (proposal 59-style)**

Take the best candidates from exploration, run them through multi-model A/B testing with Elo tracking and regression guards before merging into the baseline. This is slow, conservative, and optimizes for trust.

Exploration feeds promotion. The agent surfaces candidates; the promotion pipeline validates them.

### The Exploration Loop

```
SETUP:
1. Run full pipeline once on N reference prompts (baseline)
2. Record baseline scores per task per prompt

LOOP:
1. Select a target Luigi task
2. Read the current prompt template and recent task outputs
3. Identify a weakness or improvement hypothesis
4. Modify the prompt template (one change only)
5. git commit with description of the hypothesis
6. For each reference prompt:
   a. Delete the target task's output file
   b. Re-run pipeline (Luigi regenerates only that task)
   c. Score the regenerated output
7. Compute average score delta vs baseline
8. If improved: keep commit, update baseline scores
9. If equal or worse: git revert, log failure mode
10. Append result to results.tsv
11. Go to 1
```

### Scoring: Per-Task Evaluation

Since only one task output changes per experiment, the LLM-as-judge problem is scoped to comparing two versions of a single document (e.g., two SWOT analyses, two risk registers). This is far more reliable than holistic plan scoring.

Per-task rubric (scored 1-10 by judge LLM):

- **Specificity**: Are items concrete and grounded in the project context?
- **Actionability**: Can someone act on this output directly?
- **Completeness**: Are obvious aspects covered without major gaps?
- **Internal consistency**: Does the output align with upstream pipeline context?
- **Conciseness**: Is the output free of filler and redundancy?

Composite score: weighted average, configurable per task type.

For additional robustness, use pairwise comparison ("Which version is better and why?") alongside absolute scoring to reduce judge bias.

### What the Agent Modifies

The agent modifies prompt templates inside Luigi task classes in `worker_plan_internal/`. Types of modifications:

- Rephrase instructions for clarity
- Add or remove constraints
- Change output structure requirements
- Adjust tone/specificity instructions
- Add few-shot examples
- Remove redundant instructions (simplification)

The agent should also be able to propose simplifications. Following the autoresearch principle: if removing lines produces equal or better output, the removal is an improvement.

### Reference Prompt Set

A fixed set of 3-5 diverse plan prompts used for all experiments:

- A simple personal project (e.g., "Organize a neighborhood cleanup day")
- A business venture (e.g., "Launch a B2B SaaS for invoice automation")
- A complex initiative (e.g., "Establish a regional renewable energy cooperative")
- An edge case (e.g., a vague or contradictory prompt)

These must be stable across all experiments to ensure comparability. Periodically refresh with a hidden holdout set to detect overfitting.

### Results Tracking

`results.tsv` — one row per experiment:

```
commit	task	avg_score	baseline_score	delta	status	description
a1b2c3d	SWOTAnalysisTask	7.8	7.2	+0.6	keep	added industry-specific angle constraint
d4e5f6g	ExpertReviewTask	6.5	6.9	-0.4	discard	over-constrained format reduced depth
```

### The program.md Equivalent

A Markdown file (e.g., `prompt_research_program.md`) that instructs the agent. The human iterates on this file to steer the agent's research strategy. Example contents:

```markdown
## Current Focus
Improve tasks in the strategic analysis stage (SWOT, Expert Review,
Premortem). These show the most variance in quality across prompts.

## Priorities
1. Reduce generic/boilerplate content in SWOT outputs
2. Improve risk specificity in Premortem task
3. Expert Review should reference upstream assumptions

## Constraints
- Do not modify prepare.py or pipeline structure
- One prompt change per experiment
- Always test on all reference prompts before deciding
- Keep prompt changes small and reversible

## What Has Worked
- Adding "be specific to this project, avoid generic advice"
  consistently improves scores
- Referencing upstream context (e.g., "given the assumptions above")
  improves consistency scores

## What Has Not Worked
- Adding many few-shot examples increases cost without clear benefit
- Over-constraining output format reduces depth
```

## Integration with Proposal 59

This proposal and proposal 59 serve different purposes in the same system:

| Aspect | This proposal (exploration) | Proposal 59 (promotion) |
|--------|---------------------------|------------------------|
| Goal | Discover promising variants | Validate and ship variants |
| Speed | Hundreds of experiments/night | Days per decision |
| Rigor | Greedy, single-metric | Multi-model, multi-domain, Elo |
| Agent role | Fully autonomous | Human-gated |
| Output | results.tsv + git history | Structured experiment artifacts |

Workflow: Exploration finds top candidates -> Promotion validates them -> Merge into baseline.

## Phased Implementation

### Phase 0: Minimal Loop (days)
- Target 1 Luigi task
- 1 reference prompt
- 1 LLM for generation, 1 for judging
- Simple score (single number from judge)
- `results.tsv` tracking
- Agent loops manually (human triggers each iteration)
- Goal: validate that the scoring signal is meaningful

### Phase 1: Autonomous Exploration (1-2 weeks)
- Expand to 3-5 reference prompts
- Agent loops autonomously with `program.md`-style instructions
- Git commit/revert workflow
- Cover 5-10 Luigi tasks
- Goal: first overnight run producing actionable results

### Phase 2: Multi-Task Coverage (weeks)
- Extend to all scorable Luigi tasks
- Task-specific rubrics
- Agent can choose which task to target based on score gaps
- Goal: systematic coverage of the full pipeline

### Phase 3: Connect to Promotion Pipeline
- Feed exploration winners into proposal 59's A/B matrix
- Multi-model validation before merging
- Elo tracking for long-term quality trends
- Goal: end-to-end prompt improvement pipeline

## Cost Considerations

Per experiment (1 task, 1 reference prompt):
- 1-20 LLM calls for regeneration (depending on task complexity)
- 1 LLM call for judge scoring
- Total: ~2-21 LLM calls

Per overnight run (assuming 3 reference prompts, 8 hours, ~2 min per experiment):
- ~240 experiments
- ~5,000-15,000 LLM calls
- Cost depends on model choice

Mitigation:
- Use cheaper models (e.g., Haiku) for exploration generation
- Use a stronger model (e.g., Opus) only for judging
- Validate winners with full-cost models in the promotion phase
- Start with Phase 0 to confirm signal before scaling up

## Risks

- **Judge instability**: LLM-as-judge scores may be noisy. Mitigate with pairwise comparison and averaging across reference prompts.
- **Overfitting to reference prompts**: Prompts may be optimized for the test set. Mitigate with periodic holdout refresh.
- **Simplification bias**: Agent may converge on shorter prompts that score well but lose nuance. Mitigate by including completeness in the rubric.
- **Cost runaway**: Overnight runs with expensive models add up. Mitigate by starting with cheap models and capping experiment count.
- **Cascading effects**: Improving one task's prompt may degrade downstream tasks that depended on the previous output style. Mitigate by scoring downstream tasks as well for kept changes.

## Open Questions

- Should the agent be allowed to modify pipeline structure (add/remove tasks), or only prompt templates?
- What is the minimum number of reference prompts needed for a reliable signal?
- Should exploration runs use the same LLM as production, or is a cheaper proxy acceptable?
- How do we detect and handle cascading effects on downstream tasks?
- Can the agent generate its own improvement hypotheses from analyzing low-scoring outputs, or should hypotheses come from the human-written program.md?

## Success Metrics

- Number of prompt improvements discovered and promoted per week
- Average quality score improvement across benchmark suite after promotion
- Reduction in human time spent on manual prompt iteration
- Stability of improvements across LLM providers (measured via proposal 59's multi-model testing)
