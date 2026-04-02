# Split run_plan_pipeline.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract ~66 Luigi task classes from `run_plan_pipeline.py` (4,257 lines) into individual files under `stages/`, leaving only the shared framework in the original file.

**Architecture:** Each task class moves verbatim to its own file under `worker_plan/worker_plan_internal/plan/stages/`. Each file imports `PlanTask` from `run_plan_pipeline` and its upstream task dependencies from sibling stage files. `FullPlanPipeline` moves to `stages/full_plan_pipeline.py`. `run_plan_pipeline.py` shrinks to ~280 lines keeping only `PlanTask`, `ExecutePipeline`, and supporting utilities.

**Tech Stack:** Python 3.11, Luigi (task orchestration), llama_index

**Spec:** `docs/superpowers/specs/2026-04-02-split-run-plan-pipeline-design.md`

---

## Reference: Source File

All task classes are extracted verbatim from:
`worker_plan/worker_plan_internal/plan/run_plan_pipeline.py`

The source file is referred to as `SOURCE` below. When a step says "copy lines X-Y from SOURCE", it means copy those lines verbatim — no modifications to the task class body.

## How Each Stage File Is Structured

Every stage file follows this exact pattern:

```python
"""Pipeline stage: <description>."""
<imports>

logger = logging.getLogger(__name__)  # only if the task class uses logger

class FooTask(PlanTask):
    # ... verbatim from SOURCE
```

The import block is the ONLY new code per file. The class body is a verbatim copy.

---

### Task 1: Create stages/ directory and Phase 1-2 stages (Input, Validation, Purpose)

**Files:**
- Create: `worker_plan/worker_plan_internal/plan/stages/__init__.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/start_time.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/setup.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/redline_gate.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/premise_attack.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/identify_purpose.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/plan_type.py`

- [ ] **Step 1: Create the stages directory with empty `__init__.py`**

```python
# worker_plan/worker_plan_internal/plan/stages/__init__.py
```

(Empty file — stage files are imported directly by whoever needs them.)

- [ ] **Step 2: Create `stages/start_time.py`**

```python
"""Pipeline stage: record pipeline start timestamp."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
```

Copy the `StartTimeTask` class from SOURCE lines 217-225 verbatim after the imports.

- [ ] **Step 3: Create `stages/setup.py`**

```python
"""Pipeline stage: load initial plan prompt."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
```

Copy `SetupTask` from SOURCE lines 228-236 verbatim.

- [ ] **Step 4: Create `stages/redline_gate.py`**

```python
"""Pipeline stage: preliminary validation of the plan."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.redline_gate import RedlineGate
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
```

Copy `RedlineGateTask` from SOURCE lines 239-260 verbatim.

- [ ] **Step 5: Create `stages/premise_attack.py`**

```python
"""Pipeline stage: challenge foundational assumptions."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.premise_attack import PremiseAttack
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
```

Copy `PremiseAttackTask` from SOURCE lines 263-286 verbatim.

- [ ] **Step 6: Create `stages/identify_purpose.py`**

```python
"""Pipeline stage: determine plan purpose (business/personal/other)."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.identify_purpose import IdentifyPurpose
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
```

Copy `IdentifyPurposeTask` from SOURCE lines 289-313 verbatim.

- [ ] **Step 7: Create `stages/plan_type.py`**

```python
"""Pipeline stage: determine if plan is digital-only or physical."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.identify_plan_type import IdentifyPlanType
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
```

Copy `PlanTypeTask` from SOURCE lines 316-350 verbatim.

- [ ] **Step 8: Verify imports resolve**

Run from `worker_plan/`:
```bash
python -c "from worker_plan_internal.plan.stages.plan_type import PlanTypeTask; print('OK')"
```
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 1-2 pipeline stages to individual files

Extract StartTimeTask, SetupTask, RedlineGateTask, PremiseAttackTask,
IdentifyPurposeTask, PlanTypeTask into stages/ directory."
```

---

### Task 2: Phase 3 stages (Strategic Options & Scenarios)

**Files:**
- Create: `worker_plan/worker_plan_internal/plan/stages/potential_levers.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/deduplicate_levers.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/enrich_levers.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/focus_on_vital_few_levers.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/strategic_decisions_markdown.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/candidate_scenarios.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/select_scenario.py`
- Create: `worker_plan/worker_plan_internal/plan/stages/scenarios_markdown.py`

- [ ] **Step 1: Create `stages/potential_levers.py`**

```python
"""Pipeline stage: identify potential strategic levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.identify_potential_levers import IdentifyPotentialLevers
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
```

Copy `PotentialLeversTask` from SOURCE lines 352-392 verbatim.

- [ ] **Step 2: Create `stages/deduplicate_levers.py`**

```python
"""Pipeline stage: remove redundant levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.deduplicate_levers import DeduplicateLevers
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.potential_levers import PotentialLeversTask
```

Copy `DeduplicateLeversTask` from SOURCE lines 395-439 verbatim.

- [ ] **Step 3: Create `stages/enrich_levers.py`**

```python
"""Pipeline stage: enrich levers with additional information."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.enrich_potential_levers import EnrichPotentialLevers
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.deduplicate_levers import DeduplicateLeversTask
```

Copy `EnrichLeversTask` from SOURCE lines 441-486 verbatim.

- [ ] **Step 4: Create `stages/focus_on_vital_few_levers.py`**

```python
"""Pipeline stage: apply 80/20 principle to select vital levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.focus_on_vital_few_levers import FocusOnVitalFewLevers
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.enrich_levers import EnrichLeversTask
```

Copy `FocusOnVitalFewLeversTask` from SOURCE lines 488-532 verbatim.

- [ ] **Step 5: Create `stages/strategic_decisions_markdown.py`**

```python
"""Pipeline stage: consolidate strategic decisions to markdown."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.strategic_decisions_markdown import StrategicDecisionsMarkdown
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.enrich_levers import EnrichLeversTask
from worker_plan_internal.plan.stages.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
```

Copy `StrategicDecisionsMarkdownTask` from SOURCE lines 535-561 verbatim.

- [ ] **Step 6: Create `stages/candidate_scenarios.py`**

```python
"""Pipeline stage: generate candidate scenarios from vital levers."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.candidate_scenarios import CandidateScenarios
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
```

Copy `CandidateScenariosTask` from SOURCE lines 563-610 verbatim.

- [ ] **Step 7: Create `stages/select_scenario.py`**

```python
"""Pipeline stage: select the best scenario."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.select_scenario import SelectScenario
from worker_plan_internal.llm_util.llm_executor import LLMExecutor
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
from worker_plan_internal.plan.stages.candidate_scenarios import CandidateScenariosTask
```

Copy `SelectScenarioTask` from SOURCE lines 613-665 verbatim.

- [ ] **Step 8: Create `stages/scenarios_markdown.py`**

```python
"""Pipeline stage: present scenarios in human-readable markdown."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.lever.scenarios_markdown import ScenariosMarkdown
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.candidate_scenarios import CandidateScenariosTask
from worker_plan_internal.plan.stages.select_scenario import SelectScenarioTask
```

Copy `ScenariosMarkdownTask` from SOURCE lines 668-695 verbatim.

- [ ] **Step 9: Verify imports resolve**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask; print('OK')"
```

- [ ] **Step 10: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 3 pipeline stages (levers & scenarios)"
```

---

### Task 3: Phase 4-5 stages (Context & Assumptions)

**Files:**
- Create: `stages/physical_locations.py` — `PhysicalLocationsTask` (SOURCE lines 698-761)
- Create: `stages/currency_strategy.py` — `CurrencyStrategyTask` (SOURCE lines 763-813)
- Create: `stages/identify_risks.py` — `IdentifyRisksTask` (SOURCE lines 816-870)
- Create: `stages/make_assumptions.py` — `MakeAssumptionsTask` (SOURCE lines 873-934)
- Create: `stages/distill_assumptions.py` — `DistillAssumptionsTask` (SOURCE lines 937-984)
- Create: `stages/review_assumptions.py` — `ReviewAssumptionsTask` (SOURCE lines 987-1047)
- Create: `stages/consolidate_assumptions_markdown.py` — `ConsolidateAssumptionsMarkdownTask` (SOURCE lines 1050-1132)

Each file needs these common imports plus task-specific ones:

- [ ] **Step 1: Create `stages/physical_locations.py`**

```python
"""Pipeline stage: identify physical locations for the plan."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.physical_locations import PhysicalLocations
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask

logger = logging.getLogger(__name__)
```

Copy `PhysicalLocationsTask` from SOURCE lines 698-761 verbatim.

- [ ] **Step 2: Create `stages/currency_strategy.py`**

```python
"""Pipeline stage: determine currency and financial strategy."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.currency_strategy import CurrencyStrategy
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
```

Copy `CurrencyStrategyTask` from SOURCE lines 763-813 verbatim.

- [ ] **Step 3: Create `stages/identify_risks.py`**

```python
"""Pipeline stage: identify risks based on locations and strategy."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.identify_risks import IdentifyRisks
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
```

Copy `IdentifyRisksTask` from SOURCE lines 816-870 verbatim.

- [ ] **Step 4: Create `stages/make_assumptions.py`**

```python
"""Pipeline stage: make initial assumptions about the plan."""
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.make_assumptions import MakeAssumptions
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.stages.identify_risks import IdentifyRisksTask
```

Copy `MakeAssumptionsTask` from SOURCE lines 873-934 verbatim.

- [ ] **Step 5: Create `stages/distill_assumptions.py`**

```python
"""Pipeline stage: distill and consolidate raw assumptions."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.distill_assumptions import DistillAssumptions
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.make_assumptions import MakeAssumptionsTask
```

Copy `DistillAssumptionsTask` from SOURCE lines 937-984 verbatim.

- [ ] **Step 6: Create `stages/review_assumptions.py`**

```python
"""Pipeline stage: review and find issues with assumptions."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.review_assumptions import ReviewAssumptions
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.stages.identify_risks import IdentifyRisksTask
from worker_plan_internal.plan.stages.make_assumptions import MakeAssumptionsTask
from worker_plan_internal.plan.stages.distill_assumptions import DistillAssumptionsTask

logger = logging.getLogger(__name__)
```

Copy `ReviewAssumptionsTask` from SOURCE lines 987-1047 verbatim.

- [ ] **Step 7: Create `stages/consolidate_assumptions_markdown.py`**

```python
"""Pipeline stage: combine assumption documents into one markdown."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.assume.shorten_markdown import ShortenMarkdown
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.stages.identify_risks import IdentifyRisksTask
from worker_plan_internal.plan.stages.make_assumptions import MakeAssumptionsTask
from worker_plan_internal.plan.stages.distill_assumptions import DistillAssumptionsTask
from worker_plan_internal.plan.stages.review_assumptions import ReviewAssumptionsTask

logger = logging.getLogger(__name__)
```

Copy `ConsolidateAssumptionsMarkdownTask` from SOURCE lines 1050-1132 verbatim.

- [ ] **Step 8: Verify and commit**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask; print('OK')"
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 4-5 pipeline stages (context & assumptions)"
```

---

### Task 4: Phase 6-7 stages (Plan Foundation & Governance)

**Files:**
- Create: `stages/pre_project_assessment.py` — `PreProjectAssessmentTask` (SOURCE lines 1135-1183)
- Create: `stages/project_plan.py` — `ProjectPlanTask` (SOURCE lines 1185-1241)
- Create: `stages/governance_phase1_audit.py` — `GovernancePhase1AuditTask` (SOURCE lines 1244-1291)
- Create: `stages/governance_phase2_bodies.py` — `GovernancePhase2BodiesTask` (SOURCE lines 1294-1345)
- Create: `stages/governance_phase3_impl_plan.py` — `GovernancePhase3ImplPlanTask` (SOURCE lines 1348-1399)
- Create: `stages/governance_phase4_decision_escalation_matrix.py` — `GovernancePhase4DecisionEscalationMatrixTask` (SOURCE lines 1401-1456)
- Create: `stages/governance_phase5_monitoring_progress.py` — `GovernancePhase5MonitoringProgressTask` (SOURCE lines 1458-1517)
- Create: `stages/governance_phase6_extra.py` — `GovernancePhase6ExtraTask` (SOURCE lines 1519-1586)
- Create: `stages/consolidate_governance.py` — `ConsolidateGovernanceTask` (SOURCE lines 1588-1629)

For each file, follow this pattern:

- [ ] **Step 1: Create `stages/pre_project_assessment.py`**

```python
"""Pipeline stage: pre-project feasibility assessment."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.expert.pre_project_assessment import PreProjectAssessment
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask

logger = logging.getLogger(__name__)
```

Copy `PreProjectAssessmentTask` from SOURCE lines 1135-1183 verbatim.

- [ ] **Step 2: Create `stages/project_plan.py`**

```python
"""Pipeline stage: generate the main project plan."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.plan.project_plan import ProjectPlan
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.pre_project_assessment import PreProjectAssessmentTask

logger = logging.getLogger(__name__)
```

Copy `ProjectPlanTask` from SOURCE lines 1185-1241 verbatim.

- [ ] **Step 3: Create all 7 governance stage files**

Each governance file follows the same pattern. The imports for each are:

**`stages/governance_phase1_audit.py`** (SOURCE lines 1244-1291):
```python
"""Pipeline stage: governance audit."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.governance.governance_phase1_audit import GovernancePhase1Audit
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask

logger = logging.getLogger(__name__)
```

**`stages/governance_phase2_bodies.py`** (SOURCE lines 1294-1345):
```python
"""Pipeline stage: identify governance bodies."""
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.governance.governance_phase2_bodies import GovernancePhase2Bodies
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.governance_phase1_audit import GovernancePhase1AuditTask

logger = logging.getLogger(__name__)
```

**`stages/governance_phase3_impl_plan.py`** (SOURCE lines 1348-1399):
```python
"""Pipeline stage: governance implementation plan."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.governance.governance_phase3_impl_plan import GovernancePhase3ImplPlan
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.governance_phase2_bodies import GovernancePhase2BodiesTask

logger = logging.getLogger(__name__)
```

**`stages/governance_phase4_decision_escalation_matrix.py`** (SOURCE lines 1401-1456):
Same pattern. Imports `GovernancePhase4DecisionEscalationMatrix` from `worker_plan_internal.governance.governance_phase4_decision_escalation_matrix`. Upstream tasks: SetupTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask, GovernancePhase2BodiesTask, GovernancePhase3ImplPlanTask. Uses `json`, `format_json_for_use_in_query`.

**`stages/governance_phase5_monitoring_progress.py`** (SOURCE lines 1458-1517):
Same pattern. Imports `GovernancePhase5MonitoringProgress`. Upstream adds `GovernancePhase4DecisionEscalationMatrixTask`. Uses `json`, `format_json_for_use_in_query`.

**`stages/governance_phase6_extra.py`** (SOURCE lines 1519-1586):
Same pattern. Imports `GovernancePhase6Extra`. Upstream includes all governance phases 1-5. Uses `json`, `format_json_for_use_in_query`.

**`stages/consolidate_governance.py`** (SOURCE lines 1588-1629):
```python
"""Pipeline stage: consolidate all governance phases into one document."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.governance_phase1_audit import GovernancePhase1AuditTask
from worker_plan_internal.plan.stages.governance_phase2_bodies import GovernancePhase2BodiesTask
from worker_plan_internal.plan.stages.governance_phase3_impl_plan import GovernancePhase3ImplPlanTask
from worker_plan_internal.plan.stages.governance_phase4_decision_escalation_matrix import GovernancePhase4DecisionEscalationMatrixTask
from worker_plan_internal.plan.stages.governance_phase5_monitoring_progress import GovernancePhase5MonitoringProgressTask
from worker_plan_internal.plan.stages.governance_phase6_extra import GovernancePhase6ExtraTask
```

- [ ] **Step 4: Verify and commit**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.consolidate_governance import ConsolidateGovernanceTask; print('OK')"
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 6-7 pipeline stages (plan foundation & governance)"
```

---

### Task 5: Phase 8 stages (Team)

**Files:**
- Create: `stages/related_resources.py` — `RelatedResourcesTask` (SOURCE lines 1631-1678)
- Create: `stages/find_team_members.py` — `FindTeamMembersTask` (SOURCE lines 1680-1741)
- Create: `stages/enrich_team_contract_type.py` — `EnrichTeamMembersWithContractTypeTask` (SOURCE lines 1743-1808)
- Create: `stages/enrich_team_background_story.py` — `EnrichTeamMembersWithBackgroundStoryTask` (SOURCE lines 1810-1887)
- Create: `stages/enrich_team_environment_info.py` — `EnrichTeamMembersWithEnvironmentInfoTask` (SOURCE lines 1889-1954)
- Create: `stages/review_team.py` — `ReviewTeamTask` (SOURCE lines 1956-2020)
- Create: `stages/team_markdown.py` — `TeamMarkdownTask` (SOURCE lines 2022-2053)

Each file imports `PlanTask`, its executor class, `FilenameEnum`, and its upstream task(s) from sibling stages.

Key imports per file:

- `related_resources.py`: executor `RelatedResources` from `worker_plan_internal.plan.related_resources`. Upstreams: SetupTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `find_team_members.py`: executor `FindTeamMembers` from `worker_plan_internal.team.find_team_members`. Upstreams: SetupTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, PreProjectAssessmentTask, ProjectPlanTask, RelatedResourcesTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `enrich_team_contract_type.py`: executor `EnrichTeamMembersWithContractType`. Upstreams: same as find + FindTeamMembersTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `enrich_team_background_story.py`: executor `EnrichTeamMembersWithBackgroundStory`. Upstreams: same + EnrichTeamMembersWithContractTypeTask. Also imports `SpeedVsDetailEnum` from `worker_plan_api.speedvsdetail` (for FAST_BUT_SKIP_DETAILS check). Uses `json`, `logging`, `format_json_for_use_in_query`.

- `enrich_team_environment_info.py`: executor `EnrichTeamMembersWithEnvironmentInfo`. Upstreams: same but depends on BackgroundStoryTask instead of ContractTypeTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `review_team.py`: executor `ReviewTeam` + `TeamMarkdownDocumentBuilder` from `worker_plan_internal.team.team_markdown_document`. Upstreams: SetupTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, PreProjectAssessmentTask, ProjectPlanTask, EnrichTeamMembersWithEnvironmentInfoTask, RelatedResourcesTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `team_markdown.py`: `TeamMarkdownDocumentBuilder` from `worker_plan_internal.team.team_markdown_document`. Upstreams: EnrichTeamMembersWithEnvironmentInfoTask, ReviewTeamTask. Uses `json`, `logging`.

- [ ] **Step 1: Create all 7 team stage files following the pattern above**

- [ ] **Step 2: Verify and commit**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.team_markdown import TeamMarkdownTask; print('OK')"
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 8 pipeline stages (team)"
```

---

### Task 6: Phase 9-10 stages (Analysis & Documents)

**Files:**
- Create: `stages/swot_analysis.py` — `SWOTAnalysisTask` (SOURCE lines 2055-2123)
- Create: `stages/expert_review.py` — `ExpertReviewTask` (SOURCE lines 2125-2194)
- Create: `stages/data_collection.py` — `DataCollectionTask` (SOURCE lines 2197-2257)
- Create: `stages/identify_documents.py` — `IdentifyDocumentsTask` (SOURCE lines 2259-2328)
- Create: `stages/filter_documents_to_find.py` — `FilterDocumentsToFindTask` (SOURCE lines 2330-2387)
- Create: `stages/filter_documents_to_create.py` — `FilterDocumentsToCreateTask` (SOURCE lines 2389-2446)
- Create: `stages/draft_documents_to_find.py` — `DraftDocumentsToFindTask` (SOURCE lines 2448-2532)
- Create: `stages/draft_documents_to_create.py` — `DraftDocumentsToCreateTask` (SOURCE lines 2534-2618)
- Create: `stages/markdown_documents.py` — `MarkdownWithDocumentsToCreateAndFindTask` (SOURCE lines 2620-2656)

Key imports per file:

- `swot_analysis.py`: executor `SWOTAnalysis` from `worker_plan_internal.swot.swot_analysis`. Upstreams: SetupTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, IdentifyPurposeTask, ConsolidateAssumptionsMarkdownTask, PreProjectAssessmentTask, ProjectPlanTask, RelatedResourcesTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `expert_review.py`: executors `ExpertFinder` from `worker_plan_internal.expert.expert_finder`, `ExpertCriticism` from `worker_plan_internal.expert.expert_criticism`, `ExpertOrchestrator` from `worker_plan_internal.expert.expert_orchestrator`. Also `LLMExecutor` from `worker_plan_internal.llm_util.llm_executor`. Upstreams: SetupTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, PreProjectAssessmentTask, ProjectPlanTask, SWOTAnalysisTask. Uses `json`, `logging`, `format_json_for_use_in_query`, `FilenameEnum`.

- `data_collection.py`: executor `DataCollection` from `worker_plan_internal.plan.data_collection`. Upstreams: StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask, RelatedResourcesTask, SWOTAnalysisTask, TeamMarkdownTask, ExpertReviewTask.

- `identify_documents.py`: executor `IdentifyDocuments` from `worker_plan_internal.document.identify_documents`. Upstreams: IdentifyPurposeTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask, RelatedResourcesTask, SWOTAnalysisTask, TeamMarkdownTask, ExpertReviewTask. Uses `json`.

- `filter_documents_to_find.py`: executor `FilterDocumentsToFind` from `worker_plan_internal.document.filter_documents_to_find`. Upstreams: IdentifyPurposeTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask, IdentifyDocumentsTask. Uses `json`.

- `filter_documents_to_create.py`: executor `FilterDocumentsToCreate` from `worker_plan_internal.document.filter_documents_to_create`. Same upstreams as filter_to_find.

- `draft_documents_to_find.py`: executor `DraftDocumentToFind` from `worker_plan_internal.document.draft_document_to_find`. Also `LLMExecutor, PipelineStopRequested` from `worker_plan_internal.llm_util.llm_executor`, `SpeedVsDetailEnum`. Upstreams: IdentifyPurposeTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask, FilterDocumentsToFindTask. Uses `json`, `logging`.

- `draft_documents_to_create.py`: executor `DraftDocumentToCreate` from `worker_plan_internal.document.draft_document_to_create`. Same pattern as draft_to_find, but depends on FilterDocumentsToCreateTask.

- `markdown_documents.py`: `markdown_rows_with_document_to_create, markdown_rows_with_document_to_find` from `worker_plan_internal.document.markdown_with_document`. Upstreams: DraftDocumentsToCreateTask, DraftDocumentsToFindTask. Uses `json`.

- [ ] **Step 1: Create all 9 files**

- [ ] **Step 2: Verify and commit**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.markdown_documents import MarkdownWithDocumentsToCreateAndFindTask; print('OK')"
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 9-10 pipeline stages (analysis & documents)"
```

---

### Task 7: Phase 11 stages (WBS & Pitch)

**Files:**
- Create: `stages/create_wbs_level1.py` — `CreateWBSLevel1Task` (SOURCE lines 2658-2706)
- Create: `stages/create_wbs_level2.py` — `CreateWBSLevel2Task` (SOURCE lines 2708-2768)
- Create: `stages/wbs_project_level1_and_level2.py` — `WBSProjectLevel1AndLevel2Task` (SOURCE lines 2770-2795)
- Create: `stages/create_pitch.py` — `CreatePitchTask` (SOURCE lines 2797-2853)
- Create: `stages/convert_pitch_to_markdown.py` — `ConvertPitchToMarkdownTask` (SOURCE lines 2855-2888)
- Create: `stages/identify_task_dependencies.py` — `IdentifyTaskDependenciesTask` (SOURCE lines 2891-2939)
- Create: `stages/estimate_task_durations.py` — `EstimateTaskDurationsTask` (SOURCE lines 2941-3041)
- Create: `stages/create_wbs_level3.py` — `CreateWBSLevel3Task` (SOURCE lines 3043-3158)
- Create: `stages/wbs_project_level1_level2_level3.py` — `WBSProjectLevel1AndLevel2AndLevel3Task` (SOURCE lines 3160-3195)

Key imports:

- `create_wbs_level1.py`: executor `CreateWBSLevel1` from `worker_plan_internal.plan.create_wbs_level1`. Upstreams: ProjectPlanTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `create_wbs_level2.py`: executor `CreateWBSLevel2`. Upstreams: StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ProjectPlanTask, CreateWBSLevel1Task, DataCollectionTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `wbs_project_level1_and_level2.py`: `WBSPopulate` from `worker_plan_internal.wbs.wbs_populate`. Upstreams: CreateWBSLevel1Task, CreateWBSLevel2Task. Uses `json`.

- `create_pitch.py`: executor `CreatePitch` from `worker_plan_internal.pitch.create_pitch`, `WBSProject` from `worker_plan_internal.wbs.wbs_task`. Upstreams: StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ProjectPlanTask, WBSProjectLevel1AndLevel2Task, RelatedResourcesTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `convert_pitch_to_markdown.py`: executor `ConvertPitchToMarkdown` from `worker_plan_internal.pitch.convert_pitch_to_markdown`. Upstreams: CreatePitchTask. Uses `json`, `format_json_for_use_in_query`.

- `identify_task_dependencies.py`: executor `IdentifyWBSTaskDependencies` from `worker_plan_internal.plan.identify_wbs_task_dependencies`. Upstreams: StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ProjectPlanTask, CreateWBSLevel2Task, DataCollectionTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `estimate_task_durations.py`: executor `EstimateWBSTaskDurations` from `worker_plan_internal.plan.estimate_wbs_task_durations`, `WBSProject` from `worker_plan_internal.wbs.wbs_task`. Also `LLMExecutor, PipelineStopRequested` from `worker_plan_internal.llm_util.llm_executor`, `SpeedVsDetailEnum`. Upstreams: ProjectPlanTask, WBSProjectLevel1AndLevel2Task. Uses `json`, `logging`.

- `create_wbs_level3.py`: executor `CreateWBSLevel3` from `worker_plan_internal.plan.create_wbs_level3`, `WBSProject` from `worker_plan_internal.wbs.wbs_task`, `WBSPopulate` from `worker_plan_internal.wbs.wbs_populate`. Also `LLMExecutor, PipelineStopRequested`, `SpeedVsDetailEnum`. Upstreams: ProjectPlanTask, WBSProjectLevel1AndLevel2Task, EstimateTaskDurationsTask, DataCollectionTask. Uses `json`, `logging`, `format_json_for_use_in_query`.

- `wbs_project_level1_level2_level3.py`: `WBSProject` from `worker_plan_internal.wbs.wbs_task`, `WBSPopulate` from `worker_plan_internal.wbs.wbs_populate`. Upstreams: WBSProjectLevel1AndLevel2Task, CreateWBSLevel3Task. Uses `json`.

- [ ] **Step 1: Create all 9 files**

- [ ] **Step 2: Verify and commit**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.wbs_project_level1_level2_level3 import WBSProjectLevel1AndLevel2AndLevel3Task; print('OK')"
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 11 pipeline stages (WBS & pitch)"
```

---

### Task 8: Phase 12-13 stages (Schedule, Final Review & Report)

**Files:**
- Create: `stages/create_schedule.py` — `CreateScheduleTask` (SOURCE lines 3197-3288)
- Create: `stages/review_plan.py` — `ReviewPlanTask` (SOURCE lines 3290-3364)
- Create: `stages/executive_summary.py` — `ExecutiveSummaryTask` (SOURCE lines 3367-3443)
- Create: `stages/questions_and_answers.py` — `QuestionsAndAnswersTask` (SOURCE lines 3446-3524)
- Create: `stages/premortem.py` — `PremortemTask` (SOURCE lines 3526-3607)
- Create: `stages/self_audit.py` — `SelfAuditTask` (SOURCE lines 3610-3707)
- Create: `stages/report.py` — `ReportTask` (SOURCE lines 3709-3774)

Key imports:

- `create_schedule.py`: `ProjectSchedulePopulator, ProjectSchedule` from schedule modules, `ExportGanttDHTMLX, ExportGanttCSV` from schedule modules, `WBSProject` from `worker_plan_internal.wbs.wbs_task`, `WBSTaskTooltip` from `worker_plan_internal.wbs.wbs_task_tooltip`, `PIPELINE_CONFIG` from `worker_plan_internal.plan.pipeline_config`. Upstreams: StartTimeTask, CreateWBSLevel1Task, IdentifyTaskDependenciesTask, EstimateTaskDurationsTask, WBSProjectLevel1AndLevel2AndLevel3Task. Uses `json`, `logging`, `datetime`, `typing.Any`.

- `review_plan.py`: executor `ReviewPlan` from `worker_plan_internal.plan.review_plan`. Also `LLMExecutor`. Upstreams: StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, ProjectPlanTask, DataCollectionTask, RelatedResourcesTask, SWOTAnalysisTask, TeamMarkdownTask, ConvertPitchToMarkdownTask, ExpertReviewTask, WBSProjectLevel1AndLevel2AndLevel3Task.

- `executive_summary.py`: executor `ExecutiveSummary` from `worker_plan_internal.plan.executive_summary`. Same upstreams as review_plan + ReviewPlanTask.

- `questions_and_answers.py`: executor `QuestionsAnswers` from `worker_plan_internal.questions_answers.questions_answers`. Upstreams include ConsolidateGovernanceTask, MarkdownWithDocumentsToCreateAndFindTask, ReviewPlanTask.

- `premortem.py`: executor `Premortem` from `worker_plan_internal.diagnostics.premortem`. Also `LLMExecutor` and `SpeedVsDetailEnum`. Same broad upstreams + QuestionsAndAnswersTask.

- `self_audit.py`: executor `SelfAudit` from `worker_plan_internal.self_audit.self_audit`. Also `LLMExecutor`, `SpeedVsDetailEnum`, `Optional` from typing. Same broad upstreams + PremortemTask.

- `report.py`: `ReportGenerator` from `worker_plan_internal.report.report_generator`. Also imports `REPORT_EXECUTE_PLAN_SECTION_HIDDEN` from `worker_plan_internal.plan.run_plan_pipeline`. Upstreams: SetupTask, RedlineGateTask, PremiseAttackTask, StrategicDecisionsMarkdownTask, ScenariosMarkdownTask, ConsolidateAssumptionsMarkdownTask, TeamMarkdownTask, RelatedResourcesTask, ConsolidateGovernanceTask, SWOTAnalysisTask, ConvertPitchToMarkdownTask, DataCollectionTask, MarkdownWithDocumentsToCreateAndFindTask, CreateWBSLevel1Task, WBSProjectLevel1AndLevel2AndLevel3Task, ExpertReviewTask, ProjectPlanTask, ReviewPlanTask, ExecutiveSummaryTask, CreateScheduleTask, QuestionsAndAnswersTask, PremortemTask, SelfAuditTask.

- [ ] **Step 1: Create all 7 files**

- [ ] **Step 2: Verify and commit**

```bash
cd worker_plan && python -c "from worker_plan_internal.plan.stages.report import ReportTask; print('OK')"
git add worker_plan/worker_plan_internal/plan/stages/
git commit -m "refactor: extract Phase 12-13 pipeline stages (schedule, review & report)"
```

---

### Task 9: Create FullPlanPipeline and slim run_plan_pipeline.py

**Files:**
- Create: `worker_plan/worker_plan_internal/plan/stages/full_plan_pipeline.py`
- Modify: `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py`

- [ ] **Step 1: Create `stages/full_plan_pipeline.py`**

This file imports ALL task classes from the stages and defines `FullPlanPipeline`:

```python
"""Pipeline orchestrator: declares all stages as Luigi dependencies."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum

# Phase 1-2: Input & Validation, Purpose
from worker_plan_internal.plan.stages.start_time import StartTimeTask
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.redline_gate import RedlineGateTask
from worker_plan_internal.plan.stages.premise_attack import PremiseAttackTask
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.plan_type import PlanTypeTask

# Phase 3: Strategic Options & Scenarios
from worker_plan_internal.plan.stages.potential_levers import PotentialLeversTask
from worker_plan_internal.plan.stages.deduplicate_levers import DeduplicateLeversTask
from worker_plan_internal.plan.stages.enrich_levers import EnrichLeversTask
from worker_plan_internal.plan.stages.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.candidate_scenarios import CandidateScenariosTask
from worker_plan_internal.plan.stages.select_scenario import SelectScenarioTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask

# Phase 4-5: Context & Assumptions
from worker_plan_internal.plan.stages.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.stages.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.stages.identify_risks import IdentifyRisksTask
from worker_plan_internal.plan.stages.make_assumptions import MakeAssumptionsTask
from worker_plan_internal.plan.stages.distill_assumptions import DistillAssumptionsTask
from worker_plan_internal.plan.stages.review_assumptions import ReviewAssumptionsTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask

# Phase 6-7: Plan Foundation & Governance
from worker_plan_internal.plan.stages.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.governance_phase1_audit import GovernancePhase1AuditTask
from worker_plan_internal.plan.stages.governance_phase2_bodies import GovernancePhase2BodiesTask
from worker_plan_internal.plan.stages.governance_phase3_impl_plan import GovernancePhase3ImplPlanTask
from worker_plan_internal.plan.stages.governance_phase4_decision_escalation_matrix import GovernancePhase4DecisionEscalationMatrixTask
from worker_plan_internal.plan.stages.governance_phase5_monitoring_progress import GovernancePhase5MonitoringProgressTask
from worker_plan_internal.plan.stages.governance_phase6_extra import GovernancePhase6ExtraTask
from worker_plan_internal.plan.stages.consolidate_governance import ConsolidateGovernanceTask

# Phase 8: Team
from worker_plan_internal.plan.stages.related_resources import RelatedResourcesTask
from worker_plan_internal.plan.stages.find_team_members import FindTeamMembersTask
from worker_plan_internal.plan.stages.enrich_team_contract_type import EnrichTeamMembersWithContractTypeTask
from worker_plan_internal.plan.stages.enrich_team_background_story import EnrichTeamMembersWithBackgroundStoryTask
from worker_plan_internal.plan.stages.enrich_team_environment_info import EnrichTeamMembersWithEnvironmentInfoTask
from worker_plan_internal.plan.stages.review_team import ReviewTeamTask
from worker_plan_internal.plan.stages.team_markdown import TeamMarkdownTask

# Phase 9-10: Analysis & Documents
from worker_plan_internal.plan.stages.swot_analysis import SWOTAnalysisTask
from worker_plan_internal.plan.stages.expert_review import ExpertReviewTask
from worker_plan_internal.plan.stages.data_collection import DataCollectionTask
from worker_plan_internal.plan.stages.identify_documents import IdentifyDocumentsTask
from worker_plan_internal.plan.stages.filter_documents_to_find import FilterDocumentsToFindTask
from worker_plan_internal.plan.stages.filter_documents_to_create import FilterDocumentsToCreateTask
from worker_plan_internal.plan.stages.draft_documents_to_find import DraftDocumentsToFindTask
from worker_plan_internal.plan.stages.draft_documents_to_create import DraftDocumentsToCreateTask
from worker_plan_internal.plan.stages.markdown_documents import MarkdownWithDocumentsToCreateAndFindTask

# Phase 11: WBS & Pitch
from worker_plan_internal.plan.stages.create_wbs_level1 import CreateWBSLevel1Task
from worker_plan_internal.plan.stages.create_wbs_level2 import CreateWBSLevel2Task
from worker_plan_internal.plan.stages.wbs_project_level1_and_level2 import WBSProjectLevel1AndLevel2Task
from worker_plan_internal.plan.stages.create_pitch import CreatePitchTask
from worker_plan_internal.plan.stages.convert_pitch_to_markdown import ConvertPitchToMarkdownTask
from worker_plan_internal.plan.stages.identify_task_dependencies import IdentifyTaskDependenciesTask
from worker_plan_internal.plan.stages.estimate_task_durations import EstimateTaskDurationsTask
from worker_plan_internal.plan.stages.create_wbs_level3 import CreateWBSLevel3Task
from worker_plan_internal.plan.stages.wbs_project_level1_level2_level3 import WBSProjectLevel1AndLevel2AndLevel3Task

# Phase 12-13: Schedule, Final Review & Report
from worker_plan_internal.plan.stages.create_schedule import CreateScheduleTask
from worker_plan_internal.plan.stages.review_plan import ReviewPlanTask
from worker_plan_internal.plan.stages.executive_summary import ExecutiveSummaryTask
from worker_plan_internal.plan.stages.questions_and_answers import QuestionsAndAnswersTask
from worker_plan_internal.plan.stages.premortem import PremortemTask
from worker_plan_internal.plan.stages.self_audit import SelfAuditTask
from worker_plan_internal.plan.stages.report import ReportTask
```

Copy the `FullPlanPipeline` class body verbatim from SOURCE lines 3776-3848. The `requires()` dict references all the task classes imported above.

- [ ] **Step 2: Slim `run_plan_pipeline.py`**

Remove:
1. All task class definitions (lines 217-3848) — everything from `class StartTimeTask` through `class FullPlanPipeline` including its methods.
2. All imports that were ONLY used by the removed task classes. Keep imports used by `PlanTask`, `ExecutePipeline`, `configure_logging`, and the `__main__` block.

The remaining imports in `run_plan_pipeline.py` should be:

```python
from dataclasses import dataclass, field
from datetime import date, datetime
import os
import logging
import json
import re
from typing import Any, Optional
import luigi
from pathlib import Path
import sys
from llama_index.core.llms.llm import LLM
from worker_plan_api.filenames import FilenameEnum, ExtraFilenameEnum
from worker_plan_api.pipeline_version import PIPELINE_VERSION
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_internal.utils.planexe_llmconfig import PlanExeLLMConfig
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelFromName, ShouldStopCallbackParameters, PipelineStopRequested, RetryConfig
from worker_plan_internal.llm_factory import get_llm_names_by_priority, SPECIAL_AUTO_ID, is_valid_llm_name
from worker_plan_api.model_profile import ModelProfileEnum, normalize_model_profile
from worker_plan_internal.luigi_util.obtain_output_files import ObtainOutputFiles
from worker_plan_internal.plan.pipeline_environment import PipelineEnvironment
from worker_plan_internal.plan.ping_llm import run_ping_llm_report
```

- [ ] **Step 3: Update `ExecutePipeline.setup()` to use deferred import**

Change the `setup()` method in `ExecutePipeline` (around line 3902 in the original). Replace the direct reference to `FullPlanPipeline` with a deferred import:

```python
def setup(self) -> None:
    # ... existing validation code stays the same ...

    from worker_plan_internal.plan.stages.full_plan_pipeline import FullPlanPipeline
    full_plan_pipeline_task = FullPlanPipeline(
        run_id_dir=self.run_id_dir,
        speedvsdetail=self.speedvsdetail,
        llm_models=self.llm_models,
        _pipeline_executor_callback=self.callback_run_task
    )
    self.full_plan_pipeline_task = full_plan_pipeline_task
    # ... rest of setup() stays the same ...
```

Also update the type hint on `full_plan_pipeline_task` field from `Optional[FullPlanPipeline]` to `Optional[Any]` (since `FullPlanPipeline` is no longer importable at module level):

```python
full_plan_pipeline_task: Optional[Any] = field(default=None)
```

- [ ] **Step 4: Verify the pipeline still works**

```bash
cd worker_plan && python -c "
from worker_plan_internal.plan.run_plan_pipeline import ExecutePipeline, PlanTask, PipelineProgress, HandleTaskCompletionParameters, _task_class_to_step_label
print('All public symbols importable: OK')
print(_task_class_to_step_label('SWOTAnalysisTask'))
"
```

Expected:
```
All public symbols importable: OK
SWOT Analysis
```

- [ ] **Step 5: Run existing tests**

```bash
cd worker_plan && python -m pytest worker_plan_internal/plan/tests/test_step_label.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add worker_plan/worker_plan_internal/plan/stages/full_plan_pipeline.py
git add worker_plan/worker_plan_internal/plan/run_plan_pipeline.py
git commit -m "refactor: slim run_plan_pipeline.py to framework-only, wire FullPlanPipeline from stages"
```

---

### Task 10: Update AGENTS.md and remediation roadmap

**Files:**
- Modify: `worker_plan/AGENTS.md`
- Modify: `docs/proposals/131-codebase-cleanliness-remediation-roadmap.md`

- [ ] **Step 1: Update `worker_plan/AGENTS.md`**

Add a new section after the existing guidelines:

```markdown
## Pipeline Stages (`worker_plan_internal/plan/stages/`)

Each Luigi pipeline task lives in its own file under `stages/`. This enables:
- Multiple agents working on different stages without merge conflicts
- `self_improve/` targeting individual step files
- Easy DAG insertion (create new file, update downstream `requires()`)

### Convention for new stages

1. Create `stages/<stage_name>.py` with one task class
2. Import `PlanTask` from `worker_plan_internal.plan.run_plan_pipeline`
3. Import upstream task dependencies from sibling stage files
4. Declare dependencies via `requires()` returning upstream task(s)
5. Add the new task to `stages/full_plan_pipeline.py`'s `requires()` dict

### Framework location

`run_plan_pipeline.py` contains only shared framework:
- `PlanTask` (base class for all stages)
- `ExecutePipeline`, `HandleTaskCompletionParameters`, `PipelineProgress`
- `_task_class_to_step_label`, `configure_logging`
- `__main__` entry point
```

- [ ] **Step 2: Update remediation roadmap**

In `docs/proposals/131-codebase-cleanliness-remediation-roadmap.md`, mark Issue 1 fix step 3 as done:

Change:
```
3. Convert `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py` from a giant task registry file into a thin pipeline assembly module plus task-specific modules grouped by stage.
```

To:
```
3. ~~Convert `worker_plan/worker_plan_internal/plan/run_plan_pipeline.py` from a giant task registry file into a thin pipeline assembly module plus task-specific modules grouped by stage.~~ **Done**: Split 4,257-line monolith into ~66 individual stage files under `stages/` + framework-only core module.
```

- [ ] **Step 3: Commit**

```bash
git add worker_plan/AGENTS.md docs/proposals/131-codebase-cleanliness-remediation-roadmap.md
git commit -m "docs: update AGENTS.md and remediation roadmap for pipeline split"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run all existing tests**

```bash
cd worker_plan && python -m pytest worker_plan_internal/plan/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify import chain**

```bash
cd worker_plan && python -c "
from worker_plan_internal.plan.stages.full_plan_pipeline import FullPlanPipeline
from worker_plan_internal.plan.run_plan_pipeline import ExecutePipeline
print(f'FullPlanPipeline requires {len(FullPlanPipeline(run_id_dir=\"/tmp/test\").requires())} tasks')
print('Import chain: OK')
"
```

- [ ] **Step 3: Count lines in slimmed run_plan_pipeline.py**

```bash
wc -l worker_plan/worker_plan_internal/plan/run_plan_pipeline.py
```

Expected: ~280 lines (down from 4,257).

- [ ] **Step 4: Count stage files**

```bash
ls worker_plan/worker_plan_internal/plan/stages/*.py | wc -l
```

Expected: ~67 files (66 stages + `__init__.py` + `full_plan_pipeline.py`).
