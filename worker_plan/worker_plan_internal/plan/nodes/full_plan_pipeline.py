"""Pipeline orchestrator: declares all stages as Luigi dependencies."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum

# Phase 1-2
from worker_plan_internal.plan.nodes.start_time import StartTimeTask
from worker_plan_internal.plan.nodes.setup import SetupTask
from worker_plan_internal.plan.nodes.redline_gate import RedlineGateTask
from worker_plan_internal.plan.nodes.premise_attack import PremiseAttackTask
from worker_plan_internal.plan.nodes.screen_planning_prompt import ScreenPlanningPromptTask
from worker_plan_internal.plan.nodes.extract_constraints import ExtractConstraintsTask
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.plan_type import PlanTypeTask

# Phase 3
from worker_plan_internal.plan.nodes.potential_levers import PotentialLeversTask
from worker_plan_internal.plan.nodes.triage_levers import TriageLeversTask
from worker_plan_internal.plan.nodes.enrich_levers import EnrichLeversTask
from worker_plan_internal.plan.nodes.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.candidate_scenarios import CandidateScenariosTask
from worker_plan_internal.plan.nodes.select_scenario import SelectScenarioTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.constraint_checker_stages import (
    PotentialLeversConstraintTask,
    TriagedLeversConstraintTask,
    EnrichedLeversConstraintTask,
    VitalFewLeversConstraintTask,
    CandidateScenariosConstraintTask,
    SelectedScenarioConstraintTask,
)

# Phase 4-5
from worker_plan_internal.plan.nodes.physical_locations import PhysicalLocationsTask
from worker_plan_internal.plan.nodes.currency_strategy import CurrencyStrategyTask
from worker_plan_internal.plan.nodes.identify_risks import IdentifyRisksTask
from worker_plan_internal.plan.nodes.make_assumptions import MakeAssumptionsTask
from worker_plan_internal.plan.nodes.distill_assumptions import DistillAssumptionsTask
from worker_plan_internal.plan.nodes.review_assumptions import ReviewAssumptionsTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask

# Phase 6-7
from worker_plan_internal.plan.nodes.pre_project_assessment import PreProjectAssessmentTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.governance_phase1_audit import GovernancePhase1AuditTask
from worker_plan_internal.plan.nodes.governance_phase2_bodies import GovernancePhase2BodiesTask
from worker_plan_internal.plan.nodes.governance_phase3_impl_plan import GovernancePhase3ImplPlanTask
from worker_plan_internal.plan.nodes.governance_phase4_decision_escalation_matrix import GovernancePhase4DecisionEscalationMatrixTask
from worker_plan_internal.plan.nodes.governance_phase5_monitoring_progress import GovernancePhase5MonitoringProgressTask
from worker_plan_internal.plan.nodes.governance_phase6_extra import GovernancePhase6ExtraTask
from worker_plan_internal.plan.nodes.consolidate_governance import ConsolidateGovernanceTask

# Phase 8
from worker_plan_internal.plan.nodes.related_resources import RelatedResourcesTask
from worker_plan_internal.plan.nodes.find_team_members import FindTeamMembersTask
from worker_plan_internal.plan.nodes.enrich_team_contract_type import EnrichTeamMembersWithContractTypeTask
from worker_plan_internal.plan.nodes.enrich_team_background_story import EnrichTeamMembersWithBackgroundStoryTask
from worker_plan_internal.plan.nodes.enrich_team_environment_info import EnrichTeamMembersWithEnvironmentInfoTask
from worker_plan_internal.plan.nodes.review_team import ReviewTeamTask
from worker_plan_internal.plan.nodes.team_markdown import TeamMarkdownTask

# Phase 9-10
from worker_plan_internal.plan.nodes.swot_analysis import SWOTAnalysisTask
from worker_plan_internal.plan.nodes.expert_review import ExpertReviewTask
from worker_plan_internal.plan.nodes.data_collection import DataCollectionTask
from worker_plan_internal.plan.nodes.identify_documents import IdentifyDocumentsTask
from worker_plan_internal.plan.nodes.filter_documents_to_find import FilterDocumentsToFindTask
from worker_plan_internal.plan.nodes.filter_documents_to_create import FilterDocumentsToCreateTask
from worker_plan_internal.plan.nodes.draft_documents_to_find import DraftDocumentsToFindTask
from worker_plan_internal.plan.nodes.draft_documents_to_create import DraftDocumentsToCreateTask
from worker_plan_internal.plan.nodes.markdown_documents import MarkdownWithDocumentsToCreateAndFindTask

# Phase 11
from worker_plan_internal.plan.nodes.create_wbs_level1 import CreateWBSLevel1Task
from worker_plan_internal.plan.nodes.create_wbs_level2 import CreateWBSLevel2Task
from worker_plan_internal.plan.nodes.wbs_project_level1_and_level2 import WBSProjectLevel1AndLevel2Task
from worker_plan_internal.plan.nodes.create_pitch import CreatePitchTask
from worker_plan_internal.plan.nodes.convert_pitch_to_markdown import ConvertPitchToMarkdownTask
from worker_plan_internal.plan.nodes.identify_task_dependencies import IdentifyTaskDependenciesTask
from worker_plan_internal.plan.nodes.estimate_task_durations import EstimateTaskDurationsTask
from worker_plan_internal.plan.nodes.create_wbs_level3 import CreateWBSLevel3Task
from worker_plan_internal.plan.nodes.wbs_project_level1_level2_level3 import WBSProjectLevel1AndLevel2AndLevel3Task

# Phase 12-13
from worker_plan_internal.plan.nodes.create_schedule import CreateScheduleTask
from worker_plan_internal.plan.nodes.review_plan import ReviewPlanTask
from worker_plan_internal.plan.nodes.executive_summary import ExecutiveSummaryTask
from worker_plan_internal.plan.nodes.questions_and_answers import QuestionsAndAnswersTask
from worker_plan_internal.plan.nodes.premortem import PremortemTask
from worker_plan_internal.plan.nodes.self_audit import SelfAuditTask
from worker_plan_internal.plan.nodes.prompt_adherence import PromptAdherenceTask
from worker_plan_internal.plan.nodes.report import ReportTask


class FullPlanPipeline(PlanTask):
    def requires(self):
        return {
            'start_time': self.clone(StartTimeTask),
            'setup': self.clone(SetupTask),
            'screen_planning_prompt': self.clone(ScreenPlanningPromptTask),
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'redline_gate': self.clone(RedlineGateTask),
            'premise_attack': self.clone(PremiseAttackTask),
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'plan_type': self.clone(PlanTypeTask),
            'potential_levers': self.clone(PotentialLeversTask),
            'triage_levers': self.clone(TriageLeversTask),
            'enriched_levers': self.clone(EnrichLeversTask),
            'focus_on_vital_few_levers': self.clone(FocusOnVitalFewLeversTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'candidate_scenarios': self.clone(CandidateScenariosTask),
            'select_scenario': self.clone(SelectScenarioTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'potential_levers_constraint': self.clone(PotentialLeversConstraintTask),
            'triaged_levers_constraint': self.clone(TriagedLeversConstraintTask),
            'enriched_levers_constraint': self.clone(EnrichedLeversConstraintTask),
            'vital_few_levers_constraint': self.clone(VitalFewLeversConstraintTask),
            'candidate_scenarios_constraint': self.clone(CandidateScenariosConstraintTask),
            'selected_scenario_constraint': self.clone(SelectedScenarioConstraintTask),
            'physical_locations': self.clone(PhysicalLocationsTask),
            'currency_strategy': self.clone(CurrencyStrategyTask),
            'identify_risks': self.clone(IdentifyRisksTask),
            'make_assumptions': self.clone(MakeAssumptionsTask),
            'assumptions': self.clone(DistillAssumptionsTask),
            'review_assumptions': self.clone(ReviewAssumptionsTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'pre_project_assessment': self.clone(PreProjectAssessmentTask),
            'project_plan': self.clone(ProjectPlanTask),
            'governance_phase1_audit': self.clone(GovernancePhase1AuditTask),
            'governance_phase2_bodies': self.clone(GovernancePhase2BodiesTask),
            'governance_phase3_impl_plan': self.clone(GovernancePhase3ImplPlanTask),
            'governance_phase4_decision_escalation_matrix': self.clone(GovernancePhase4DecisionEscalationMatrixTask),
            'governance_phase5_monitoring_progress': self.clone(GovernancePhase5MonitoringProgressTask),
            'governance_phase6_extra': self.clone(GovernancePhase6ExtraTask),
            'consolidate_governance': self.clone(ConsolidateGovernanceTask),
            'related_resources': self.clone(RelatedResourcesTask),
            'find_team_members': self.clone(FindTeamMembersTask),
            'enrich_team_members_with_contract_type': self.clone(EnrichTeamMembersWithContractTypeTask),
            'enrich_team_members_with_background_story': self.clone(EnrichTeamMembersWithBackgroundStoryTask),
            'enrich_team_members_with_environment_info': self.clone(EnrichTeamMembersWithEnvironmentInfoTask),
            'review_team': self.clone(ReviewTeamTask),
            'team_markdown': self.clone(TeamMarkdownTask),
            'swot_analysis': self.clone(SWOTAnalysisTask),
            'expert_review': self.clone(ExpertReviewTask),
            'data_collection': self.clone(DataCollectionTask),
            'identified_documents': self.clone(IdentifyDocumentsTask),
            'filter_documents_to_find': self.clone(FilterDocumentsToFindTask),
            'filter_documents_to_create': self.clone(FilterDocumentsToCreateTask),
            'draft_documents_to_find': self.clone(DraftDocumentsToFindTask),
            'draft_documents_to_create': self.clone(DraftDocumentsToCreateTask),
            'documents_to_create_and_find': self.clone(MarkdownWithDocumentsToCreateAndFindTask),
            'wbs_level1': self.clone(CreateWBSLevel1Task),
            'wbs_level2': self.clone(CreateWBSLevel2Task),
            'wbs_project12': self.clone(WBSProjectLevel1AndLevel2Task),
            'pitch_raw': self.clone(CreatePitchTask),
            'pitch_markdown': self.clone(ConvertPitchToMarkdownTask),
            'dependencies': self.clone(IdentifyTaskDependenciesTask),
            'durations': self.clone(EstimateTaskDurationsTask),
            'wbs_level3': self.clone(CreateWBSLevel3Task),
            'wbs_project123': self.clone(WBSProjectLevel1AndLevel2AndLevel3Task),
            'plan_evaluator': self.clone(ReviewPlanTask),
            'executive_summary': self.clone(ExecutiveSummaryTask),
            'create_schedule': self.clone(CreateScheduleTask),
            'questions_and_answers': self.clone(QuestionsAndAnswersTask),
            'premortem': self.clone(PremortemTask),
            'self_audit': self.clone(SelfAuditTask),
            'prompt_adherence': self.clone(PromptAdherenceTask),
            'report': self.clone(ReportTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.PIPELINE_COMPLETE)

    def run_inner(self):
        with self.output().open("w") as f:
            f.write("Full pipeline executed successfully.\n")
