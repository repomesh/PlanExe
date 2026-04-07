# Split run_plan_pipeline.py — Design Spec

**Date:** 2026-04-02
**Status:** Approved
**Tags:** `worker_plan`, `refactor`, `maintainability`, `agent-isolation`

---

## Goal

Split `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py` (4,257 lines) into ~66 individual stage files plus a slim core module, optimizing for parallel agent work, `self_improve/` integration, and conflict-free DAG insertion.

## Problem

`run_plan_pipeline.py` contains ~66 Luigi task classes, the `PlanTask` base class, `ExecutePipeline`, `FullPlanPipeline`, and supporting utilities — all in one file. This means:

1. Two agents working on different pipeline steps must edit the same file, causing merge conflicts.
2. `self_improve/` cannot target an individual step file — it must reason about a 4,257-line module.
3. Inserting a new task in the DAG requires editing the giant file, risking unrelated merge conflicts with other in-flight work.

## Design Priorities

These priorities (from the user) override backward-compatibility concerns:

1. **Agent isolation** — each pipeline step in its own file so agents never conflict.
2. **Easy DAG insertion** — adding a new task between two existing tasks touches only 2 files (the new file and the downstream file's `requires()`), never a central registry.
3. **`self_improve/` addressability** — each step is an individually importable module.

## Approach

Extract each task class into its own file under a new `stages/` directory. Each file declares its own Luigi `requires()` dependencies by importing its upstream task(s). `run_plan_pipeline.py` keeps only the shared framework (`PlanTask`, `ExecutePipeline`, etc.).

## New Module Layout

### `run_plan_pipeline.py` (~280 lines, slimmed core)

Keeps:
- All imports needed by the framework classes
- `PlanTask` base class (lines 105–215)
- `_task_class_to_step_label` utility (lines 3851–3862)
- `PipelineProgress` dataclass (lines 3866–3871)
- `HandleTaskCompletionParameters` dataclass (lines 3875–3878)
- `ExecutePipeline` dataclass (lines 3882–4107)
- `DemoStoppingExecutePipeline` (lines 4109–4116)
- `configure_logging` (lines 4119–4148)
- `__main__` block (lines 4152–4258)
- Module-level constants: `logger`, `DEFAULT_LLM_MODEL`, `REPORT_EXECUTE_PLAN_SECTION_HIDDEN`

Changes:
- `ExecutePipeline.setup()` imports `FullPlanPipeline` from `stages.full_plan_pipeline` instead of referencing it as a module-level class.
- The `__main__` block's `DemoStoppingExecutePipeline` reference stays (it's in the same file).
- All ~66 task class definitions and their imports are removed.

### `stages/` directory

Each file contains exactly one task class (except where noted). Files follow this pattern:

```python
"""Pipeline stage: <one-line description>."""
import logging
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
# ... executor imports specific to this stage
# ... upstream task imports from sibling stage files

logger = logging.getLogger(__name__)

class FooTask(PlanTask):
    def requires(self):
        return self.clone(UpstreamTask)

    def output(self):
        return self.local_target(FilenameEnum.FOO)

    def run_with_llm(self, llm):
        # ... verbatim from current code
```

### `stages/__init__.py`

Empty file. Stage files are imported directly by whoever needs them (other stages, `FullPlanPipeline`).

### `stages/full_plan_pipeline.py`

Contains `FullPlanPipeline` which imports all task classes and lists them in `requires()`. This is the only file that imports every stage — it's the DAG root.

**Note:** `FullPlanPipeline.requires()` currently lists ALL tasks explicitly (not just leaves). This is preserved verbatim to maintain identical Luigi behavior. Optimizing to leaf-only listing is a separate future change.

### Complete file list

```
stages/
├── __init__.py
├── full_plan_pipeline.py
│
│  # Phase 1: Input & Validation
├── start_time.py                              (StartTimeTask)
├── setup.py                                   (SetupTask)
├── redline_gate.py                            (RedlineGateTask)
├── premise_attack.py                          (PremiseAttackTask)
│
│  # Phase 2: Purpose & Classification
├── identify_purpose.py                        (IdentifyPurposeTask)
├── plan_type.py                               (PlanTypeTask)
│
│  # Phase 3: Strategic Options & Scenarios
├── potential_levers.py                        (PotentialLeversTask)
├── deduplicate_levers.py                      (DeduplicateLeversTask)
├── enrich_levers.py                           (EnrichLeversTask)
├── focus_on_vital_few_levers.py               (FocusOnVitalFewLeversTask)
├── strategic_decisions_markdown.py            (StrategicDecisionsMarkdownTask)
├── candidate_scenarios.py                     (CandidateScenariosTask)
├── select_scenario.py                         (SelectScenarioTask)
├── scenarios_markdown.py                      (ScenariosMarkdownTask)
│
│  # Phase 4: Context
├── physical_locations.py                      (PhysicalLocationsTask)
├── currency_strategy.py                       (CurrencyStrategyTask)
├── identify_risks.py                          (IdentifyRisksTask)
│
│  # Phase 5: Assumptions
├── make_assumptions.py                        (MakeAssumptionsTask)
├── distill_assumptions.py                     (DistillAssumptionsTask)
├── review_assumptions.py                      (ReviewAssumptionsTask)
├── consolidate_assumptions_markdown.py        (ConsolidateAssumptionsMarkdownTask)
│
│  # Phase 6: Plan Foundation
├── pre_project_assessment.py                  (PreProjectAssessmentTask)
├── project_plan.py                            (ProjectPlanTask)
│
│  # Phase 7: Governance
├── governance_phase1_audit.py                 (GovernancePhase1AuditTask)
├── governance_phase2_bodies.py                (GovernancePhase2BodiesTask)
├── governance_phase3_impl_plan.py             (GovernancePhase3ImplPlanTask)
├── governance_phase4_decision_escalation_matrix.py (GovernancePhase4DecisionEscalationMatrixTask)
├── governance_phase5_monitoring_progress.py   (GovernancePhase5MonitoringProgressTask)
├── governance_phase6_extra.py                 (GovernancePhase6ExtraTask)
├── consolidate_governance.py                  (ConsolidateGovernanceTask)
│
│  # Phase 8: Team
├── related_resources.py                       (RelatedResourcesTask)
├── find_team_members.py                       (FindTeamMembersTask)
├── enrich_team_contract_type.py               (EnrichTeamMembersWithContractTypeTask)
├── enrich_team_background_story.py            (EnrichTeamMembersWithBackgroundStoryTask)
├── enrich_team_environment_info.py            (EnrichTeamMembersWithEnvironmentInfoTask)
├── review_team.py                             (ReviewTeamTask)
├── team_markdown.py                           (TeamMarkdownTask)
│
│  # Phase 9: Analysis
├── swot_analysis.py                           (SWOTAnalysisTask)
├── expert_review.py                           (ExpertReviewTask)
│
│  # Phase 10: Documents
├── data_collection.py                         (DataCollectionTask)
├── identify_documents.py                      (IdentifyDocumentsTask)
├── filter_documents_to_find.py                (FilterDocumentsToFindTask)
├── filter_documents_to_create.py              (FilterDocumentsToCreateTask)
├── draft_documents_to_find.py                 (DraftDocumentsToFindTask)
├── draft_documents_to_create.py               (DraftDocumentsToCreateTask)
├── markdown_documents.py                      (MarkdownWithDocumentsToCreateAndFindTask)
│
│  # Phase 11: WBS & Pitch
├── create_wbs_level1.py                       (CreateWBSLevel1Task)
├── create_wbs_level2.py                       (CreateWBSLevel2Task)
├── wbs_project_level1_and_level2.py           (WBSProjectLevel1AndLevel2Task)
├── create_pitch.py                            (CreatePitchTask)
├── convert_pitch_to_markdown.py               (ConvertPitchToMarkdownTask)
├── identify_task_dependencies.py              (IdentifyTaskDependenciesTask)
├── estimate_task_durations.py                 (EstimateTaskDurationsTask)
├── create_wbs_level3.py                       (CreateWBSLevel3Task)
├── wbs_project_level1_level2_level3.py        (WBSProjectLevel1AndLevel2AndLevel3Task)
│
│  # Phase 12: Schedule & Final Review
├── create_schedule.py                         (CreateScheduleTask)
├── review_plan.py                             (ReviewPlanTask)
├── executive_summary.py                       (ExecutiveSummaryTask)
├── questions_and_answers.py                   (QuestionsAndAnswersTask)
├── premortem.py                               (PremortemTask)
├── self_audit.py                              (SelfAuditTask)
│
│  # Phase 13: Report
└── report.py                                  (ReportTask)
```

## DAG Insertion Example

To insert a new `ValidateBudgetTask` between `CurrencyStrategyTask` and `IdentifyRisksTask`:

1. Create `stages/validate_budget.py`:
   ```python
   from worker_plan_internal.plan.nodes.currency_strategy import CurrencyStrategyTask

   class ValidateBudgetTask(PlanTask):
       def requires(self):
           return self.clone(CurrencyStrategyTask)
       # ...
   ```

2. Edit `stages/identify_risks.py` — change its `requires()` to depend on `ValidateBudgetTask` instead of `CurrencyStrategyTask`.

3. Add one line to `stages/full_plan_pipeline.py`'s `requires()` dict.

Only 3 files touched. No other stage files are affected.

## What Does NOT Change

- No behavioral changes — identical DAG, identical task execution, identical output files
- No new dependencies
- No changes to Luigi task parameters, output filenames, or callback mechanisms
- No changes to `worker_plan_database/app.py` (imports `ExecutePipeline` from `run_plan_pipeline`, which stays)
- No changes to `test_step_label.py` (imports `_task_class_to_step_label` from `run_plan_pipeline`, which stays)
- The `__main__` entry point still works: `python -m worker_plan_internal.plan.run_plan_pipeline`

## Code Movement Rules

1. **Verbatim extraction** — task class bodies are moved exactly as-is, no logic changes.
2. **Each file gets only the imports it needs** — no bulk import block copied to every file.
3. **The `REPORT_EXECUTE_PLAN_SECTION_HIDDEN` constant** stays in `run_plan_pipeline.py` since it's used by `ReportTask`. `stages/report.py` imports it from there.

## AGENTS.md Update

`worker_plan/AGENTS.md` will be updated to document:
- The `stages/` directory and the one-file-per-task convention
- How to add a new pipeline stage (create file, wire `requires()`, add to `FullPlanPipeline`)
- That `run_plan_pipeline.py` contains only shared framework, not task implementations

## Risks

1. **Circular imports**: `stages/*.py` files import `PlanTask` from `run_plan_pipeline.py`. `run_plan_pipeline.py` imports `FullPlanPipeline` from `stages/full_plan_pipeline.py` (only inside `ExecutePipeline.setup()`, not at module level). No circularity because the cross-import is deferred to method call time.

2. **Luigi task discovery**: Luigi resolves tasks via `requires()` chains starting from `FullPlanPipeline`. Since each stage file imports its upstream tasks, all task classes are loaded when `FullPlanPipeline` is imported. No registration mechanism needed.

3. **`self_improve/` runner compatibility**: The runner imports and executes step source files directly. After the split, individual step executor classes (like `IdentifyPotentialLevers`) still live in their original locations (`worker_plan_internal/lever/`). The Luigi task wrappers move to `stages/`, but `self_improve/` doesn't import those — it imports the executor classes directly. No changes needed.
