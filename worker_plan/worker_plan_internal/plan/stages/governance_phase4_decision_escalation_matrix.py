"""GovernancePhase4DecisionEscalationMatrixTask - Decision escalation matrix."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.governance.governance_phase4_decision_escalation_matrix import GovernancePhase4DecisionEscalationMatrix
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.setup import SetupTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.governance_phase2_bodies import GovernancePhase2BodiesTask
from worker_plan_internal.plan.stages.governance_phase3_impl_plan import GovernancePhase3ImplPlanTask

logger = logging.getLogger(__name__)


class GovernancePhase4DecisionEscalationMatrixTask(PlanTask):
    """Establish decision-making authority and escalation pathways."""

    def requires(self):
        return {
            'setup': self.clone(SetupTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'governance_phase2_bodies': self.clone(GovernancePhase2BodiesTask),
            'governance_phase3_impl_plan': self.clone(GovernancePhase3ImplPlanTask)
        }

    def output(self):
        return {
            'raw': self.local_target(FilenameEnum.GOVERNANCE_PHASE4_DECISION_ESCALATION_MATRIX_RAW),
            'markdown': self.local_target(FilenameEnum.GOVERNANCE_PHASE4_DECISION_ESCALATION_MATRIX_MARKDOWN)
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
        with self.input()['governance_phase2_bodies']['raw'].open("r") as f:
            governance_phase2_bodies_dict = json.load(f)
        with self.input()['governance_phase3_impl_plan']['raw'].open("r") as f:
            governance_phase3_impl_plan_dict = json.load(f)

        # Build the query.
        query = (
            f"File 'initial-plan.txt':\n{plan_prompt}\n\n"
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{consolidate_assumptions_markdown}\n\n"
            f"File 'project-plan.json':\n{format_json_for_use_in_query(project_plan_dict)}\n\n"
            f"File 'governance-phase2-bodies.json':\n{format_json_for_use_in_query(governance_phase2_bodies_dict)}\n\n"
            f"File 'governance-phase3-impl-plan.json':\n{format_json_for_use_in_query(governance_phase3_impl_plan_dict)}"
        )

        # Execute.
        try:
            governance_phase4_decision_escalation_matrix = GovernancePhase4DecisionEscalationMatrix.execute(llm, query)
        except Exception as e:
            logger.error("GovernancePhase4DecisionEscalationMatrix failed: %s", e)
            raise

        # Save the results.
        governance_phase4_decision_escalation_matrix.save_raw(self.output()['raw'].path)
        governance_phase4_decision_escalation_matrix.save_markdown(self.output()['markdown'].path)
