# Proposals Audit — Clustering, Top 10, and Five Novel Ideas

## Purpose

This proposal looks across the other ~137 proposals in `docs/proposals/`, classifies them
by current relevance, picks the ten most promising directions and explains how to take
them to the next level, then adds five novel ideas that are not yet on the table.

The intent is curatorial. The proposal folder has grown faster than it has been pruned.
A reader landing in `docs/proposals/` today cannot tell which ideas are dead, which are
half-built, and which are the next place to invest energy. This document is the answer
to "what should we work on next, and which proposals can we stop re-reading?"

The audit was performed by surveying every numbered proposal (00–137) plus the three
unnumbered files (`AGENTS.md`, `ensemble-judge-refinement.md`, `parallel-racing-robustness.md`),
cross-checking each against the codebase under `planexe/` and recent git history.

---

## Classification scheme

Each proposal is tagged on three axes:

- **STATUS** — `implemented`, `partial`, `untouched`, `superseded`, `stale`.
  - `implemented` = the proposal's core idea is shipped.
  - `partial` = some scaffolding exists but the proposal is not fully realised.
  - `untouched` = no code yet.
  - `superseded` = a newer proposal subsumes it.
  - `stale` = the premise no longer matches the project's direction.
- **RELEVANCE** — `high`, `medium`, `low`.
- **THEME** — `agentic`, `finance`, `plugin`, `verification`, `ranking`, `ui`,
  `governance`, `infra`, `prompt-quality`, `data`, `other`.

---

## Cluster overview

### By status

| Status | Count (approx.) | Reading guidance |
|---|---:|---|
| Implemented | ~16 | Treat as historical record. Worth reading only when chasing the rationale behind a current code path. |
| Partial | ~24 | The interesting middle. These are stalled mid-build and most of them will benefit from a finishing push, not a fresh design. |
| Untouched, high-relevance | ~30 | The candidate pool for next-quarter work. Most of the "Top 10" below comes from here. |
| Untouched, medium-relevance | ~40 | Useful seed material but not the next step. Keep on the shelf. |
| Untouched, low / stale | ~28 | Candidates for retirement (move to `docs/proposals/archive/` or just stop linking from indexes). |

### By theme

| Theme | Hot proposals | Status of the cluster |
|---|---|---|
| `verification` | 21, 22, 27, 38, 42, 43, 46, 56, 88, 102, 107, 112, 118, 123, 133, 135, ensemble-judge | Largest cluster, mostly untouched; this is the project's biggest under-invested area. |
| `agentic` | 26, 40, 41, 60, 61, 64, 66, 69, 71, 111, 114, 120, 121, parallel-racing | Second biggest; lots of "post-plan agents" overlap that needs consolidation. |
| `ranking` / quality | 07, 29, 68, 89–92, 96, 119, 122, 132 | 122 already shipped; 132/07 are the two ELO drafts that should be merged. |
| `finance` | 11–14, 33–37, 44, 45, 76, 100, 105 | 11–14 are stale (investor-portfolio framing); 33–37, 44 are a coherent untouched module. |
| `prompt-quality` | 57–59, 82, 83, 94, 117, 128, 129, 130 | Live area — the self-improve loop (117/94) is the project's actual quality engine today. |
| `infra` | 03, 31, 50–53, 55, 70, 73–75, 79–81, 87, 93, 101, 103, 104, 108–110, 131, 134 | Most of the recent shipping work landed here; remaining items are smaller cleanups. |
| `plugin` | 16–20, 47, 115, 127 | Conceptually solid but no momentum. Likely premature until the agentic story lands. |
| `ui` | 02, 04, 08, 32, 62, 95, 116 | 08 shipped (home.planexe.org); 95 (routing UX modes) is the next high-leverage UI. |
| `data` | 05, 77, 98, 105, 106, 110, 137 | 05 (semantic plan graph) is the pearl; the rest are niche. |
| `governance` | 00, 15, 25, 30, 54, 78, 99, 136, AGENTS | Mostly meta/process docs; not blocking anything. |
| `other` | 48, 67, 72, 84, 85, 125, 126 | The retirement bucket. |

### Likely retirement candidates

These are good to read once for context, then stop linking:

`11-investor-thesis-matching-engine`, `12-evidence-based-founder-execution-index`,
`13-portfolio-aware-capital-allocation`, `14-confidence-weighted-funding-auctions`
(all assume a "PlanExe as VC infrastructure" framing the project no longer pursues),
`28`/`29`/`30` (autonomous bid factory — same framing problem),
`48-moltbook-reputation-bridge`, `49-distributed-physical-task-dispatch-protocol`,
`51-decentralized-planexe-survivability`, `67-buildinpublic-twitter-automation`,
`72-ai-replacing-c-level-roles`, `84`/`85` (business-idea critique — narrow domain),
`99-human-utility-show-pedigree`, `100-lobster-museum-donation-routing`,
`126-arc-agi3-structured-exploration`.

### Implemented (no longer "proposals")

`00-triage`, `08-ui-for-editing-plan`, `55-taskitem-activity-log-decomposition-and-secure-downloads`,
`73-rename-task-prefix-in-mcp-tools`, `74-rename-taskitem-to-planitem`,
`75-post-rename-cleanup-issues`, `79-multiple-api-keys`, `81-mcp-api-key-validation`,
`87-plan-resume-mcp-tool`, `93-local-model-roadmap`, `109-llm-executor-retry-improvements`,
`110-usage-metrics-local-runs`, `113-llm-error-traceability`, `122-deduplicate-levers`,
`127-mcp-feedback`, `AGENTS`. These should ideally be moved into a `docs/proposals/done/`
subfolder so the active set stays scannable.

---

## Top 10 promising directions

Each entry below names the proposal(s) being built on, why it matters now, and a
concrete "next level" step that would move it from idea to shipped capability.

### 1. ELO ranking as the quality signal — `07`, `132`

**Why now.** Without an automated scalar quality signal, every other quality-related
proposal — prompt optimiser (117, 94), drift measurement (82, 83), ensemble judge,
benchmark prompts (98) — has to invent its own metric. ELO solves that once.

**Next level.**
1. Pick the *unit* of comparison: full plan, single pipeline stage output, or single
   answer to a benchmark prompt. Stage-output is the highest-leverage choice because it
   plugs directly into self-improve.
2. Implement a pairwise-judge primitive (`planexe/quality/elo_judge.py`) that takes two
   stage outputs + the rubric for that stage and returns a winner with a one-paragraph
   justification.
3. Run it nightly across the canonical benchmark suite (98) to produce a leaderboard
   per stage; surface that leaderboard in the self-improve runner so each prompt edit
   gets a delta in ELO points.
4. Once the leaderboard is stable, retire ad-hoc "iter N is better" judgements from
   the self-improve loop.

### 2. Semantic plan search graph — `05`

**Why now.** PlanExe accumulates more plans every week, and the only way to find one
today is by directory name. A pgvector index over plan text + structured metadata
(domain, scale, lever taxonomy) unlocks: few-shot retrieval into the pipeline,
duplicate-detection across runs, "show me plans like this one" in the UI, and the
data substrate for novel ideas N1, N3, N5 below.

**Next level.**
1. PostgreSQL is already deployed (memory: `database_postgres`). Add a `plans` table
   with embeddings on (initial_prompt, executive_summary, lever_set).
2. Backfill from the plan archive on home.planexe.org; do it lazily via a Luigi task.
3. Expose `plan_search` as an MCP tool first; ship the UI surface afterwards.

### 3. Routing trio: task complexity + cache-aware handoff + UX modes — `92`, `95`, `96`

**Why now.** The 26-Feb routing post-mortem (89) showed that the project pays Opus
prices for tasks that Haiku could handle. These three proposals are different angles
on the same problem and should be designed together, not separately.

**Next level.**
1. Use the complexity-assessment work (90, 91) to label every pipeline stage with a
   complexity tier in `LLMConfig`.
2. Wire 96 (cache-aware handoff) into `LLMExecutor` so a stage that needs Sonnet for
   its hard step doesn't blow the cache built up by Haiku in the easy steps.
3. Ship 95 (UX modes) last — it is a thin chooser on top of the routing primitive,
   not a separate system.

### 4. Autonomous prompt optimisation, fully closed-loop — `94`, `117`

**Why now.** The self-improve loop documented in `MEMORY.md` is already the project's
quality engine in practice (40 iterations on `identify_potential_levers`, 52 on
`deduplicate_levers`). The proposal-level next step is to remove the human-in-loop
verdict step and let it run unattended overnight.

**Next level.**
1. Replace the current "Claude reads the assessment and writes a verdict" step with
   the ELO judge from #1 above. The judge is the only thing that needs to be trusted
   to be hands-off.
2. Add a budget guard (cost ceiling per night) and a regression guard (don't promote
   a prompt that loses on >X% of benchmark prompts).
3. Add a per-stage rotation so the loop doesn't only optimise one prompt for weeks.

### 5. Post-plan agent execution — `61`, `64`, `66`, `120`, `121`

**Why now.** Five proposals describe variations on "the plan should not be the end of
the pipeline; agents should pick up the plan and start doing the work." This is the
single biggest user-visible upgrade on the table, but the five proposals contradict
each other on scope. They need consolidation into one architecture before any code
gets written.

**Next level.**
1. Write a consolidating proposal (139?) that picks one execution model: Luigi-driven,
   MCP-tool-driven, or Claude Agent SDK-driven. The Luigi-driven option dovetails
   with 65 (git as state machine) and 101 (Luigi resume hooks).
2. Define exactly *which* plan artifacts become agent inputs (project plan? WBS? next
   action list?) and what "done" means for an agent step.
3. Pilot with a single safe domain (e.g., literature-review plans) before expanding.

### 6. Adversarial red-team + critical-premises gate — `56`, `123`, `135`

**Why now.** PlanExe plans look authoritative whether or not they are correct. Three
proposals describe adversarial verification: 56 generates an attacker, 135 extracts
the load-bearing premises, 123 demands evidence calibration. Together they form a
"premortem-as-a-pipeline-stage" capability that would catch the most embarrassing
failure mode (confident, false plans).

**Next level.**
1. Implement 135 first: a structured extraction of "if this premise is wrong, the
   plan collapses" → list of N premises with confidence scores. (`planexe/critical_premises/`)
2. Layer 56 on top: a red-team agent that attacks each high-load premise and produces
   a counter-narrative.
3. Layer 123 last: an evidence-discipline scorer that grades how well the plan
   defends each premise. Block low-scoring plans from finishing.

### 7. Fermi sanity gate + domain-aware normaliser — `88`, `107`

**Why now.** Numbers in PlanExe plans are currently un-audited. A user can get a
$2.4M budget that quietly assumes Nairobi carpenters earn US wages. 88 proposes a
sanity-check gate that runs Fermi estimates against extracted parameters; 107
proposes a domain-aware normaliser. They are the same idea at two layers.

**Next level.**
1. Build the parameter extractor first (proposal 137 is a useful upstream design).
2. Pipe extracted parameters through an order-of-magnitude check against a small
   reference table (regional wages, material prices, conversion rates). Initial
   table can be hard-coded; a future iteration can pull from a service (105, 106).
3. When a parameter is >1 order of magnitude off, raise a `FermiViolation` that
   forces a regeneration of the offending paragraph rather than a global rerun.

### 8. Ensemble judge + parallel model racing — `ensemble-judge-refinement`, `parallel-racing-robustness`

**Why now.** The two unnumbered proposals are both about robustness on early-pipeline
tasks where a single model failure cascades downstream. They are complementary:
parallel racing fixes the *availability* side (pick whichever model returns first
with a valid answer), the ensemble judge fixes the *quality* side (when multiple
models return, pick the best). Code in `redline_gate.py` already gestures at this.

**Next level.**
1. Add `ParallelRacer` to `LLMExecutor` for stages tagged `racing-eligible`.
2. When >1 result comes back inside the deadline, hand them to the ELO judge from #1.
3. Log the loser results — they are training data for prompt optimisation (#4).

### 9. Finance triad — `33`, `34`, `35` (with `36`, `37`, `44` as follow-ups)

**Why now.** Proposals 33 (CBS), 34 (top-down), 35 (bottom-up reconciliation) form a
self-contained financial-modelling layer. They sit untouched while the project ships
narrower finance ideas (100, 105, 106). The triad would close the biggest credibility
gap in PlanExe outputs: budgets that are made of numbers, not vibes.

**Next level.**
1. Implement 33 (CBS) as a new pipeline stage that emits a structured cost tree.
2. Use the same stage to feed both 34 (top-down) and 35 (bottom-up) and reconcile
   them in a single report section. The reconciliation delta *is* the credibility
   signal.
3. Once the triad is in place, 36 (Monte Carlo) and 44 (audit pack) become small
   add-ons rather than new modules.

### 10. Multi-stage expert verification — `21`, `22`, `27`

**Why now.** PlanExe currently invents experts in-prompt. These three proposals
describe a coherent flow: discover the right expert profile (21), run multi-stage
verification with that expert (22), and triangulate across angles (27). It would
turn "Pretend Expert" into a structured second opinion.

**Next level.**
1. Start with 21 in narrow form: a deterministic expert-profile generator that emits
   2–3 personas with credentials and known biases for any plan domain.
2. Use those personas inside the existing critique/premortem stages instead of the
   currently anonymous expert voice. This is a one-week change and immediately
   raises plan quality.
3. Defer 27 (multi-angle) until #1 and #2 have run on the benchmark suite for a
   month and produced ELO data.

---

## Five novel ideas

These are not in the existing proposal set.

### N1. Plan lineage and time-travel diff

Every plan run produces a snapshot today, but the snapshots aren't related. Treat
each rerun as a commit on the same plan: store the parent run id, the prompt diff,
and the per-stage output diff. The user can then ask "what changed when I added
'in Nairobi' to the prompt?" and see exactly which downstream sections moved.

This pairs with the prompt optimiser (117, 94) — it gives every prompt edit a
visible diff in plan-space, not just in metric-space — and with semantic search
(#2) which provides the join key.

### N2. Counterfactual plan forking

Once plans are stored as a graph (N1 + #2), let the user fork at any node and
re-run only the downstream tasks under a "what-if" assumption ("what if the budget
is half?", "what if the deadline slips 6 months?"). Today the user has to re-run
the entire pipeline. Branching reruns turn PlanExe into a planning sandbox instead
of a one-shot generator. Ties into proposal 45 (counterfactual scenario explorer)
but reframes it as a graph operation rather than a separate engine.

### N3. Replay Lab — quality drift across model generations

Capture the full LLM I/O for every plan run (already partially possible via 113).
Build a tool that takes any historical plan and re-runs *just the LLM calls*
against today's models, using yesterday's prompts. The output is a curve of
"quality vs. model generation" for every plan in the archive — the dataset that
would let PlanExe answer "is Sonnet 4.7 actually better than 4.6 for our pipeline?"
without manual labelling. Also unlocks "we shipped a regression in stage X three
weeks ago" detection.

### N4. Risk curriculum — actionable next-24h checklist

Most users close the plan tab and never act on it. Add a small terminal section
called "Before you do anything else" that surfaces the top three most fragile
premises (from #6) as questions the user should answer in 24 hours, with the
exact source the user could check (e.g., "Confirm with city hall: is permit X
required for buildings under 200 m²?"). Converts a long plan into one
short-feedback loop. Scope is small; impact on user follow-through is plausibly
large.

### N5. Federated lever library

Levers (the dedup pipeline, proposal 122) are extracted from each plan and then
discarded after that run. Opt users into a shared library keyed by domain +
scale, so the dedup stage can borrow patterns: "for renewable-energy plans at
city scale, the canonical lever set is roughly these eight." This compounds with
every plan written and is a moat the project doesn't currently have. Privacy
boundary: only lever taxonomies and abstract patterns are shared, never the
user's prompt or specific numbers.

---

## Conclusion

The proposal folder reads like an idea graveyard partly because nobody is
allowed to bury anything. The first practical action this audit recommends is
operational, not technical: move the 16 implemented proposals into a `done/`
subfolder and the ~14 stale ones into an `archive/` subfolder, so the active
working set is the ~80 proposals that still represent genuine choices.

Once the noise is gone, the signal is sharp. Five clusters dominate the
"untouched but high-relevance" set:

1. **Quality measurement** — ELO judge as the underlying scalar (#1), used by
   the prompt optimiser (#4), the ensemble judge (#8), and the routing tier (#3).
2. **Verification** — adversarial red-team and critical-premise gates (#6),
   Fermi sanity check (#7), and structured expert personas (#10).
3. **Agentic execution** — the five overlapping post-plan-agents proposals
   collapsed into one design (#5).
4. **Knowledge substrate** — the semantic plan graph (#2), which is the
   precondition for novel ideas N1–N5.
5. **Financial credibility** — the CBS / top-down / bottom-up triad (#9),
   the only cluster that addresses the "PlanExe budgets aren't auditable"
   weakness.

The two recurring failure modes in the existing proposals are: ideas that
arrived before their preconditions (most plugin proposals; most agentic
proposals before there was an executor), and ideas that drift in scope until
they need their own quarter (the bid-factory / portfolio-VC framing). The
remedy on both sides is the same — finish the substrate work (ELO, semantic
graph, post-plan agent architecture) before opening the next batch.

The five novel ideas are deliberately built on top of that substrate rather
than alongside it, so any investment in #1, #2, and #5 above pays for N1–N5
as well.
