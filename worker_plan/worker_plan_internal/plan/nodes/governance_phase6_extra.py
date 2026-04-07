"""GovernancePhase6ExtraTask - Extra governance considerations."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.governance.governance_phase6_extra import GovernancePhase6Extra
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.governance_phase1_audit import GovernancePhase1AuditTask
from worker_plan_internal.plan.nodes.governance_phase2_bodies import GovernancePhase2BodiesTask
from worker_plan_internal.plan.nodes.governance_phase3_impl_plan import GovernancePhase3ImplPlanTask
from worker_plan_internal.plan.nodes.governance_phase4_decision_escalation_matrix import GovernancePhase4DecisionEscalationMatrixTask
from worker_plan_internal.plan.nodes.governance_phase5_monitoring_progress import GovernancePhase5MonitoringProgressTask

logger = logging.getLogger(__name__)


class GovernancePhase6ExtraTask(PlanTask):
    """Validate prior governance phases with tough questions and a high-level summary."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'governance_phase1_audit': self.clone(GovernancePhase1AuditTask),
            'governance_phase2_bodies': self.clone(GovernancePhase2BodiesTask),
            'governance_phase3_impl_plan': self.clone(GovernancePhase3ImplPlanTask),
            'governance_phase4_decision_escalation_matrix': self.clone(GovernancePhase4DecisionEscalationMatrixTask),
            'governance_phase5_monitoring_progress': self.clone(GovernancePhase5MonitoringProgressTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.GOVERNANCE_PHASE6_EXTRA_RAW),
            'markdown': self.local_target(FilenameEnum.GOVERNANCE_PHASE6_EXTRA_MARKDOWN)
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['setup'].open("r") as f:
            plan_prompt = f.read()
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            consolidate_assumptions_markdown = f.read()
        with self.input()['project_plan']['raw'].open("r") as f:
            project_plan_dict = json.load(f)
        with self.input()['governance_phase1_audit']['raw'].open("r") as f:
            governance_phase1_audit_dict = json.load(f)
        with self.input()['governance_phase2_bodies']['raw'].open("r") as f:
            governance_phase2_bodies_dict = json.load(f)
        with self.input()['governance_phase3_impl_plan']['raw'].open("r") as f:
            governance_phase3_impl_plan_dict = json.load(f)
        with self.input()['governance_phase4_decision_escalation_matrix']['raw'].open("r") as f:
            governance_phase4_decision_escalation_matrix_dict = json.load(f)
        with self.input()['governance_phase5_monitoring_progress']['raw'].open("r") as f:
            governance_phase5_monitoring_progress_dict = json.load(f)

        # Build the query.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'project-plan.json':\n{format_json_for_use_in_query(project_plan_dict)}\n\n"
            f"File 'governance-phase1-audit.json':\n{format_json_for_use_in_query(governance_phase1_audit_dict)}\n\n"
            f"File 'governance-phase2-bodies.json':\n{format_json_for_use_in_query(governance_phase2_bodies_dict)}\n\n"
            f"File 'governance-phase3-impl-plan.json':\n{format_json_for_use_in_query(governance_phase3_impl_plan_dict)}\n\n"
            f"File 'governance-phase4-decision-escalation-matrix.json':\n{format_json_for_use_in_query(governance_phase4_decision_escalation_matrix_dict)}\n\n"
            f"File 'governance-phase5-monitoring-progress.json':\n{format_json_for_use_in_query(governance_phase5_monitoring_progress_dict)}"
        )

        # Execute.
        try:
            governance_phase6_extra = GovernancePhase6Extra.execute(llm, query)
        except Exception as e:
            logger.error("GovernancePhase6Extra failed: %s", e)
            raise

        # Save the results.
        governance_phase6_extra.save_raw(self.output()['raw'].path)
        governance_phase6_extra.save_markdown(self.output()['markdown'].path)
