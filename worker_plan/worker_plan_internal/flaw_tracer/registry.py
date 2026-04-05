# worker_plan/worker_plan_internal/flaw_tracer/registry.py
"""Static DAG mapping for the PlanExe pipeline.

Maps every pipeline stage to its output files, upstream dependencies,
and source code files. Derived from the Luigi task classes in
worker_plan_internal/plan/stages/.
"""
from dataclasses import dataclass
from pathlib import Path

# Base path for source code, relative to worker_plan/
_SOURCE_BASE = Path(__file__).resolve().parent.parent.parent  # worker_plan/


@dataclass(frozen=True)
class StageInfo:
    """One pipeline stage."""
    name: str
    output_files: tuple[str, ...]
    primary_output: str  # preferred file to read when checking for flaws
    upstream_stages: tuple[str, ...] = ()
    source_code_files: tuple[str, ...] = ()


# ── Complete pipeline registry ──────────────────────────────────────────

STAGES: tuple[StageInfo, ...] = (
    # Phase 1: Initialization
    StageInfo(
        name="start_time",
        output_files=("001-1-start_time.json",),
        primary_output="001-1-start_time.json",
        upstream_stages=(),
        source_code_files=("worker_plan_internal/plan/stages/start_time.py",),
    ),
    StageInfo(
        name="setup",
        output_files=("001-2-plan.txt",),
        primary_output="001-2-plan.txt",
        upstream_stages=(),
        source_code_files=("worker_plan_internal/plan/stages/setup.py",),
    ),
    # Phase 2: Input Validation & Strategy
    StageInfo(
        name="screen_planning_prompt",
        output_files=("002-0-screen_planning_prompt.json", "002-0-screen_planning_prompt.md"),
        primary_output="002-0-screen_planning_prompt.md",
        upstream_stages=("setup",),
        source_code_files=(
            "worker_plan_internal/plan/stages/screen_planning_prompt.py",
            "worker_plan_internal/diagnostics/screen_planning_prompt.py",
        ),
    ),
    StageInfo(
        name="extract_constraints",
        output_files=("002-0-extract_constraints_raw.json", "002-0-extract_constraints.md"),
        primary_output="002-0-extract_constraints.md",
        upstream_stages=("setup",),
        source_code_files=(
            "worker_plan_internal/plan/stages/extract_constraints.py",
            "worker_plan_internal/diagnostics/extract_constraints.py",
        ),
    ),
    StageInfo(
        name="redline_gate",
        output_files=("002-1-redline_gate.json", "002-2-redline_gate.md"),
        primary_output="002-2-redline_gate.md",
        upstream_stages=("setup",),
        source_code_files=(
            "worker_plan_internal/plan/stages/redline_gate.py",
            "worker_plan_internal/diagnostics/redline_gate.py",
        ),
    ),
    StageInfo(
        name="premise_attack",
        output_files=("002-3-premise_attack.json", "002-4-premise_attack.md"),
        primary_output="002-4-premise_attack.md",
        upstream_stages=("setup",),
        source_code_files=(
            "worker_plan_internal/plan/stages/premise_attack.py",
            "worker_plan_internal/diagnostics/premise_attack.py",
        ),
    ),
    StageInfo(
        name="identify_purpose",
        output_files=("002-5-identify_purpose_raw.json", "002-6-identify_purpose.md"),
        primary_output="002-6-identify_purpose.md",
        upstream_stages=("setup",),
        source_code_files=(
            "worker_plan_internal/plan/stages/identify_purpose.py",
            "worker_plan_internal/assume/identify_purpose.py",
        ),
    ),
    StageInfo(
        name="plan_type",
        output_files=("002-7-plan_type_raw.json", "002-8-plan_type.md"),
        primary_output="002-8-plan_type.md",
        upstream_stages=("setup", "identify_purpose"),
        source_code_files=(
            "worker_plan_internal/plan/stages/plan_type.py",
            "worker_plan_internal/assume/identify_plan_type.py",
        ),
    ),
    StageInfo(
        name="potential_levers",
        output_files=("002-9-potential_levers_raw.json", "002-10-potential_levers.json"),
        primary_output="002-10-potential_levers.json",
        upstream_stages=("setup", "identify_purpose", "plan_type", "extract_constraints"),
        source_code_files=(
            "worker_plan_internal/plan/stages/potential_levers.py",
            "worker_plan_internal/lever/identify_potential_levers.py",
        ),
    ),
    StageInfo(
        name="deduplicate_levers",
        output_files=("002-11-deduplicated_levers_raw.json",),
        primary_output="002-11-deduplicated_levers_raw.json",
        upstream_stages=("setup", "identify_purpose", "plan_type", "potential_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/deduplicate_levers.py",
            "worker_plan_internal/lever/deduplicate_levers.py",
        ),
    ),
    StageInfo(
        name="enrich_levers",
        output_files=("002-12-enriched_levers_raw.json",),
        primary_output="002-12-enriched_levers_raw.json",
        upstream_stages=("setup", "identify_purpose", "plan_type", "deduplicate_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/enrich_levers.py",
            "worker_plan_internal/lever/enrich_potential_levers.py",
        ),
    ),
    StageInfo(
        name="focus_on_vital_few_levers",
        output_files=("002-13-vital_few_levers_raw.json",),
        primary_output="002-13-vital_few_levers_raw.json",
        upstream_stages=("setup", "identify_purpose", "plan_type", "enrich_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/focus_on_vital_few_levers.py",
            "worker_plan_internal/lever/focus_on_vital_few_levers.py",
        ),
    ),
    StageInfo(
        name="strategic_decisions_markdown",
        output_files=("002-14-strategic_decisions.md",),
        primary_output="002-14-strategic_decisions.md",
        upstream_stages=("enrich_levers", "focus_on_vital_few_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/strategic_decisions_markdown.py",
            "worker_plan_internal/lever/strategic_decisions_markdown.py",
        ),
    ),
    StageInfo(
        name="candidate_scenarios",
        output_files=("002-15-candidate_scenarios_raw.json", "002-16-candidate_scenarios.json"),
        primary_output="002-16-candidate_scenarios.json",
        upstream_stages=("setup", "identify_purpose", "plan_type", "focus_on_vital_few_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/candidate_scenarios.py",
            "worker_plan_internal/lever/candidate_scenarios.py",
        ),
    ),
    StageInfo(
        name="select_scenario",
        output_files=("002-17-selected_scenario_raw.json", "002-18-selected_scenario.json"),
        primary_output="002-18-selected_scenario.json",
        upstream_stages=("setup", "identify_purpose", "plan_type", "focus_on_vital_few_levers", "candidate_scenarios"),
        source_code_files=(
            "worker_plan_internal/plan/stages/select_scenario.py",
            "worker_plan_internal/lever/select_scenario.py",
        ),
    ),
    StageInfo(
        name="scenarios_markdown",
        output_files=("002-19-scenarios.md",),
        primary_output="002-19-scenarios.md",
        upstream_stages=("candidate_scenarios", "select_scenario"),
        source_code_files=(
            "worker_plan_internal/plan/stages/scenarios_markdown.py",
            "worker_plan_internal/lever/scenarios_markdown.py",
        ),
    ),
    # Constraint checkers
    StageInfo(
        name="potential_levers_constraint",
        output_files=("002-10-potential_levers_constraint.json",),
        primary_output="002-10-potential_levers_constraint.json",
        upstream_stages=("extract_constraints", "potential_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/constraint_checker_stages.py",
            "worker_plan_internal/diagnostics/constraint_checker.py",
        ),
    ),
    StageInfo(
        name="deduplicated_levers_constraint",
        output_files=("002-11-deduplicated_levers_constraint.json",),
        primary_output="002-11-deduplicated_levers_constraint.json",
        upstream_stages=("extract_constraints", "deduplicate_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/constraint_checker_stages.py",
            "worker_plan_internal/diagnostics/constraint_checker.py",
        ),
    ),
    StageInfo(
        name="enriched_levers_constraint",
        output_files=("002-12-enriched_levers_constraint.json",),
        primary_output="002-12-enriched_levers_constraint.json",
        upstream_stages=("extract_constraints", "enrich_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/constraint_checker_stages.py",
            "worker_plan_internal/diagnostics/constraint_checker.py",
        ),
    ),
    StageInfo(
        name="vital_few_levers_constraint",
        output_files=("002-13-vital_few_levers_constraint.json",),
        primary_output="002-13-vital_few_levers_constraint.json",
        upstream_stages=("extract_constraints", "focus_on_vital_few_levers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/constraint_checker_stages.py",
            "worker_plan_internal/diagnostics/constraint_checker.py",
        ),
    ),
    StageInfo(
        name="candidate_scenarios_constraint",
        output_files=("002-16-candidate_scenarios_constraint.json",),
        primary_output="002-16-candidate_scenarios_constraint.json",
        upstream_stages=("extract_constraints", "candidate_scenarios"),
        source_code_files=(
            "worker_plan_internal/plan/stages/constraint_checker_stages.py",
            "worker_plan_internal/diagnostics/constraint_checker.py",
        ),
    ),
    StageInfo(
        name="selected_scenario_constraint",
        output_files=("002-18-selected_scenario_constraint.json",),
        primary_output="002-18-selected_scenario_constraint.json",
        upstream_stages=("extract_constraints", "select_scenario"),
        source_code_files=(
            "worker_plan_internal/plan/stages/constraint_checker_stages.py",
            "worker_plan_internal/diagnostics/constraint_checker.py",
        ),
    ),
    # Phase 3: Context & Assumptions
    StageInfo(
        name="physical_locations",
        output_files=("002-20-physical_locations_raw.json", "002-21-physical_locations.md"),
        primary_output="002-21-physical_locations.md",
        upstream_stages=("setup", "identify_purpose", "plan_type", "strategic_decisions_markdown", "scenarios_markdown"),
        source_code_files=(
            "worker_plan_internal/plan/stages/physical_locations.py",
            "worker_plan_internal/assume/physical_locations.py",
        ),
    ),
    StageInfo(
        name="currency_strategy",
        output_files=("002-22-currency_strategy_raw.json", "002-23-currency_strategy.md"),
        primary_output="002-23-currency_strategy.md",
        upstream_stages=("setup", "identify_purpose", "plan_type", "physical_locations", "strategic_decisions_markdown", "scenarios_markdown"),
        source_code_files=(
            "worker_plan_internal/plan/stages/currency_strategy.py",
            "worker_plan_internal/assume/currency_strategy.py",
        ),
    ),
    StageInfo(
        name="identify_risks",
        output_files=("003-1-identify_risks_raw.json", "003-2-identify_risks.md"),
        primary_output="003-2-identify_risks.md",
        upstream_stages=("setup", "identify_purpose", "plan_type", "strategic_decisions_markdown", "scenarios_markdown", "physical_locations", "currency_strategy"),
        source_code_files=(
            "worker_plan_internal/plan/stages/identify_risks.py",
            "worker_plan_internal/assume/identify_risks.py",
        ),
    ),
    StageInfo(
        name="make_assumptions",
        output_files=("003-3-make_assumptions_raw.json", "003-4-make_assumptions.json", "003-5-make_assumptions.md"),
        primary_output="003-5-make_assumptions.md",
        upstream_stages=("setup", "identify_purpose", "plan_type", "strategic_decisions_markdown", "scenarios_markdown", "physical_locations", "currency_strategy", "identify_risks"),
        source_code_files=(
            "worker_plan_internal/plan/stages/make_assumptions.py",
            "worker_plan_internal/assume/make_assumptions.py",
        ),
    ),
    StageInfo(
        name="distill_assumptions",
        output_files=("003-6-distill_assumptions_raw.json", "003-7-distill_assumptions.md"),
        primary_output="003-7-distill_assumptions.md",
        upstream_stages=("setup", "identify_purpose", "strategic_decisions_markdown", "scenarios_markdown", "make_assumptions"),
        source_code_files=(
            "worker_plan_internal/plan/stages/distill_assumptions.py",
            "worker_plan_internal/assume/distill_assumptions.py",
        ),
    ),
    StageInfo(
        name="review_assumptions",
        output_files=("003-8-review_assumptions_raw.json", "003-9-review_assumptions.md"),
        primary_output="003-9-review_assumptions.md",
        upstream_stages=("identify_purpose", "plan_type", "strategic_decisions_markdown", "scenarios_markdown", "physical_locations", "currency_strategy", "identify_risks", "make_assumptions", "distill_assumptions"),
        source_code_files=(
            "worker_plan_internal/plan/stages/review_assumptions.py",
            "worker_plan_internal/assume/review_assumptions.py",
        ),
    ),
    StageInfo(
        name="consolidate_assumptions_markdown",
        output_files=("003-10-consolidate_assumptions_full.md", "003-11-consolidate_assumptions_short.md"),
        primary_output="003-10-consolidate_assumptions_full.md",
        upstream_stages=("identify_purpose", "plan_type", "physical_locations", "currency_strategy", "identify_risks", "make_assumptions", "distill_assumptions", "review_assumptions"),
        source_code_files=(
            "worker_plan_internal/plan/stages/consolidate_assumptions_markdown.py",
            "worker_plan_internal/assume/shorten_markdown.py",
        ),
    ),
    # Phase 4: Pre-Project Assessment & Project Plan
    StageInfo(
        name="pre_project_assessment",
        output_files=("004-1-pre_project_assessment_raw.json", "004-2-pre_project_assessment.json"),
        primary_output="004-2-pre_project_assessment.json",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown"),
        source_code_files=(
            "worker_plan_internal/plan/stages/pre_project_assessment.py",
            "worker_plan_internal/expert/pre_project_assessment.py",
        ),
    ),
    StageInfo(
        name="project_plan",
        output_files=("005-1-project_plan_raw.json", "005-2-project_plan.md"),
        primary_output="005-2-project_plan.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "pre_project_assessment"),
        source_code_files=(
            "worker_plan_internal/plan/stages/project_plan.py",
            "worker_plan_internal/plan/project_plan.py",
        ),
    ),
    # Phase 5: Governance
    StageInfo(
        name="governance_phase1_audit",
        output_files=("006-1-governance_phase1_audit_raw.json", "006-2-governance_phase1_audit.md"),
        primary_output="006-2-governance_phase1_audit.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan"),
        source_code_files=(
            "worker_plan_internal/plan/stages/governance_phase1_audit.py",
            "worker_plan_internal/governance/governance_phase1_audit.py",
        ),
    ),
    StageInfo(
        name="governance_phase2_bodies",
        output_files=("006-3-governance_phase2_bodies_raw.json", "006-4-governance_phase2_bodies.md"),
        primary_output="006-4-governance_phase2_bodies.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "governance_phase1_audit"),
        source_code_files=(
            "worker_plan_internal/plan/stages/governance_phase2_bodies.py",
            "worker_plan_internal/governance/governance_phase2_bodies.py",
        ),
    ),
    StageInfo(
        name="governance_phase3_impl_plan",
        output_files=("006-5-governance_phase3_impl_plan_raw.json", "006-6-governance_phase3_impl_plan.md"),
        primary_output="006-6-governance_phase3_impl_plan.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "governance_phase2_bodies"),
        source_code_files=(
            "worker_plan_internal/plan/stages/governance_phase3_impl_plan.py",
            "worker_plan_internal/governance/governance_phase3_impl_plan.py",
        ),
    ),
    StageInfo(
        name="governance_phase4_decision_escalation_matrix",
        output_files=("006-7-governance_phase4_decision_escalation_matrix_raw.json", "006-8-governance_phase4_decision_escalation_matrix.md"),
        primary_output="006-8-governance_phase4_decision_escalation_matrix.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "governance_phase2_bodies", "governance_phase3_impl_plan"),
        source_code_files=(
            "worker_plan_internal/plan/stages/governance_phase4_decision_escalation_matrix.py",
            "worker_plan_internal/governance/governance_phase4_decision_escalation_matrix.py",
        ),
    ),
    StageInfo(
        name="governance_phase5_monitoring_progress",
        output_files=("006-9-governance_phase5_monitoring_progress_raw.json", "006-10-governance_phase5_monitoring_progress.md"),
        primary_output="006-10-governance_phase5_monitoring_progress.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "governance_phase2_bodies", "governance_phase3_impl_plan", "governance_phase4_decision_escalation_matrix"),
        source_code_files=(
            "worker_plan_internal/plan/stages/governance_phase5_monitoring_progress.py",
            "worker_plan_internal/governance/governance_phase5_monitoring_progress.py",
        ),
    ),
    StageInfo(
        name="governance_phase6_extra",
        output_files=("006-11-governance_phase6_extra_raw.json", "006-12-governance_phase6_extra.md"),
        primary_output="006-12-governance_phase6_extra.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "governance_phase1_audit", "governance_phase2_bodies", "governance_phase3_impl_plan", "governance_phase4_decision_escalation_matrix", "governance_phase5_monitoring_progress"),
        source_code_files=(
            "worker_plan_internal/plan/stages/governance_phase6_extra.py",
            "worker_plan_internal/governance/governance_phase6_extra.py",
        ),
    ),
    StageInfo(
        name="consolidate_governance",
        output_files=("006-13-consolidate_governance.md",),
        primary_output="006-13-consolidate_governance.md",
        upstream_stages=("governance_phase1_audit", "governance_phase2_bodies", "governance_phase3_impl_plan", "governance_phase4_decision_escalation_matrix", "governance_phase5_monitoring_progress", "governance_phase6_extra"),
        source_code_files=("worker_plan_internal/plan/stages/consolidate_governance.py",),
    ),
    # Phase 6: Resources & Team
    StageInfo(
        name="related_resources",
        output_files=("007-1-related_resources_raw.json", "007-8-related_resources.md"),
        primary_output="007-8-related_resources.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan"),
        source_code_files=(
            "worker_plan_internal/plan/stages/related_resources.py",
            "worker_plan_internal/plan/related_resources.py",
        ),
    ),
    StageInfo(
        name="find_team_members",
        output_files=("008-1-find_team_members_raw.json", "008-2-find_team_members.json"),
        primary_output="008-2-find_team_members.json",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "pre_project_assessment", "project_plan", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/find_team_members.py",
            "worker_plan_internal/team/find_team_members.py",
        ),
    ),
    StageInfo(
        name="enrich_team_contract_type",
        output_files=("009-1-enrich_team_members_contract_type_raw.json", "009-2-enrich_team_members_contract_type.json"),
        primary_output="009-2-enrich_team_members_contract_type.json",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "pre_project_assessment", "project_plan", "find_team_members", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/enrich_team_contract_type.py",
            "worker_plan_internal/team/enrich_team_members_with_contract_type.py",
        ),
    ),
    StageInfo(
        name="enrich_team_background_story",
        output_files=("010-1-enrich_team_members_background_story_raw.json", "010-2-enrich_team_members_background_story.json"),
        primary_output="010-2-enrich_team_members_background_story.json",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "pre_project_assessment", "project_plan", "enrich_team_contract_type", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/enrich_team_background_story.py",
            "worker_plan_internal/team/enrich_team_members_with_background_story.py",
        ),
    ),
    StageInfo(
        name="enrich_team_environment_info",
        output_files=("011-1-enrich_team_members_environment_info_raw.json", "011-2-enrich_team_members_environment_info.json"),
        primary_output="011-2-enrich_team_members_environment_info.json",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "pre_project_assessment", "project_plan", "enrich_team_background_story", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/enrich_team_environment_info.py",
            "worker_plan_internal/team/enrich_team_members_with_environment_info.py",
        ),
    ),
    StageInfo(
        name="review_team",
        output_files=("012-review_team_raw.json",),
        primary_output="012-review_team_raw.json",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "pre_project_assessment", "project_plan", "enrich_team_environment_info", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/review_team.py",
            "worker_plan_internal/team/review_team.py",
        ),
    ),
    StageInfo(
        name="team_markdown",
        output_files=("013-team.md",),
        primary_output="013-team.md",
        upstream_stages=("enrich_team_environment_info", "review_team"),
        source_code_files=(
            "worker_plan_internal/plan/stages/team_markdown.py",
            "worker_plan_internal/team/team_markdown_document.py",
        ),
    ),
    # Phase 7: Analysis & Experts
    StageInfo(
        name="swot_analysis",
        output_files=("014-1-swot_analysis_raw.json", "014-2-swot_analysis.md"),
        primary_output="014-2-swot_analysis.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "identify_purpose", "consolidate_assumptions_markdown", "pre_project_assessment", "project_plan", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/swot_analysis.py",
            "worker_plan_internal/swot/swot_analysis.py",
        ),
    ),
    StageInfo(
        name="expert_review",
        output_files=("015-1-experts_raw.json", "015-2-experts.json", "016-2-expert_criticism.md"),
        primary_output="016-2-expert_criticism.md",
        upstream_stages=("setup", "strategic_decisions_markdown", "scenarios_markdown", "pre_project_assessment", "project_plan", "swot_analysis"),
        source_code_files=(
            "worker_plan_internal/plan/stages/expert_review.py",
            "worker_plan_internal/expert/expert_finder.py",
            "worker_plan_internal/expert/expert_criticism.py",
        ),
    ),
    # Phase 8: Data & Documents
    StageInfo(
        name="data_collection",
        output_files=("017-1-data_collection_raw.json", "017-2-data_collection.md"),
        primary_output="017-2-data_collection.md",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "related_resources", "swot_analysis", "team_markdown", "expert_review"),
        source_code_files=(
            "worker_plan_internal/plan/stages/data_collection.py",
            "worker_plan_internal/plan/data_collection.py",
        ),
    ),
    StageInfo(
        name="identify_documents",
        output_files=("017-3-identified_documents_raw.json", "017-4-identified_documents.md", "017-5-identified_documents_to_find.json", "017-6-identified_documents_to_create.json"),
        primary_output="017-4-identified_documents.md",
        upstream_stages=("identify_purpose", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "related_resources", "swot_analysis", "team_markdown", "expert_review"),
        source_code_files=(
            "worker_plan_internal/plan/stages/identify_documents.py",
            "worker_plan_internal/document/identify_documents.py",
        ),
    ),
    StageInfo(
        name="filter_documents_to_find",
        output_files=("017-7-filter_documents_to_find_raw.json", "017-8-filter_documents_to_find_clean.json"),
        primary_output="017-8-filter_documents_to_find_clean.json",
        upstream_stages=("identify_purpose", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "identify_documents"),
        source_code_files=(
            "worker_plan_internal/plan/stages/filter_documents_to_find.py",
            "worker_plan_internal/document/filter_documents_to_find.py",
        ),
    ),
    StageInfo(
        name="filter_documents_to_create",
        output_files=("017-9-filter_documents_to_create_raw.json", "017-10-filter_documents_to_create_clean.json"),
        primary_output="017-10-filter_documents_to_create_clean.json",
        upstream_stages=("identify_purpose", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "identify_documents"),
        source_code_files=(
            "worker_plan_internal/plan/stages/filter_documents_to_create.py",
            "worker_plan_internal/document/filter_documents_to_create.py",
        ),
    ),
    StageInfo(
        name="draft_documents_to_find",
        output_files=("017-12-draft_documents_to_find.json",),
        primary_output="017-12-draft_documents_to_find.json",
        upstream_stages=("identify_purpose", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "filter_documents_to_find"),
        source_code_files=(
            "worker_plan_internal/plan/stages/draft_documents_to_find.py",
            "worker_plan_internal/document/draft_document_to_find.py",
        ),
    ),
    StageInfo(
        name="draft_documents_to_create",
        output_files=("017-14-draft_documents_to_create.json",),
        primary_output="017-14-draft_documents_to_create.json",
        upstream_stages=("identify_purpose", "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "filter_documents_to_create"),
        source_code_files=(
            "worker_plan_internal/plan/stages/draft_documents_to_create.py",
            "worker_plan_internal/document/draft_document_to_create.py",
        ),
    ),
    StageInfo(
        name="markdown_documents",
        output_files=("017-15-documents_to_create_and_find.md",),
        primary_output="017-15-documents_to_create_and_find.md",
        upstream_stages=("draft_documents_to_create", "draft_documents_to_find"),
        source_code_files=(
            "worker_plan_internal/plan/stages/markdown_documents.py",
            "worker_plan_internal/document/markdown_with_document.py",
        ),
    ),
    # Phase 9: WBS
    StageInfo(
        name="create_wbs_level1",
        output_files=("018-1-wbs_level1_raw.json", "018-2-wbs_level1.json", "018-3-wbs_level1_project_title.json"),
        primary_output="018-2-wbs_level1.json",
        upstream_stages=("project_plan",),
        source_code_files=(
            "worker_plan_internal/plan/stages/create_wbs_level1.py",
            "worker_plan_internal/plan/create_wbs_level1.py",
        ),
    ),
    StageInfo(
        name="create_wbs_level2",
        output_files=("018-4-wbs_level2_raw.json", "018-5-wbs_level2.json"),
        primary_output="018-5-wbs_level2.json",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "project_plan", "create_wbs_level1", "data_collection"),
        source_code_files=(
            "worker_plan_internal/plan/stages/create_wbs_level2.py",
            "worker_plan_internal/plan/create_wbs_level2.py",
        ),
    ),
    StageInfo(
        name="wbs_project_level1_and_level2",
        output_files=("019-wbs_project_level1_and_level2.json",),
        primary_output="019-wbs_project_level1_and_level2.json",
        upstream_stages=("create_wbs_level1", "create_wbs_level2"),
        source_code_files=(
            "worker_plan_internal/plan/stages/wbs_project_level1_and_level2.py",
            "worker_plan_internal/wbs/wbs_populate.py",
        ),
    ),
    # Phase 10: Pitch & Dependencies
    StageInfo(
        name="create_pitch",
        output_files=("020-1-pitch_raw.json",),
        primary_output="020-1-pitch_raw.json",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "project_plan", "wbs_project_level1_and_level2", "related_resources"),
        source_code_files=(
            "worker_plan_internal/plan/stages/create_pitch.py",
            "worker_plan_internal/pitch/create_pitch.py",
        ),
    ),
    StageInfo(
        name="convert_pitch_to_markdown",
        output_files=("020-2-pitch_to_markdown_raw.json", "020-3-pitch.md"),
        primary_output="020-3-pitch.md",
        upstream_stages=("create_pitch",),
        source_code_files=(
            "worker_plan_internal/plan/stages/convert_pitch_to_markdown.py",
            "worker_plan_internal/pitch/convert_pitch_to_markdown.py",
        ),
    ),
    StageInfo(
        name="identify_task_dependencies",
        output_files=("021-task_dependencies_raw.json",),
        primary_output="021-task_dependencies_raw.json",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "project_plan", "create_wbs_level2", "data_collection"),
        source_code_files=(
            "worker_plan_internal/plan/stages/identify_task_dependencies.py",
            "worker_plan_internal/plan/identify_wbs_task_dependencies.py",
        ),
    ),
    StageInfo(
        name="estimate_task_durations",
        output_files=("022-2-task_durations.json",),
        primary_output="022-2-task_durations.json",
        upstream_stages=("project_plan", "wbs_project_level1_and_level2"),
        source_code_files=(
            "worker_plan_internal/plan/stages/estimate_task_durations.py",
            "worker_plan_internal/plan/estimate_wbs_task_durations.py",
        ),
    ),
    # Phase 11: WBS Level 3
    StageInfo(
        name="create_wbs_level3",
        output_files=("023-2-wbs_level3.json",),
        primary_output="023-2-wbs_level3.json",
        upstream_stages=("project_plan", "wbs_project_level1_and_level2", "estimate_task_durations", "data_collection"),
        source_code_files=(
            "worker_plan_internal/plan/stages/create_wbs_level3.py",
            "worker_plan_internal/plan/create_wbs_level3.py",
        ),
    ),
    StageInfo(
        name="wbs_project_level1_level2_level3",
        output_files=("023-3-wbs_project_level1_and_level2_and_level3.json", "023-4-wbs_project_level1_and_level2_and_level3.csv"),
        primary_output="023-3-wbs_project_level1_and_level2_and_level3.json",
        upstream_stages=("wbs_project_level1_and_level2", "create_wbs_level3"),
        source_code_files=(
            "worker_plan_internal/plan/stages/wbs_project_level1_level2_level3.py",
            "worker_plan_internal/wbs/wbs_populate.py",
        ),
    ),
    # Phase 12: Schedule & Reviews
    StageInfo(
        name="create_schedule",
        output_files=("026-2-schedule_gantt_dhtmlx.html", "026-3-schedule_gantt_machai.csv"),
        primary_output="026-2-schedule_gantt_dhtmlx.html",
        upstream_stages=("start_time", "create_wbs_level1", "identify_task_dependencies", "estimate_task_durations", "wbs_project_level1_level2_level3"),
        source_code_files=(
            "worker_plan_internal/plan/stages/create_schedule.py",
            "worker_plan_internal/schedule/project_schedule_populator.py",
        ),
    ),
    StageInfo(
        name="review_plan",
        output_files=("024-1-review_plan_raw.json", "024-2-review_plan.md"),
        primary_output="024-2-review_plan.md",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "data_collection", "related_resources", "swot_analysis", "team_markdown", "convert_pitch_to_markdown", "expert_review", "wbs_project_level1_level2_level3"),
        source_code_files=(
            "worker_plan_internal/plan/stages/review_plan.py",
            "worker_plan_internal/plan/review_plan.py",
        ),
    ),
    StageInfo(
        name="executive_summary",
        output_files=("025-1-executive_summary_raw.json", "025-2-executive_summary.md"),
        primary_output="025-2-executive_summary.md",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "project_plan", "data_collection", "related_resources", "swot_analysis", "team_markdown", "convert_pitch_to_markdown", "expert_review", "wbs_project_level1_level2_level3", "review_plan"),
        source_code_files=(
            "worker_plan_internal/plan/stages/executive_summary.py",
            "worker_plan_internal/plan/executive_summary.py",
        ),
    ),
    StageInfo(
        name="questions_and_answers",
        output_files=("027-1-questions_and_answers_raw.json", "027-2-questions_and_answers.md", "027-3-questions_and_answers.html"),
        primary_output="027-2-questions_and_answers.md",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "team_markdown", "related_resources", "consolidate_governance", "swot_analysis", "convert_pitch_to_markdown", "data_collection", "markdown_documents", "wbs_project_level1_level2_level3", "expert_review", "project_plan", "review_plan"),
        source_code_files=(
            "worker_plan_internal/plan/stages/questions_and_answers.py",
            "worker_plan_internal/questions_answers/questions_answers.py",
        ),
    ),
    StageInfo(
        name="premortem",
        output_files=("028-1-premortem_raw.json", "028-2-premortem.md"),
        primary_output="028-2-premortem.md",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "team_markdown", "related_resources", "consolidate_governance", "swot_analysis", "convert_pitch_to_markdown", "data_collection", "markdown_documents", "wbs_project_level1_level2_level3", "expert_review", "project_plan", "review_plan", "questions_and_answers"),
        source_code_files=(
            "worker_plan_internal/plan/stages/premortem.py",
            "worker_plan_internal/diagnostics/premortem.py",
        ),
    ),
    StageInfo(
        name="self_audit",
        output_files=("029-1-self_audit_raw.json", "029-2-self_audit.md"),
        primary_output="029-2-self_audit.md",
        upstream_stages=("strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown", "team_markdown", "related_resources", "consolidate_governance", "swot_analysis", "convert_pitch_to_markdown", "data_collection", "markdown_documents", "wbs_project_level1_level2_level3", "expert_review", "project_plan", "review_plan", "questions_and_answers", "premortem"),
        source_code_files=(
            "worker_plan_internal/plan/stages/self_audit.py",
            "worker_plan_internal/self_audit/self_audit.py",
        ),
    ),
    # Phase 13: Final Report
    StageInfo(
        name="report",
        output_files=("030-report.html",),
        primary_output="030-report.html",
        upstream_stages=(
            "setup", "screen_planning_prompt", "redline_gate", "premise_attack",
            "strategic_decisions_markdown", "scenarios_markdown", "consolidate_assumptions_markdown",
            "team_markdown", "related_resources", "consolidate_governance", "swot_analysis",
            "convert_pitch_to_markdown", "data_collection", "markdown_documents",
            "create_wbs_level1", "wbs_project_level1_level2_level3", "expert_review",
            "project_plan", "review_plan", "executive_summary", "create_schedule",
            "questions_and_answers", "premortem", "self_audit",
        ),
        source_code_files=(
            "worker_plan_internal/plan/stages/report.py",
            "worker_plan_internal/report/report_generator.py",
        ),
    ),
)

# ── Lookup indexes (built once at import time) ──────────────────────────

_STAGE_BY_NAME: dict[str, StageInfo] = {s.name: s for s in STAGES}
_STAGE_BY_FILENAME: dict[str, StageInfo] = {}
for _stage in STAGES:
    for _fname in _stage.output_files:
        _STAGE_BY_FILENAME[_fname] = _stage


def find_stage_by_filename(filename: str) -> StageInfo | None:
    """Given an output filename, return the stage that produced it."""
    return _STAGE_BY_FILENAME.get(filename)


def get_upstream_files(stage_name: str, output_dir: Path) -> list[tuple[str, Path]]:
    """Return (stage_name, file_path) pairs for upstream stages whose primary output exists on disk."""
    stage = _STAGE_BY_NAME.get(stage_name)
    if stage is None:
        return []

    result = []
    for upstream_name in stage.upstream_stages:
        upstream_stage = _STAGE_BY_NAME.get(upstream_name)
        if upstream_stage is None:
            continue
        primary_path = output_dir / upstream_stage.primary_output
        if primary_path.exists():
            result.append((upstream_name, primary_path))
    return result


def get_source_code_paths(stage_name: str) -> list[Path]:
    """Return absolute paths to source code files for a stage."""
    stage = _STAGE_BY_NAME.get(stage_name)
    if stage is None:
        return []
    return [_SOURCE_BASE / f for f in stage.source_code_files]
