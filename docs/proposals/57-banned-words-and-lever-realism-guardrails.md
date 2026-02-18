---
title: Banned Words and Lever Realism Guardrails
date: 2026-02-18
status: proposal
author: Simon Strandgaard
---

# Banned Words and Lever Realism Guardrails

**Author:** Simon Strandgaard  
**Date:** 2026-02-18  
**Status:** Proposal  
**Tags:** `prompting`, `realism`, `guardrails`, `scenario-selection`, `quality`

## Pitch
Make “banned words” and “no-hype constraints” a first-class part of planning so users no longer need to manually append lines like `Banned words: blockchain, VR, AR, AI, DAO, Robots.` to get practical plans on small budgets.

Also add a post-lever sanity check: if selected strategic levers are too extreme or experimental for budget/timeline/context, automatically regenerate with less optimistic settings.

Critical rule: if the user explicitly asks for a term (for example blockchain), allow it and do not silently suppress it.

## Problem
Today the model can drift toward buzzword-heavy, high-uncertainty strategies (for example blockchain/VR/AR/DAO-heavy ideas) even when the user needs low-risk execution.

Current behavior issues:

- Users repeatedly patch prompts manually with banned-word lists.
- Lever selection can choose “moonshot” settings that are inconsistent with budget/time constraints.
- Scenario outputs sometimes feel impressive but are impractical.
- Practical intents (for example house renovation or normal business setup) still get hype-heavy recommendations that users did not ask for.

Evidence already exists in prompt data:

- `worker_plan/worker_plan_api/prompt/data/simple_plan_prompts.jsonl` includes multiple prompts that explicitly add banned words and realism hints.


## Additional Motivation: “Bizarre Plan” Stress Tests

Comparing extreme or bizarre plans is a useful diagnostic for guardrails: it makes failure modes obvious that templates and buzzwords can hide.

Common cross-domain failure patterns surfaced by stress tests:

- **Social license / legitimacy dominates**: plans can be “technically coherent” while being politically/ethically non-viable.
- **Primary failure mode is usually not the tech**: e.g., donor/consent pipelines, accountability, sovereignty, cultural acceptability.
- **Template-bullshit is easy to spot**: repeated phrases like “engage stakeholders” without a compliant pathway, decision rights, or go/no-go gates.
- **Internal contradictions**: executive targets that don’t match the Gantt, or “18 months after event” plans anchored to fixed calendar dates.

This proposal should therefore guard against *both* (a) hype-term drift and (b) unrealistic leverage choices that ignore legitimacy, incentives, and execution constraints.

## Feasibility
This is feasible with incremental changes:

- Prompt parser can extract banned words and realism preferences into structured constraints.
- Scenario/lever selection already has a decision stage where we can run checks and retries.
- Existing self-audit patterns can be reused for realism scoring.

Constraints:

- Must not over-block legitimate domain usage (example: “AI safety policy” as topic).
- Must be transparent about why a lever was rejected.
- Must avoid endless retry loops.

## Proposal
Introduce two linked controls:

1. **Banned Words Policy (input-time)**
2. **Lever Realism Backoff Loop (post-selection)**

### 1) Banned Words Policy (Input-Time)

Add structured constraint fields to planning input:

- `banned_words: string[]`
- `style_mode: "practical" | "balanced" | "experimental"`
- `risk_tolerance: "low" | "medium" | "high"`

Behavior:

- If user provides explicit banned words, enforce them.
- If missing and budget/timeline implies practicality, apply a default soft blocklist profile.
- Banned terms are blocked in recommended strategy language unless user explicitly overrides.
- If the user explicitly requests a normally blocked term (example: “use blockchain”), that explicit intent wins and the term is allowed.

Precedence order:

1. User explicit include request (highest).
2. User explicit banned words.
3. System default profile from context (lowest).

Profiles (example):

Add a **red-flag phrase list** (warn-only, not hard-block) to catch credibility killers like:

- “loopholes”, “jurisdictional arbitrage”, “mandatory adoption”, “no human control”, “fully autonomous governance”

These phrases should trigger an explanation and a realism downgrade unless the user explicitly wants that posture.


- `practical_small_budget`: `blockchain`, `NFT`, `DAO`, `VR`, `AR`, `metaverse` (and related hype terms)
- `practical_everyday`: default for intents like home renovation, small local business launch, routine operations upgrades; strongly suppresses hype terms unless explicitly requested
- `balanced`: warn-only
- `experimental`: no default blocklist

### 2) Lever Realism Backoff Loop (Post-Selection)

After lever/scenario selection, run a realism gate:

- Score each selected lever for:
  - implementation maturity
  - regulatory complexity
  - dependency burden
  - capex/opex fit to budget
  - delivery fit to timeline
  - **social license / legitimacy risk** (public acceptability, political feasibility)
  - **incentive compatibility** (coercion/exploitation risk, perverse incentives)
  - **accountability & reversibility** (who can stop/rollback, incident response)

If score fails threshold:

1. Mark offending levers as “too extreme”.


Additional “Reality Gate” checks (run before or alongside scoring):

- **Category impossibility flags:** detect goals that are structurally unlikely within the timeframe (e.g., “mandatory adoption by major governments by end of year”).
- **Internal consistency checks:** ensure executive summary dates match the Gantt and dependencies; reject contradictory schedules.
- **Legal pathway clarity:** require a primary compliant route *plus* 1–2 explicit fallbacks; penalize “loophole-first” strategies.
- **Decision-rights clarity:** require named owners/authorities for approvals, overrides, and incident response (especially for governance/medical domains).
- **Go/No-Go gates:** require explicit stop/pivot conditions tied to measurable thresholds (approval, safety, sentiment, funding).

When these checks fail, prefer regenerating with narrower scope, softer claims, and clearer governance rather than adding more “advanced tech”.

2. Re-run lever selection with stricter constraints.
3. Limit retries (example: max 2 backoff rounds).
4. Emit explanation in report (“why previous lever set was rejected”).

## Integration Points

- Prompt ingestion and normalization in `worker_plan_internal` prompt pipeline.
- Scenario/lever selection stage (where strategic scenarios are generated and chosen).
- Report generator to show:
  - active banned words
  - lever sanity-check decisions
  - fallback/backoff reasoning.

## Data and Output Artifacts

Add optional artifacts:

- `constraints/banned_words.json`
- `constraints/realism_profile.json`
- `scenario/lever_sanity_checks.json`
- `scenario/lever_backoff_history.json`

Report section:

- “Practicality Guardrails Applied”
- “Rejected Experimental Levers”
- “Final Lever Set and Why It Passed”

## Phased Implementation

### Phase A: Parse + Enforce Banned Words

- Parse banned words from prompt and/or config.
- Prevent banned terms in generated strategy recommendations.
- Show active constraints in output metadata.

### Phase B: Lever Realism Gate

- Add realism scoring for selected levers.
- Add single backoff retry when score fails.

### Phase C: Adaptive Profiles

- Add budget/timeline-aware default profiles.
- Add explainability output and governance metrics.

## Success Metrics

- Reduced frequency of manually added “Banned words:” in user prompts.
- Lower rate of unrealistic lever recommendations for low-budget plans.
- Lower rate of unsolicited hype-tech suggestions in practical-intent plans (business basics, renovation, operations).
- Increased user rating for practicality and implementability.
- Fewer post-generation rewrites to remove hype/experimental features.
- Lower rate of plans with **executive/Gantt date contradictions**.
- Higher rate of outputs that include **primary compliant pathway + fallbacks + go/no-go gates** when the domain is sensitive.

## Risks

- Overly strict blocks can suppress valid innovation.
- False positives on terms with legitimate context.
- Backoff loop can increase latency.

Mitigations:

- Separate hard-block vs warn-only profiles.
- Allow explicit user override (`allow_experimental_terms=true`).
- Keep backoff rounds bounded and observable.
