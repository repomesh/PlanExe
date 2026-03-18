# Lever Pipeline Implementation Memo

## Bottom line
The pipeline is well decomposed, but it compounds weak abstractions. It is good at generating plausible strategic surface area and then polishing it. It is not yet good enough at enforcing clean ontology, protecting methodological fundamentals, or correcting upstream mistakes before they become authoritative-looking output.

## 1. Core diagnosis
- The overall stage structure is sane: broad lever generation, consolidation, enrichment, prioritization, then downstream scenario and markdown synthesis.
- The biggest failure mode is inheritance: every downstream stage mostly trusts the previous stage instead of stress-testing it.
- The pipeline over-rewards levers that sound central in generated prose and under-rewards levers that are foundational for validity.
- Methodology levers, execution levers, governance levers, and communications levers are mixed together in one flat list.
- The markdown/report layer currently packages judgment errors instead of catching them.

## 2. Design principles for the next version
1. A lever should be a crisp decision variable, not a topic, workstream, or narrative bundle.
2. Deduplication should not only remove overlap; it should also re-level abstraction.
3. Methodological validity should outrank visibility, adoption, and communications when selecting the vital few.
4. Each stage should either add information or challenge the previous stage. Stages that only paraphrase are dangerous.
5. The pipeline should preserve reasons and provenance for why a lever survived, merged, split, or was demoted.

## 3. Stage-by-stage insights and implementation proposals

### 3.1 identify_potential_levers
**What the current stage gets right**
- It casts a wide net and produces many genuinely relevant candidate areas.
- It is good at surfacing second-order risks and tensions in the review field.
- It is better to over-generate here than to prematurely collapse the space.

**What is going wrong**
- The output mixes true strategic levers with product features, deliverables, stakeholder tactics, and workstreams.
- Several candidates are not real decision axes. They are clusters of partially related choices.
- Some levers are framed as options that are not mutually exclusive, which makes later ranking unstable.
- Important hidden levers are under-surfaced, especially governance/adjudication, uncertainty thresholds, prompt protocol design, data provenance/versioning, and misuse defense.

**Implementation proposals**
1. Add an explicit ontology output for each candidate: methodology, execution, governance, dissemination, product, or operations.
2. Require every candidate lever to declare a decision axis in one sentence using a forced template: “This lever controls X by choosing between A/B/C.”
3. Add a validation rule that rejects or flags candidates whose options are not mutually exclusive or that blend multiple axes.
4. Generate hidden missing-lever probes after the first pass. Ask specifically for omitted categories: governance, epistemic safeguards, release policy, red-teaming, measurement protocol, and reproducibility policy.
5. Store a structured `lever_type`, `decision_axis`, `option_exclusivity_score`, and `is_core_strategy_candidate` field in the JSON.

### 3.2 deduplicate_levers
**What the current stage gets right**
- It correctly prefers absorb over remove in many cases, which preserves useful detail.
- It often merges narrow variants into broader, better parent levers.
- It reduces obvious redundancy and makes the candidate set easier to reason about.

**What is going wrong**
- The stage is mostly literal overlap reduction. It does not ask whether a surviving item belongs at this strategic layer at all.
- It keeps too many downstream or presentation-oriented levers as first-class peers of methodological levers.
- It does not reliably split mushy levers before deduplicating them, so bad abstraction survives.
- The current keep-if-unsure behavior is safe, but it also preserves junk that should be demoted to another layer.

**Implementation proposals**
1. Rename the stage conceptually from deduplication to consolidation.
2. Perform three operations, not one: merge duplicates, split bundled levers, and demote out-of-layer levers.
3. Add an explicit classification decision for every item: keep-core, keep-secondary, absorb, split, or remove.
4. Require the stage to compare every lever against both individual levers and the emerging merged clusters.
5. Produce a machine-readable merge map so downstream stages know lineage, absorbed children, and rationale.

### 3.3 enrich_levers
**What the current stage gets right**
- It turns raw levers into objects that are readable and usable downstream.
- Descriptions, synergies, and conflicts help create report-friendly material.
- The additional fields are useful for human understanding and scenario composition.

**What is going wrong**
- The stage creates persuasive prose around levers whose abstraction may still be wrong.
- Generated synergy/conflict text is later treated as evidence of systemic centrality, which creates feedback loops built on invented structure.
- The stage enriches almost everything in the same way, even though different lever types need different enrichment.
- There is not enough explicit treatment of validity-critical fields such as uncertainty, measurement assumptions, failure conditions, and publication thresholds.

**Implementation proposals**
1. Separate narrative enrichment from structural enrichment. Narrative text is useful for reports; structural fields should drive decisions.
2. Add explicit fields that later stages can score directly: `foundationality`, `validity_risk`, `feasibility_risk`, `scope_impact`, `misuse_risk`, `governance_dependency`, and `reversibility`.
3. Generate `prerequisites`, `invalidates_if_wrong`, and `depends_on` fields instead of relying only on free-text synergy/conflict summaries.
4. Tailor enrichment by lever type. Methodology levers need epistemic-risk fields; execution levers need cost/coordination fields; dissemination levers need adoption/misuse fields.
5. Require a short “why this is not just a downstream consequence” statement for any lever still marked as core.

### 3.4 vital_few_levers
**What the current stage gets right**
- It forces prioritization instead of leaving everything equally important.
- It tries to use systemic leverage rather than simple surface importance.
- It is the first stage where the pipeline starts exposing its real strategic taste.

**What is going wrong**
- The stage currently over-relies on synergy/conflict prose, so levers that sound well-connected are promoted.
- Visibility, coordination, and outreach effects are overweighted relative to methodological necessity.
- Foundational but less rhetorically connected levers can be omitted even when they are crucial for validity.
- The stage picks one flat vital-few list even though the pipeline is mixing different kinds of levers.

**Implementation proposals**
1. Stop using prose centrality as the main proxy for importance. Use explicit scoring fields from enrichment.
2. Split selection into two passes: foundational core levers and secondary execution levers.
3. Add hard veto rules: a non-methodology lever cannot outrank a methodology lever when the methodology lever has higher foundationality and validity risk.
4. Penalize blurry levers with low decision-axis clarity.
5. Add an omission audit after selection: list the strongest excluded levers and explain why they did not make the cut.

## 4. Recommended vital-few scoring rubric
Use a weighted score that strongly favors validity and foundationality over rhetorical connectedness.
- Foundationality: 30%
- Validity risk if wrong: 25%
- Feasibility/scope constraint power: 15%
- Irreversibility / path dependence: 10%
- Governance or misuse dependency: 10%
- Connectivity: 10% maximum, and only from structured dependencies, not prose alone

Recommended selection logic:
1. Rank all keep-core levers by weighted score.
2. Force at least three methodology/governance levers into the top five unless the project is obviously non-methodological.
3. Then pick at most one or two execution/dissemination levers that materially change delivery or impact.
4. Finally run an omission check for any excluded lever with high foundationality or high validity risk.

## 5. Proposed pipeline changes
- Add `NormalizeLeverOntologyTask` between identify_potential_levers and consolidation.
- Replace `DeduplicateLeversTask` with `ConsolidateLeversTask` that supports merge, split, and demote.
- Add `ScoreLeverStructureTask` after enrichment to compute machine-usable scores.
- Replace `FocusOnVitalFewLeversTask` with `SelectFoundationalLeversTask` and `SelectExecutionLeversTask`.
- Add `AuditVitalFewSelectionTask` before markdown generation to catch missing fundamentals and over-selected downstream levers.

## 6. Suggested JSON schema changes
- `lever_type`: methodology | governance | execution | dissemination | product | operations
- `decision_axis`: short sentence describing the controllable choice
- `clarity_score`: 1-5 for how crisp the axis is
- `core_layer`: core | secondary
- `lineage`: parent lever id plus absorbed child ids
- `foundationality`, `validity_risk`, `feasibility_risk`, `misuse_risk`, `reversibility`
- `depends_on`, `prerequisites`, `invalidates_if_wrong`
- `selection_rationale`: compact machine-readable reason a lever survived or was excluded

## 7. Implementation order
1. First fix ontology and consolidation. This is the highest-leverage change.
2. Then change enrichment so it emits structural scoring fields rather than mostly prose.
3. Then redesign vital-few selection around foundationality and validity risk.
4. Only after that should report-generation prompts be revised, because presentation is not the core problem.

## 8. Practical acceptance criteria
- A bundled lever such as language prioritization is either split or rewritten into a crisp axis before enrichment.
- At least one governance or publication-threshold lever appears when the domain is politically sensitive or high stakes.
- The vital few list can explain why every omitted high-risk methodology lever was excluded.
- Downstream markdown cannot claim that no key dimensions are missing unless an omission audit passes.
- The same weak presentation-oriented lever should not repeatedly outrank foundational methodology levers across similar projects.

## 9. Final recommendation
Do not treat this as a prompt-tuning problem. The main issue is not wording quality. The main issue is stage responsibility. The early stages need tighter ontology discipline, the middle stages need structural rather than rhetorical enrichment, and the prioritization stage needs to reward validity-preserving decisions more than influential-looking prose. Fix that branch, and a large share of the downstream plan quality should improve automatically.
