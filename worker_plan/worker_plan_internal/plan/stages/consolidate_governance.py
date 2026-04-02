"""ConsolidateGovernanceTask - Combines all governance phase markdown documents."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.governance_phase1_audit import GovernancePhase1AuditTask
from worker_plan_internal.plan.stages.governance_phase2_bodies import GovernancePhase2BodiesTask
from worker_plan_internal.plan.stages.governance_phase3_impl_plan import GovernancePhase3ImplPlanTask
from worker_plan_internal.plan.stages.governance_phase4_decision_escalation_matrix import GovernancePhase4DecisionEscalationMatrixTask
from worker_plan_internal.plan.stages.governance_phase5_monitoring_progress import GovernancePhase5MonitoringProgressTask
from worker_plan_internal.plan.stages.governance_phase6_extra import GovernancePhase6ExtraTask


class ConsolidateGovernanceTask(PlanTask):
    def requires(self):
        return {
            'governance_phase1_audit': self.clone(GovernancePhase1AuditTask),
            'governance_phase2_bodies': self.clone(GovernancePhase2BodiesTask),
            'governance_phase3_impl_plan': self.clone(GovernancePhase3ImplPlanTask),
            'governance_phase4_decision_escalation_matrix': self.clone(GovernancePhase4DecisionEscalationMatrixTask),
            'governance_phase5_monitoring_progress': self.clone(GovernancePhase5MonitoringProgressTask),
            'governance_phase6_extra': self.clone(GovernancePhase6ExtraTask)
        }

    def output(self):
        return self.local_target(FilenameEnum.CONSOLIDATE_GOVERNANCE_MARKDOWN)

    def run_inner(self):
        # Read inputs from required tasks.
        with self.input()['governance_phase1_audit']['markdown'].open("r") as f:
            governance_phase1_audit_markdown = f.read()
        with self.input()['governance_phase2_bodies']['markdown'].open("r") as f:
            governance_phase2_bodies_markdown = f.read()
        with self.input()['governance_phase3_impl_plan']['markdown'].open("r") as f:
            governance_phase3_impl_plan_markdown = f.read()
        with self.input()['governance_phase4_decision_escalation_matrix']['markdown'].open("r") as f:
            governance_phase4_decision_escalation_matrix_markdown = f.read()
        with self.input()['governance_phase5_monitoring_progress']['markdown'].open("r") as f:
            governance_phase5_monitoring_progress_markdown = f.read()
        with self.input()['governance_phase6_extra']['markdown'].open("r") as f:
            governance_phase6_extra_markdown = f.read()

        # Build the document.
        markdown = []
        markdown.append(f"# Governance Audit\n\n{governance_phase1_audit_markdown}")
        markdown.append(f"# Internal Governance Bodies\n\n{governance_phase2_bodies_markdown}")
        markdown.append(f"# Governance Implementation Plan\n\n{governance_phase3_impl_plan_markdown}")
        markdown.append(f"# Decision Escalation Matrix\n\n{governance_phase4_decision_escalation_matrix_markdown}")
        markdown.append(f"# Monitoring Progress\n\n{governance_phase5_monitoring_progress_markdown}")
        markdown.append(f"# Governance Extra\n\n{governance_phase6_extra_markdown}")

        content = "\n\n".join(markdown)

        with self.output().open("w") as f:
            f.write(content)
