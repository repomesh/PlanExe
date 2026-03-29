# Proposal 130: Per-Task Sampling Profiles — Adaptive Inference Parameters for Pipeline Output Diversity

**Author:** Egon (VoynichLabs), inspired by G0DM0D3 (elder-plinius/G0DM0D3) and Mark's analysis
**Status:** Draft
**Date:** March 29, 2026
**Context:** PlanExe pipeline uses uniform, conservative sampling across all tasks. G0DM0D3's AutoTune framework demonstrates that context-adaptive parameter selection dramatically changes output quality.

---

## The problem

PlanExe generates formulaic, repetitive output because every task in the pipeline uses the same conservative sampling parameters. The current codebase confirms this:

| Task category | Temperature | top_p | freq_penalty | presence_penalty |
|---|---|---|---|---|
| IdentifyPurposeTask | 0.0 | unset | unset | unset |
| All WBS tasks (L1/L2/L3) | 0.5 | unset | unset | unset |
| TaskDurations, Dependencies | 0.5 | unset | unset | unset |
| ExpertCost | 0.5 | unset | unset | unset |
| CreatePitch | 0.5 | unset | unset | unset |
| SWOT (Gradio standalone) | 0.12 | unset | unset | unset |
| ResponsesAPILLM (default) | 1.0 | unset | unset | unset |

**Frequency penalty and presence penalty are never set anywhere in the pipeline.** These are the primary controls for vocabulary diversity and topic introduction. Their absence explains why every plan reads like it was written by the same PMO consultant recycling the same 200 phrases.

Temperature alone is insufficient. At temp 0.5, the model samples from a narrowed distribution but still draws from the same vocabulary. Presence penalty (0.0–2.0) is what forces the model to introduce new concepts. Frequency penalty (0.0–2.0) is what stops it from repeating "stakeholder engagement" twelve times per section.

## The insight from G0DM0D3

G0DM0D3 (elder-plinius/G0DM0D3) demonstrates that inference-time steering through composable sampling profiles — without modifying model weights — dramatically changes output character. Their AutoTune module defines five context profiles:

| Profile | τ (temp) | top_p | freq_penalty | presence_penalty |
|---|---|---|---|---|
| CODE | 0.15 | 0.80 | 0.20 | 0.00 |
| CREATIVE | 1.15 | 0.95 | 0.50 | 0.70 |
| ANALYTICAL | 0.40 | 0.88 | 0.20 | 0.15 |
| CHAT | 0.75 | 0.90 | 0.10 | 0.10 |
| CHAOS | 1.70 | 0.99 | 0.80 | 0.90 |

The key insight: different output objectives need different parameter vectors. Code generation and creative writing are not the same task and should not share the same temperature. G0DM0D3 achieves 84% accuracy classifying context and selecting appropriate profiles — but PlanExe doesn't need classification because we already know what each task is supposed to produce.

## Proposed: per-task sampling profiles for PlanExe

### Profile definitions

Three profiles mapped to PlanExe task types:

**STRUCTURED** — for tasks that produce JSON, schemas, or dependency graphs
```
temperature: 0.15
top_p: 0.85
frequency_penalty: 0.1
presence_penalty: 0.0
```

**ANALYTICAL** — for tasks that evaluate, review, assess, or critique
```
temperature: 0.5
top_p: 0.90
frequency_penalty: 0.3
presence_penalty: 0.3
```

**CREATIVE** — for tasks that generate diverse ideas, scenarios, or narratives
```
temperature: 0.8
top_p: 0.95
frequency_penalty: 0.5
presence_penalty: 0.7
```

### Task-to-profile mapping

**STRUCTURED profile** (deterministic, schema-safe):
- IdentifyPurposeTask (currently 0.0 — keep low)
- PlanTypeTask
- CreateWBSLevel1Task, CreateWBSLevel2Task, CreateWBSLevel3Task
- IdentifyTaskDependenciesTask
- EstimateTaskDurationsTask
- CreateScheduleTask
- WBSProjectLevel1AndLevel2Task, WBSProjectLevel1AndLevel2AndLevel3Task
- ConsolidateAssumptionsMarkdownTask
- ConsolidateGovernanceTask
- All markdown consolidation tasks

**ANALYTICAL profile** (balanced, moderate diversity):
- RedlineGateTask
- MakeAssumptionsTask, DistillAssumptionsTask, ReviewAssumptionsTask
- GovernancePhase1–6 tasks
- ReviewPlanTask
- ReviewTeamTask
- SWOTAnalysisTask
- DataCollectionTask
- FilterDocumentsToFindTask, FilterDocumentsToCreateTask
- SelfAuditTask
- ExecutiveSummaryTask
- ProjectPlanTask

**CREATIVE profile** (divergent, vocabulary-diverse):
- PremiseAttackTask
- CandidateScenariosTask
- SelectScenarioTask
- PotentialLeversTask, EnrichLeversTask, FocusOnVitalFewLeversTask
- ExpertReviewTask (expert criticism should sound like different experts, not the same one)
- PremortemTask (needs to imagine failures the user hasn't considered)
- CreatePitchTask (should be compelling, not formulaic)
- QuestionsAndAnswersTask
- FindTeamMembersTask, EnrichTeamMembersWithBackgroundStoryTask
- IdentifyRisksTask
- DraftDocumentsToFindTask, DraftDocumentsToCreateTask

### Why presence penalty is the key lever

Consider ExpertReviewTask. Currently at temp 0.5 with no penalties, the model generates eight "experts" who all use the same vocabulary:

> "The project should consider stakeholder engagement... risk mitigation strategies... a phased approach to implementation..."

With presence_penalty 0.7, the model is penalized for reusing tokens it has already generated. Each subsequent expert is forced to introduce new vocabulary and new concerns. The eighth expert cannot recycle the first expert's phrases — the penalty makes that increasingly unlikely with each token.

This is exactly what the Expert Criticism section needs: genuine diversity of perspective, not eight rewordings of the same PMO template.

For Premortem, the same logic applies: imagining how a project fails requires the model to explore different failure modes, not repeat "budget overrun, timeline slippage, stakeholder misalignment" in eight variations.

For structured tasks (WBS, dependencies, schedules), presence penalty should be near zero — you want consistent terminology across the task graph, not creative synonyms for the same work package.

## Implementation

### Option A: Profile field on PlanTask base class (minimal change)

Add a `sampling_profile` field to the `PlanTask` base class in `run_plan_pipeline.py`:

```python
class PlanTask(luigi.Task):
    # existing fields...
    
    SAMPLING_PROFILES = {
        "structured": {"temperature": 0.15, "top_p": 0.85, "frequency_penalty": 0.1, "presence_penalty": 0.0},
        "analytical": {"temperature": 0.5, "top_p": 0.90, "frequency_penalty": 0.3, "presence_penalty": 0.3},
        "creative":   {"temperature": 0.8, "top_p": 0.95, "frequency_penalty": 0.5, "presence_penalty": 0.7},
    }
    
    sampling_profile = "analytical"  # default
    
    def get_sampling_params(self):
        return self.SAMPLING_PROFILES[self.sampling_profile]
```

Each task subclass overrides `sampling_profile`:
```python
class PremortemTask(PlanTask):
    sampling_profile = "creative"
    # ...

class CreateWBSLevel1Task(PlanTask):
    sampling_profile = "structured"
    # ...
```

The `get_sampling_params()` dict is passed through to the LLM call. This requires that `llm_executor` and `responses_api_llm` accept and forward these parameters — a small change to the LLM utility layer.

### Option B: Config-driven profiles (more flexible)

Add a `sampling_profiles` section to `config.json`:

```json
{
  "sampling_profiles": {
    "structured": {"temperature": 0.15, "top_p": 0.85, "frequency_penalty": 0.1, "presence_penalty": 0.0},
    "analytical": {"temperature": 0.5, "top_p": 0.90, "frequency_penalty": 0.3, "presence_penalty": 0.3},
    "creative":   {"temperature": 0.8, "top_p": 0.95, "frequency_penalty": 0.5, "presence_penalty": 0.7}
  },
  "task_profiles": {
    "PremortemTask": "creative",
    "ExpertReviewTask": "creative",
    "CreateWBSLevel1Task": "structured",
    "default": "analytical"
  }
}
```

This lets users tune profiles without code changes. A user running a highly creative plan could bump the creative profile's temperature to 1.0; a user running a safety-critical infrastructure plan could pull everything to analytical.

### Model compatibility

Not all models support all parameters:
- **OpenAI/OpenRouter:** temperature, top_p, frequency_penalty, presence_penalty — all supported
- **Anthropic:** temperature, top_p — supported; frequency_penalty, presence_penalty — not supported
- **Ollama/local:** temperature, top_p — supported; penalties vary by model

The implementation should pass only the parameters the provider accepts. The LLM utility layer already handles provider differences — this extends that pattern.

## Experiment design

**Phase 1: A/B comparison (single prompt, two runs)**
1. Run the same prompt (e.g., "Bubba's Hot Nut Sack" or a standard test prompt) twice:
   - Control: current uniform params (temp 0.5, no penalties)
   - Treatment: per-task profiles as proposed above
2. Compare using P128 quality metrics:
   - Grounding density (TF-IDF vs PMO baseline)
   - Vocabulary diversity (unique terms / total terms per section)
   - Cross-section repetition rate (how many phrases appear in multiple sections)
   - Expert distinctiveness (for ExpertReviewTask: cosine similarity between expert outputs — lower is better)

**Phase 2: Profile tuning (3–5 runs)**
1. Vary the creative profile's presence_penalty: 0.3, 0.5, 0.7, 1.0
2. Measure at what point structured JSON starts breaking (the ceiling)
3. Find the sweet spot: maximum diversity without schema failures

**Phase 3: Model comparison**
1. Same prompt, same profiles, different models
2. Identify which models benefit most from penalty steering
3. Some models (e.g., GPT-4o) may already have internal anti-repetition; others (local Ollama models) may benefit dramatically

## Relationship to other proposals

- **P128 (quality metrics):** Provides the measurement framework. Per-task profiles are the intervention; P128 metrics are how we measure the result.
- **P129 (prompt dentist):** Complementary. P129 enriches the input; P130 optimizes how the pipeline processes it. Together they address both sides of the quality equation.
- **G0DM0D3 (external):** Source of the AutoTune concept. PlanExe's advantage: we don't need context classification because the task graph already defines what each call should produce.

## Extended: Per-Task Model Variant Steering (Grok 4.1 Fast)

### The insight Mark identified

The proposal above treats sampling parameters as knobs on a single model. But certain cheap, capable models — specifically **Grok 4.1 Fast** via OpenRouter — offer something more powerful: **two API variants of the same model with different capability surfaces.**

### Grok 4.1 Fast: Two variants, one model

| Variant | Price (in/out per 1M) | Reasoning | Structured Output | Sampling Params |
|---|---|---|---|---|
| `grok-4-1-fast-non-reasoning` | $0.20 / $0.50 | ❌ | ✅ json_schema guaranteed | ✅ temp, top_p, freq_penalty, presence_penalty |
| `grok-4-1-fast-reasoning` | $0.20 / $0.50 | ✅ CoT | ✅ json_schema guaranteed | ⚠️ temp, top_p only — **freq/presence penalty explicitly rejected** |

Source: [xAI docs — Reasoning](https://docs.x.ai/developers/model-capabilities/text/reasoning), [xAI docs — Structured Outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs), [xAI docs — Models](https://docs.x.ai/developers/models)

**Critical finding:** The xAI API returns an error if you send `presencePenalty`, `frequencyPenalty`, or `stop` to reasoning variants. This is not a soft constraint — it's a hard API rejection. The non-reasoning variant accepts all sampling parameters.

### Per-task model variant + parameter matrix

This extends the three-profile system above into a **two-dimensional steering matrix**: model variant × sampling profile.

| Task Category | Model Variant | Temperature | top_p | freq_penalty | pres_penalty | Rationale |
|---|---|---|---|---|---|---|
| **Creative** (Premortem, Expert Review, Scenarios, Pitch, Team Backstories, Risk Identification, Lever Exploration) | non-reasoning | 0.8 | 0.95 | 0.5 | 0.7 | Full penalty surface for vocabulary diversity; reasoning not needed for divergent generation |
| **Analytical** (Assumptions, Governance, Review, Self-Audit, SWOT, Pre-Project Assessment) | reasoning | 0.5 | 0.90 | n/a | n/a | CoT improves analytical depth; penalties unavailable but reasoning compensates |
| **Structured** (WBS L1/L2/L3, Dependencies, Durations, Schedule, Purpose, Plan Type) | non-reasoning | 0.15 | 0.85 | 0.1 | 0.0 | Deterministic, schema-guaranteed output; no reasoning overhead needed |

### Cost implications

The 274-task BubbasHotNutSack run cost ~$3.90 on Claude (Sonnet). At Grok 4.1 Fast pricing ($0.20/$0.50 per 1M tokens), the same run could cost approximately **$0.30–0.50** — a 7–13× cost reduction.

This isn't just about saving money. At these prices, you can afford to:
- Run the same prompt 5 times with different creative profiles and pick the best
- Use the reasoning variant for analytical tasks where CoT genuinely helps
- Run A/B experiments comparing parameter configurations without budget anxiety

### Implementation: model routing in the task profile

Extend Option A from above to include a `model_variant` field:

```python
class PlanTask(luigi.Task):
    SAMPLING_PROFILES = {
        "structured": {
            "model_variant": "non-reasoning",
            "temperature": 0.15, "top_p": 0.85,
            "frequency_penalty": 0.1, "presence_penalty": 0.0
        },
        "analytical": {
            "model_variant": "reasoning",
            "temperature": 0.5, "top_p": 0.90
            # No frequency/presence penalty — API rejects them for reasoning variants
        },
        "creative": {
            "model_variant": "non-reasoning",
            "temperature": 0.8, "top_p": 0.95,
            "frequency_penalty": 0.5, "presence_penalty": 0.7
        },
    }
```

The LLM routing layer resolves `model_variant` to the actual model ID based on the configured provider. For xAI/OpenRouter: `non-reasoning` → `x-ai/grok-4-1-fast-non-reasoning`, `reasoning` → `x-ai/grok-4-1-fast-reasoning`. For providers without variant separation (Anthropic, OpenAI), the variant field is ignored and only sampling params apply.

### Provider parameter compatibility matrix

| Provider | temp | top_p | freq_penalty | pres_penalty | structured output | reasoning toggle |
|---|---|---|---|---|---|---|
| xAI (non-reasoning) | ✅ | ✅ | ✅ | ✅ | ✅ json_schema | n/a |
| xAI (reasoning) | ✅ | ✅ | ❌ error | ❌ error | ✅ json_schema | ✅ |
| OpenAI | ✅ | ✅ | ✅ | ✅ | ✅ json_schema | ✅ (o-series) |
| Anthropic | ✅ | ✅ | ❌ unsupported | ❌ unsupported | ⚠️ tool_use workaround | ❌ |
| Ollama/local | ✅ | ✅ | varies | varies | ❌ | ❌ |
| OpenRouter | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (model-dependent) |

The implementation must strip unsupported parameters before sending to each provider. This is already partially handled by the LLM utility layer — extending it to handle the penalty params is straightforward.

## Cost and risk

- **Cost:** Zero marginal cost for parameter changes. Model variant steering on Grok 4.1 Fast actively *reduces* cost (7–13× cheaper than Claude Sonnet).
- **Risk:** Higher temperature + penalties on creative tasks could occasionally produce outputs that fail JSON schema validation. Mitigation: structured tasks stay at conservative settings; only narrative/analysis tasks get the creative profile. The pipeline's existing retry logic handles occasional schema failures. Grok's guaranteed structured output eliminates schema risk for structured tasks entirely.
- **Effort:** Option A is a half-day code change for parameter profiles. Adding model variant routing adds another half-day. Option B (config-driven) is a full day including config parsing and provider compatibility layer.

## Extended: Best-of-N Task Selection (Simon's Pattern)

### The idea

Instead of running each pipeline step once and hoping the output is good, run each step **N times** with different model configurations (different sampling profiles, different model variants, or both), then use a **reasoning model to select the best output** before feeding it to the next step.

This is G0DM0D3's ULTRAPLINIAN pattern applied at the pipeline task level: parallel generation → quality scoring → winner propagation.

### Why this is now feasible

At Grok 4.1 Fast pricing ($0.20/M in, $0.50/M out):

| Strategy | Creative tasks (N=3) | Analytical tasks (N=2) | Structured tasks (N=1) | Selection overhead | Est. total pipeline cost |
|---|---|---|---|---|---|
| Current (1×, Claude Sonnet) | — | — | — | — | ~$3.90 |
| P130 profiles only (1×, Grok Fast) | $0.01/task | $0.01/task | $0.005/task | none | ~$0.40 |
| Best-of-N + selection | $0.03/task | $0.02/task | $0.005/task | ~$0.01/task (reasoning) | ~$1.00–1.50 |

Even with 3× generation on creative tasks and a reasoning selection step, the pipeline stays under $2 — still 2–4× cheaper than a single Claude Sonnet run.

### Scoring rubric: 5-axis weighted selection

G0DM0D3's ULTRAPLINIAN module achieves 82-point quality discrimination across models using a weighted 5-axis scoring system (substance, directness, completeness, relevance, structure). The axes are objective-agnostic — the same mechanism works for any quality criterion by reweighting the axes.

For PlanExe, we adapt this to a **5-axis pipeline quality rubric**:

| Axis | Weight | What it measures | How to compute |
|---|---|---|---|
| **Schema compliance** | 0.25 | Does the output parse against the task's expected schema? | Binary: 1.0 if valid JSON/schema, 0.0 if not. With Grok's guaranteed structured output, this becomes a pre-filter (reject before scoring). |
| **Prompt fidelity** | 0.25 | Does the output address the specific plan's domain, not generic boilerplate? | TF-IDF cosine similarity between output vocabulary and the original prompt's domain terms, minus similarity to a PMO baseline vocabulary. Higher = more grounded in the user's actual plan. (P128 grounding density metric.) |
| **Diversity from context** | 0.20 | Does this step introduce new information vs recycling upstream output? | 1 − (Jaccard similarity of this output's 3-grams against concatenated upstream pipeline outputs). Penalizes the pipeline converging on a narrow vocabulary as it progresses. |
| **Domain vocabulary density** | 0.15 | Does the output use specific, concrete domain terms rather than abstract PMO jargon? | Ratio of domain-specific terms (extracted from the user's prompt and enriched via P129 prompt dentist) to total content words. "FDA 510(k) submission timeline" scores higher than "regulatory compliance framework." |
| **Internal diversity** | 0.15 | Within a single output, does it present genuinely different perspectives/items? | For multi-item outputs (ExpertReview, Premortem, Scenarios): average pairwise cosine distance between items. For single-item outputs (ExecutiveSummary): vocabulary diversity ratio (unique words / total words). G0DM0D3's feedback heuristics module computes this as a 3-gram repetition score. |

**Composite score:** Σ(axis_weight × axis_score) → 0–100 scale.

The reasoning model receives all N candidates plus the rubric and returns the index of the winner. For efficiency, the four computable axes (all except schema compliance, which is a pre-filter) can be computed deterministically without an LLM call. The reasoning model is only needed when scores are close (within 5 points) or when task-specific judgment is required.

**Axis reweighting per task type:**
- **Creative tasks** (Premortem, Expert Review, Scenarios): boost internal diversity to 0.25, reduce schema compliance to 0.15 (narrative outputs have looser schema requirements)
- **Structured tasks** (WBS, Dependencies, Schedule): boost schema compliance to 0.35, reduce internal diversity to 0.05 (consistent terminology is a feature, not a bug)
- **Analytical tasks** (Governance, Assumptions, Review): balanced weights as shown above

This follows G0DM0D3's core insight: the scoring axes are *objective-agnostic primitives*. The same 5-axis mechanism serves different pipeline tasks by reweighting — just as ULTRAPLINIAN's anti-refusal axis can be replaced with a pedagogical axis by changing weights without changing the scoring infrastructure.

### Implementation sketch

```python
class PlanTask(luigi.Task):
    # Number of parallel generations for this task
    generation_count = 1  # default: single-shot (structured tasks)
    
    # Selection model (only used when generation_count > 1)
    selection_model = "grok-4-1-fast-reasoning"
    
    def run_with_selection(self):
        if self.generation_count == 1:
            return self.generate_once()
        
        candidates = []
        for i in range(self.generation_count):
            profile = self.get_variant_profile(i)  # rotate through profiles
            candidates.append(self.generate_with_profile(profile))
        
        # Filter: schema compliance
        valid = [c for c in candidates if self.validates_schema(c)]
        if len(valid) == 1:
            return valid[0]
        
        # Select: reasoning model picks the winner
        return self.select_best(valid, model=self.selection_model)
```

Task subclasses override `generation_count`:
```python
class PremortemTask(PlanTask):
    sampling_profile = "creative"
    generation_count = 3  # best-of-3

class CreateWBSLevel1Task(PlanTask):
    sampling_profile = "structured"
    generation_count = 1  # single-shot, schema-guaranteed
```

### Selection strategy: Select vs Merge

**Select-1** (simple): Pick the single best candidate based on composite score. Appropriate for tasks that produce a single coherent output (ExecutiveSummary, ProjectPlan, PlanType).

**Merge** (Simon's pattern, preferred for list-producing tasks): Pick the best candidate as the skeleton, then scan runners-up for **individual items the winner missed** and splice them in. The reasoning model's job shifts from "pick the winner" to "assemble the best composite from all candidates."

**Merge-eligible tasks** — any task that produces a list of distinct items:
- ExpertReviewTask: 8 expert critiques → merge unique angles from all candidates
- PremortemTask: failure modes → merge non-overlapping failure scenarios
- CandidateScenariosTask: possible futures → merge to span the full possibility space
- IdentifyRisksTask: risk items → merge for coverage completeness
- PotentialLeversTask / EnrichLeversTask: lever items → merge unique levers
- FindTeamMembersTask: team roles → merge missing specializations
- DraftDocumentsToFindTask / DraftDocumentsToCreateTask: document lists → merge for completeness

**Example:** ExpertReviewTask generates 3 candidates, each with 8 expert critiques. Candidate B scores highest overall — but Candidate A identified a unique regulatory risk B missed, and Candidate C had a supply chain angle neither covered. The merge step grafts those two critiques into B's output → final output has 10 expert critiques covering more ground than any single candidate.

**Cost:** One additional reasoning call per merged task (the merge pass). At Grok 4.1 Fast pricing, negligible (~$0.005 per merge call).

### Variant rotation for N generations

When generating N candidates, rotate through different configurations:
- **Candidate 1:** Creative profile (temp 0.8, high penalties)
- **Candidate 2:** Analytical profile (temp 0.5, moderate penalties)
- **Candidate 3:** Wild profile (temp 1.1, high penalties, reasoning variant)

This ensures the candidate pool has genuine diversity, not three rolls from the same distribution.

### Parallelization

The N generations per task are independent — they can run as concurrent API calls. At Grok's 600 RPM rate limit, even 3× parallel generation per task won't bottleneck. The selection step is sequential (must wait for all candidates), but it's a single short reasoning call.

### Relationship to P128 compiler model

Simon's pattern is essentially the P128 compiler model applied **per-step** rather than as a post-pipeline gate. The tradeoff: per-step selection catches quality issues earlier (before they propagate), but costs more in total API calls. Post-pipeline gating is cheaper but can only reject the whole plan, not fix individual weak steps.

The ideal system might combine both: per-step best-of-N selection for high-variance creative tasks, plus a post-pipeline quality gate for overall coherence.

## Extended: STM Post-Processing (Zero-Cost Output Cleanup)

G0DM0D3's STM (Semantic Transformation Modules) are deterministic regex-based output transformers — composable, zero-cost, and immediately applicable without any model changes.

### Modules directly applicable to PlanExe

**Hedge Reducer** — strips hedging language:
- "I think", "I believe", "perhaps", "maybe", "It seems like", "It appears that", "probably", "possibly", "In my opinion", "From my perspective"
- 11 regex patterns, 100% precision on constructed test cases
- **PlanExe targets:** ExpertReviewTask, PremortemTask, ExecutiveSummaryTask, ReviewPlanTask — all produce outputs riddled with "It's important to note that..." hedging

**Direct Mode** — strips preambles:
- "Sure!", "Of course!", "Certainly!", "I'd be happy to help", "Great question!", "Let me help you with that"
- 10 regex patterns
- **PlanExe targets:** Every task that produces long-form output. The model almost always opens with "Certainly, here is a comprehensive analysis..."

**Implementation:** Apply as a post-processing pass after LLM generation, before writing to the pipeline output file. No model changes needed. Can be toggled per task via the profile system.

```python
class PlanTask(luigi.Task):
    stm_modules = ["hedge_reducer", "direct_mode"]  # default for all tasks
    
    def post_process(self, output: str) -> str:
        for module in self.stm_modules:
            output = STM_REGISTRY[module].transform(output)
        return output
```

## Extended: EMA Feedback Loop (Cross-Run Learning)

G0DM0D3's feedback loop uses Exponential Moving Average (α=0.3) to learn optimal parameter adjustments from binary quality ratings per context type.

### Adaptation for PlanExe

After each pipeline run, individual task outputs are rated (manually or via automated heuristics). Over multiple runs, the system learns which sampling parameters produce better outputs for each task type.

**Automated rating heuristics** (from G0DM0D3's `computeHeuristics`):
- **Repetition score:** 3-gram overlap frequency (0.0 = no repetition, 1.0 = extremely repetitive)
- **Vocabulary diversity:** unique words / total words ratio
- **Response length:** length in characters (proxy for substance)
- **Average sentence length:** complexity indicator

**Learning curve:** G0DM0D3 shows convergence to 29–62% parameter improvement within 19 ratings, reaching maximum influence (50% weight, capped) at 20 samples. For PlanExe, this means ~5–10 pipeline runs before the system meaningfully adapts.

**Per-task storage:**
```json
{
  "learned_profiles": {
    "PremortemTask": {
      "sample_count": 12,
      "positive_params_ema": {"temperature": 0.85, "presence_penalty": 0.72, ...},
      "negative_params_ema": {"temperature": 0.45, "presence_penalty": 0.15, ...},
      "adjustments": {"temperature": +0.12, "presence_penalty": +0.18}
    }
  }
}
```

The adjustments blend into the per-task sampling profile, gradually shifting each task's parameters toward what actually works — not what we guessed would work.

## References

- **G0DM0D3:** elder-plinius/G0DM0D3 (GitHub). Inference-time output steering framework. VoynichLabs fork: VoynichLabs/G0DM0D3.
- **G0DM0D3 paper:** "G0DM0D3: Inference-Time Output Steering Framework for LLMs" — five composable steering primitives (AutoTune, Feedback Loop, Parseltongue, STM, ULTRAPLINIAN). Key results: AutoTune 84% context classification accuracy, ULTRAPLINIAN 82-point quality discrimination, Feedback Loop convergence in 19 ratings.
- **P128:** Proposal 128 — Compiler Model, Quality Metrics, Dogfood Execution. Provides the measurement framework for evaluating P130's interventions.
- **P129:** Proposal 129 — Prompt Dentist, Pre-Pipeline Prompt Enrichment. Complements P130 (input enrichment + output steering).
- **xAI Grok API docs:** https://docs.x.ai/developers/models — Model pricing, reasoning variant constraints, structured output guarantees.
- **OpenRouter API docs:** https://openrouter.ai/docs/api/reference/parameters — Full sampling parameter surface (temperature, top_p, frequency_penalty, presence_penalty, repetition_penalty, min_p, top_a).

## Summary

PlanExe's formulaic output is not a model limitation — it's a parameter limitation. The pipeline never sets frequency or presence penalties, and uses uniform temperature across tasks with fundamentally different objectives. G0DM0D3 demonstrates that per-context sampling profiles produce dramatically different output character. PlanExe already knows what each task is (the task graph is explicit), so it doesn't need classification — just a mapping from task type to sampling profile.

The extended insight: models like Grok 4.1 Fast offer **two API variants** (reasoning and non-reasoning) with different parameter surfaces at the same price. Per-task steering becomes two-dimensional — select the right model variant *and* the right sampling parameters for each task. Creative tasks get full penalty control without reasoning overhead. Analytical tasks get CoT without needing penalties. Structured tasks get deterministic, schema-guaranteed output.

**Recommended priority:** High. Zero marginal cost (likely cost reduction), measurable impact, and directly addresses the "everything sounds the same" problem that undermines plan quality.
