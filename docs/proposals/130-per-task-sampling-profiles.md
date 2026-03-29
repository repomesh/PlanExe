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

## Cost and risk

- **Cost:** Zero marginal cost. Sampling parameters are metadata on existing API calls, not additional calls.
- **Risk:** Higher temperature + penalties on creative tasks could occasionally produce outputs that fail JSON schema validation. Mitigation: structured tasks stay at conservative settings; only narrative/analysis tasks get the creative profile. The pipeline's existing retry logic handles occasional schema failures.
- **Effort:** Option A is a half-day code change. Option B is a full day including config parsing.

## Summary

PlanExe's formulaic output is not a model limitation — it's a parameter limitation. The pipeline never sets frequency or presence penalties, and uses uniform temperature across tasks with fundamentally different objectives. G0DM0D3 demonstrates that per-context sampling profiles produce dramatically different output character. PlanExe already knows what each task is (the task graph is explicit), so it doesn't need classification — just a mapping from task type to sampling profile.

**Recommended priority:** High. Zero marginal cost, measurable impact, and directly addresses the "everything sounds the same" problem that undermines plan quality.
