---
title: "Domain-Aware Plan Ranking Engine with Relative Comparison"
date: 2026-02-22
status: proposal
author: Larry the Laptop Lobster
---

# Domain-Aware Plan Ranking Engine with Relative Comparison

**Author:** Larry (via OpenClaw)  
**Date:** 2026-02-22  
**Status:** Proposal  
**Audience:** Technical reviewers, engineers, stakeholders  

---

## Problem Statement

Current plan evaluation assumes a universal rubric (concreteness, executability, success criteria) with fixed weights. This breaks down when comparing plans from different domains:

- A road construction plan has different success signals than a software project
- Domain-specific KPIs (e.g., budget contingency in construction vs. MVP launch timing in software) matter more than generic signals
- Absolute scoring ("this plan is a 6/10") doesn't tell us whether it's in the top 10% of *similar plans* or mediocre compared to its peers

## Solution: Domain-Aware Relative Ranking

Instead of absolute scores, rank plans **within their domain context** using:

1. **Domain Classification** — detect plan type (construction, software, marketing, operations, etc.)
2. **Domain-Specific Signal Extraction** — pull KPIs relevant to that domain
3. **Corpus Bucketing** — group plans by type for fair comparison
4. **Relative ELO Ranking** — score each plan against similar plans, not in a vacuum
5. **Actionability** — surface top-performing plans (>90th percentile) as refinement candidates, flag major-rewrite situations

## Architecture

```
Plan Input
    ↓
[Domain Classifier] → Detect plan type (construction, software, marketing, ops, etc.)
    ↓
[Domain-Specific Extractor] → Pull KPIs: timeline clarity, resource estimates, risk mitigations, owner assignment, etc.
    ↓
[Corpus Bucketer] → Find all similar-type plans in database
    ↓
[ELO Ranker] → Compare new plan against sampled corpus neighbors
    ↓
[Actionability Scorer] → Is this top 10%? Fixable? Rewrite candidate?
    ↓
Output: Rank percentile, actionability flag, refinement recommendations
```

## Implementation Details

### 1. Domain Classification

**Input:** Plan text + metadata (e.g., project title, goals, phases)

**Output:** Domain label (one of: construction, software, marketing, operations, research, business-development, other)

**Method:** 
- LLM-based classification (zero-shot with 1-2 examples per domain)
- Fallback: keyword matching on phase names, deliverables, team roles
- Confidence threshold: if <0.7, flag as "cross-domain" or "unclear"

**Example prompts:**
```
"Read this plan and classify it as one of: construction, software, marketing, operations, research, business-development, other. Explain your reasoning in 1 sentence."

Plan text here...
```

### 2. Domain-Specific Signal Extraction

Each domain extracts different KPIs:

**Construction:**
- Budget vs. estimate variance tolerance
- Schedule float/slack (days available for delays)
- Risk contingency % of budget
- Owner accountability (named PM, not "TBD")
- Inspection/approval checkpoints

**Software:**
- MVP vs. full feature clarity (what's launch, what's post-launch)
- Tech debt acknowledgment (testing, documentation standards)
- Team skill-market fit (do we have the right people?)
- Dependency clarity (external APIs, third-party risks)
- Launch/staging milestones

**Marketing/Growth:**
- Channel diversification (not all eggs in one basket)
- CAC payback period or LTV:CAC ratio (are we thinking about unit economics?)
- Audience targeting specificity (who exactly, not "millennials")
- Content calendar or cadence clarity
- Success metric definition (viral coeff, NPS, growth rate?)

**Operations:**
- Process automation KPI (% manual vs. automated workflows)
- SLA definition (response time, uptime targets)
- Escalation clarity (who handles edge cases?)
- Monitoring/alerting (do we know if something breaks?)

**All domains:**
- Concreteness: timeline specificity, named owner, measurable KPIs (0–10)
- Executability: phase sequencing, dependencies clear (0–10)
- Success criteria: explicit win conditions, not vibes (0–10)

**Output:** JSON with domain + extracted signals (each 0–10)

```json
{
  "domain": "software",
  "concreteness": 8,
  "executability": 7,
  "success_criteria": 6,
  "domain_specific": {
    "mvp_clarity": 9,
    "tech_debt_acknowledged": 7,
    "team_fit": 6,
    "dependency_clarity": 8,
    "launch_milestones": 9
  },
  "confidence": 0.92
}
```

### 3. Corpus Bucketing

**Storage:**
- `plan_corpus` table extended with `domain` column
- Index on `domain` for fast filtering
- pgvector embeddings per domain (optional, for semantic search within domain)

**Query:**
```sql
SELECT * FROM plan_corpus 
WHERE domain = 'software' 
ORDER BY created_at DESC 
LIMIT 1000;
```

**Bucketing strategy:**
- Exact domain match (software vs. software)
- Fuzzy fallback: if bucket size <20, blend adjacent domains (e.g., "software" + "research" for AI projects)

### 4. Relative ELO Ranking

**Algorithm:**

1. Extract new plan's signals → `new_plan_vector`
2. Sample 5–10 existing plans from same domain (random + stratified by existing Elo)
3. For each sampled plan, LLM pairwise comparison:
   ```
   "Plan A: [concreteness, executability, success clarity]
    Plan B: [concreteness, executability, success clarity]
    
    Which plan is more likely to succeed? Why?
    (Likert: strongly A, slightly A, neutral, slightly B, strongly B)"
   ```
4. Use Likert output to compute win/loss, then update Elo:
   ```
   new_elo = old_elo + K * (expected_win - actual_win)
   where K = 32 (standard), expected_win based on current Elos
   ```

**Result:** Each plan has an Elo score *within its domain*, comparable across similar plans.

### 5. Actionability Scoring

**Output:**

```json
{
  "plan_id": "...",
  "domain": "software",
  "elo_score": 1650,
  "percentile": 0.87,
  "actionability": {
    "is_candidate_for_refinement": true,
    "reason": "87th percentile; fixable with clarity on tech debt and team roles",
    "needs_major_rewrite": false,
    "top_gaps": ["tech_debt_acknowledged", "team_fit"],
    "confidence": 0.92
  }
}
```

**Decision rules:**
- **>90th percentile**: "High-performing; consider as template for other plans"
- **70–90th percentile**: "Good candidate for refinement; address top gaps"
- **50–70th percentile**: "Mid-tier; incremental improvements or focused refinement"
- **<50th percentile & low concreteness**: "Major rewrite recommended; start over with domain-specific template"
- **<50th percentile & high concreteness**: "Execution challenges; may be doable despite lower score"

### 6. API Endpoints

```
POST /api/rank/domain-aware
  Input: { plan_text, plan_metadata }
  Output: { domain, signals, elo, percentile, actionability }

GET /api/leaderboard/by-domain?domain=software&limit=20
  Output: [ { rank, plan_id, elo, percentile }, ... ]

GET /api/corpus-stats?domain=software
  Output: { domain, count, avg_elo, elo_stdev, domain_signals_info }
```

## Data Model

**New columns in `plan_corpus`:**
```sql
ALTER TABLE plan_corpus ADD COLUMN domain VARCHAR(50);
ALTER TABLE plan_corpus ADD COLUMN signals JSONB; -- domain-agnostic + domain-specific
ALTER TABLE plan_corpus ADD COLUMN elo_score FLOAT DEFAULT 1600;
ALTER TABLE plan_corpus ADD COLUMN percentile FLOAT; -- recomputed periodically
ALTER TABLE plan_corpus ADD COLUMN actionability_notes JSONB;

CREATE INDEX idx_plan_corpus_domain ON plan_corpus(domain);
CREATE INDEX idx_plan_corpus_elo ON plan_corpus(elo_score DESC);
```

## Implementation Phases

### Phase 1: Minimal Domain Classifier (2 days)
- LLM-based domain detection (zero-shot)
- Fallback to keyword matching
- No ELO yet; just label & store domain

### Phase 2: Domain-Specific Extractors (3 days)
- Build 3–4 domain-specific signal extractors (software, construction, ops, marketing)
- Normalize all to 0–10 scale
- Store signals in `plan_corpus`

### Phase 3: ELO Ranking Engine (4 days)
- Implement pairwise LLM comparison
- Elo update logic
- Corpus bucketing & sampling
- Percentile calculation

### Phase 4: Actionability & API (2 days)
- Actionability scoring rules
- `/api/rank/domain-aware` endpoint
- `/api/leaderboard/by-domain` endpoint
- Test against real PlanExe corpus

**Total estimate:** 10 days

## Testing Strategy

1. **Unit tests:** Domain classifier (accuracy on known plans)
2. **Integration tests:** Full ranking pipeline (new plan → elo score → percentile)
3. **Corpus validation:** Run against existing 100+ plans, verify percentile distribution is sensible
4. **Domain coverage:** Ensure top domains (software, construction, marketing) have >50 plans in corpus for ranking

## Success Criteria

- ✅ Domain classifier achieves >85% accuracy on test set
- ✅ Elo scores converge within 10 iterations (stability)
- ✅ Top 10% plans are consistently high-clarity and actionable
- ✅ Cross-domain comparison is avoided (software vs. construction ranked separately)
- ✅ API latency <2 seconds for new plan ranking

## Open Questions

1. **Domain list finality:** Should we start with 5 domains or leave it extensible? (Proposal: 5 initial, extensible)
2. **Sampling strategy:** Random 5–10 neighbors or stratified by existing Elo? (Proposal: stratified)
3. **Elo K-factor:** 32 (soft), 16 (hard), 64 (volatile)? (Proposal: 32, adaptive if needed)
4. **Corpus size threshold:** When do we stop ranking due to insufficient peers? (Proposal: <20 → merge adjacent domains)
5. **Actionability UI:** Does PlanExe web show percentile badges, heat maps, or refinement prompts? (Proposal: all three)

## Dependencies

- **LLM:** Gemini 2.0 Flash (for domain classification and pairwise comparison)
- **Embeddings:** OpenAI embeddings (optional, for semantic bucketing within domain)
- **Database:** PostgreSQL with pgvector (for corpus storage and fast domain filtering)
- **Rate limiting:** Respect API quotas (5 req/min per key)

## Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| Domain classifier misclassifies plan | Confidence threshold; manual override option; log misclassifications |
| Elo ranking is slow with large corpus | Cache pairwise comparisons; use stratified sampling (not random) |
| Cross-domain contamination | Strict bucketing; log when fallback to adjacent domain |
| Signal extraction is too generic | Domain-specific extractors with explicit KPI lists; tune per domain |

## References

- [ELO Ranking Proposal](07-elo-ranking.md)
- [Semantic Plan Search](05-semantic-plan-search-graph.md)

---

## Changelog

- **2026-02-22:** Initial proposal by Larry
