# Proposal 122: Deduplicate Levers — Architecture and Improvements

## Status

**Current state**: PR #375 merged (2026-03-21). Single batch call with
primary/secondary/remove taxonomy. 3x faster than baseline, all models
complete successfully. Best iteration: 52.

**This proposal**: documents the iteration journey, known issues, and
future improvement directions for the deduplicate_levers step.

---

## Pipeline Context

DeduplicateLevers is step 2 in a 6-step solution-space exploration pipeline:

1. **IdentifyPotentialLevers** — brainstorms 15-20 raw levers
2. **DeduplicateLevers** ← this step
3. **EnrichLevers** — adds description, synergy, and conflict text
4. **FocusOnVitalFewLevers** — filters down to 4-6 high-impact levers
5. **ScenarioGeneration** — builds 3 scenarios (aggressive, medium, safe)
6. **ScenarioSelection** — picks the best-fitting scenario

Step 1 intentionally over-generates. This step removes near-duplicates,
filters irrelevant levers, and tags survivors as primary (strategic) or
secondary (operational). Step 4 handles further filtering.

---

## Iteration History (iter 44-52)

Nine iterations across five PRs to reach the current state.

| Iter | PR | Architecture | Taxonomy | Verdict | Key insight |
|------|-----|-------------|----------|---------|-------------|
| 48 | — | 18 sequential calls | keep/absorb/remove | BASELINE | llama3.1 collapsed 7 levers into "Risk Framing" |
| 45 | #365 | 18 sequential calls | primary/secondary/absorb/remove (4-way) | YES (5/7) | Primary/secondary triage is the real quality gain. `remove` dead when `absorb` exists |
| 49 | #372 | 18 sequential calls | primary/secondary/remove (3-way) | YES | All 3 categories exercised. Template-lock identified |
| 50 | #373 | 1 batch call | Likert scoring (-2 to +2) | REVERT | Relevance != deduplication. llama3.1 inverted the scale |
| 51 | #374 | 1 batch call | primary/secondary/remove | YES | Batch + categorical works. llama3.1 timed out 2/5 plans |
| 52 | #375 | 1 batch call | primary/secondary/remove | YES (merged) | Shorter justifications fixed llama3.1 timeout |

### What moved the needle

1. **Single batch call** (iter 50-52): 18 calls → 1. 3x faster, no
   position bias, global consistency, simpler code (190 vs 330 lines).

2. **Primary/secondary triage** (iter 45+): New downstream signal. Main
   branch only had `keep` — no prioritization information.

3. **Shorter justifications** (iter 52): ~20-30 words instead of ~40-80.
   Fixed llama3.1 timeout, API models 55% shorter and 25% faster.

### What didn't move the needle

- **Taxonomy label changes**: Renaming keep→primary, absorb→remove produced
  nearly identical results. Labels are interchangeable.
- **Anti-template-lock instructions**: Not needed with short categorical labels.
- **Calibration hints**: Models that remove aggressively do so regardless.
  Conservative models ignore calibration guidance.

### Current metrics (iter 52 vs baseline)

| Metric | Baseline (iter 48) | Current (iter 52) |
|--------|-------------------|-------------------|
| Architecture | 18 sequential calls | 1 batch call |
| Taxonomy | keep/absorb/remove | primary/secondary/remove |
| Triage signal | None | primary 54% / secondary 31% |
| Avg kept | 13.9 / 18 | 15.6 / 18 |
| Avg removed | 4.1 / 18 (23%) | 2.4 / 18 (15%) |
| Avg duration | 120.5s | 40.3s |
| llama3.1 failures | Collapse into "Risk Framing" | None |

---

## Known Issues

### Structural issues

#### 1. The step conflates deduplication with prioritization

The current schema asks the LLM to make two decisions at once:
- Whether a lever survives deduplication (keep vs remove)
- Whether a surviving lever is strategically important (primary vs secondary)

A lever can be clearly distinct but low priority, or highly important but
partly redundant with another broader lever. By fusing these decisions,
the step creates a bias toward keeping anything that seems important, even
if it overlaps heavily with another lever.

The step drifts toward "strategic triage" rather than real overlap reduction.

#### 2. No explicit absorption structure

When a lever is removed, only a freeform justification is stored. There is
no structured `absorbed_into` field. The pipeline loses information about
which surviving lever subsumed the removed one.

Without absorption links:
- You cannot audit whether removal was correct
- You cannot detect hierarchy reversals (narrow lever kept, general removed)
- You cannot detect chain absorptions (A→B→C where B is also removed)
- Later stages cannot recover wording or evidence from removed items

#### 3. The retention bias is strong

The uncertainty rules produce predictable skew:
- Uncertain between primary and secondary → primary (promotes)
- Uncertain between keep and remove → secondary (keeps)
- Missing decisions → secondary (keeps)

The model is rewarded for being vague. The step becomes a low-risk
classifier instead of a real deduplicator.

#### 4. No survivor-overlap validation

No post-check asks whether surviving items still overlap heavily. Two
survivors might be different phrasings of the same lever, or policy,
procurement, and standards variants of one underlying mechanism.

#### 5. No category balance awareness

The flat comparison setup encourages the model to favor narratively vivid
levers (creative, character, thematic) over less glamorous but equally
critical ones (financing, legal, operations, distribution).

#### 6. Single-batch reasoning is useful but brittle

One batch call gives global context, but one bad completion corrupts the
whole output. There is no repair pass for missing IDs, suspicious
distributions, or ambiguous overlap clusters.

### Implementation issues

#### 7. Silent failure masking

When the LLM call times out, `batch_result` stays `None`, all levers
default to secondary, and `outputs.jsonl` records `status=ok` with
`calls_succeeded=1`. Monitoring pipelines cannot detect these failures.

#### 8. `user_prompt` field stores wrong value

`user_prompt=project_context` at line 272 stores the plan description, not
the full assembled prompt including the levers JSON. The saved artifact
cannot reconstruct the exact LLM input.

#### 9. `calls_succeeded` hardcoded

`runner.py` returns `calls_succeeded=1` regardless of whether the LLM call
succeeded or the fallback fired.

#### 10. Minimum count threshold is too low

`max(3, len(input_levers) // 4)` = 4 for 18 levers. A model removing 14/18
still clears the warning. Consider `max(5, len(input_levers) // 3)`.

---

## Improvement Proposals

### Option A: Incremental improvements (low risk)

Keep the current single-call architecture and taxonomy. Fix implementation
issues and add validation.

**Changes:**
1. Add `absorbed_into: str | None` field to `LeverClassificationDecision`.
   Required when classification is `remove` and the lever overlaps another.
   Enables merge-graph validation.

2. Add `remove_reason: Literal["duplicate", "subset", "irrelevant", "too_narrow"]`
   to make removals auditable and categorized.

3. Add a survivor-overlap validation pass. After the main classification,
   compute similarity between surviving levers (by name/consequences overlap).
   If two survivors are suspiciously similar, log a warning or trigger a
   focused comparison.

4. Replace `missing → secondary` with `missing → unresolved`. Send unresolved
   items through a focused repair call rather than silently keeping them.

5. Fix observability: expose `llm_call_succeeded` from `DeduplicateLevers`,
   emit `classification_fallback` events in `events.jsonl`, fix `user_prompt`
   field, make `calls_succeeded` reflect reality.

6. Add calibration checks: warn if >70% survive (likely under-dedup) or
   <35% survive (likely over-removal). Optionally trigger a repair pass.

**Effort**: Medium. Each change is independent and can be shipped separately.

### Option B: Two-pass architecture (medium risk)

Separate deduplication from prioritization into distinct passes.

**Pass 1 — Overlap resolution:**
- Decisions: `keep` / `absorb` / `remove`
- Only answers: does this lever survive as a distinct concept?
- Requires `absorbed_into` for absorb decisions

**Pass 2 — Prioritization of survivors:**
- Decisions: `primary` / `secondary`
- Only answers: among surviving levers, which are top-level strategic?

**Benefits:**
- Cleaner separation of concerns
- Deduplication quality not contaminated by importance assessment
- Each pass is simpler for the LLM

**Risks:**
- Two LLM calls instead of one (cost, latency)
- More complex orchestration
- Pass 2 may disagree with pass 1's keep decisions

**Effort**: High. New schemas, two-call orchestration, compatibility with
existing runner and analysis pipeline.

### Option C: Cluster-based deduplication (higher risk)

Instead of item-level labels, first cluster semantically similar levers,
then pick representatives within each cluster.

**Step 1**: Group all levers into semantic clusters in one call.
**Step 2**: For each cluster with >1 lever, pick the canonical representative.
Tag as primary/secondary. Mark others as absorbed.

**Output shape:**
```json
{
  "cluster_id": "procurement-conditions",
  "canonical": "Procurement Conditionality",
  "absorbed": [
    {
      "lever_id": "...",
      "reason": "near_duplicate",
      "absorbed_into": "Procurement Conditionality"
    }
  ]
}
```

**Benefits:**
- Most interpretable output
- Natural absorption structure
- Explicit nearest-neighbor reasoning within clusters

**Risks:**
- Most implementation work
- Clustering quality depends on model capability
- Output schema change affects downstream consumers

**Effort**: High. New clustering schema, new orchestration, downstream
consumer updates.

### Option D: Mechanism-based deduplication (research)

Force the model to decompose each lever into structured fields before
deduplicating:

- Target actor
- Intervention mechanism
- Expected effect
- Time horizon
- Implementation domain

Then deduplicate primarily on mechanism + actor + effect, not just
semantic similarity. This would reduce both false merges (same topic,
different mechanism) and false splits (different wording, same mechanism).

**Benefits:**
- Most principled approach to deduplication
- Catches "sounds similar but different mechanism" false merges

**Risks:**
- Significantly more output per lever (structured decomposition)
- May exceed token budgets for weak models
- Research-grade — untested in this pipeline

**Effort**: Very high. New decomposition schema, new comparison logic,
likely two calls minimum.

---

## Recommendation

### Near-term (next 1-2 iterations)

Implement Option A items 1-2 and 5:
- Add `absorbed_into` field for auditable removal
- Add `remove_reason` categorization
- Fix observability (silent failure masking, `user_prompt`, `calls_succeeded`)

These are low-risk, independent changes that make the step more inspectable
without changing its behavior.

### Medium-term (next 3-5 iterations)

Implement Option A items 3-4 and 6:
- Survivor-overlap validation pass
- Replace `missing → secondary` with `missing → unresolved` + repair
- Calibration checks with optional second pass

### Long-term (future consideration)

Evaluate Option B (two-pass) or Option C (cluster-based) based on whether
the incremental improvements are sufficient. The current single-call
architecture may hit a quality ceiling where one LLM call cannot reliably
do both overlap detection and prioritization well. If that happens, Option B
is the natural next step.

Option D (mechanism-based) is interesting but too expensive for the current
model roster. Worth revisiting when cheaper structured-output models become
available.

---

## Lessons Learned

### From 9 iterations of optimization

1. **Architecture matters more than taxonomy.** Changing labels (keep vs
   primary, absorb vs remove) across 5 iterations produced nearly identical
   results. Changing from 18 sequential calls to 1 batch call produced a
   3x speedup and eliminated position bias.

2. **Relevance and deduplication are different questions.** A lever can be
   highly relevant to the plan AND fully redundant with another lever.
   Asking "how relevant?" (iter 50, Likert scoring) produced 0% removal
   for capable models. Asking "is this redundant?" (iter 51-52, categorical)
   restored deduplication.

3. **Integer scales can be inverted; categorical labels cannot.** llama3.1
   scored 17/18 levers as -2 while writing "highly relevant" in
   justifications. This failure mode is structurally impossible with
   categorical labels.

4. **Output length directly affects model completion.** Shortening
   justifications from ~40-80 words to ~20-30 words let llama3.1 finish
   within timeout on all plans. Advisory length constraints work for API
   models but are fragile for local models.

5. **The step currently mixes two goals.** Deduplication (overlap reduction)
   and prioritization (primary vs secondary) are fused into one decision.
   This creates a retention bias — anything that seems important survives,
   even if it overlaps. Separating these concerns is the most promising
   architectural improvement.

6. **Conservative retention is a valid design choice** for an intermediate
   pipeline stage, but it has consequences: the output is noisier, later
   stages inherit ambiguity, and the step no longer provides a clear
   compression boundary. The current design accepts this tradeoff because
   step 4 (FocusOnVitalFewLevers) handles further filtering.

7. **Single-batch reasoning is powerful but brittle.** The model sees all
   levers at once (good for global consistency) but one bad completion
   corrupts everything (no repair mechanism). Adding a validation pass
   over survivors would catch the most common failure modes without
   requiring a full architectural change.
