"""Pipeline stages: check constraint violations for early pipeline outputs.

Each task reads the extracted constraints and a specific stage's output,
then uses the ConstraintChecker to identify violations.
"""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.diagnostics.constraint_checker import ConstraintChecker
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.extract_constraints import ExtractConstraintsTask
from worker_plan_internal.plan.nodes.potential_levers import PotentialLeversTask
from worker_plan_internal.plan.nodes.deduplicate_levers import DeduplicateLeversTask
from worker_plan_internal.plan.nodes.enrich_levers import EnrichLeversTask
from worker_plan_internal.plan.nodes.focus_on_vital_few_levers import FocusOnVitalFewLeversTask
from worker_plan_internal.plan.nodes.candidate_scenarios import CandidateScenariosTask
from worker_plan_internal.plan.nodes.select_scenario import SelectScenarioTask


def _read_constraints_json(task: PlanTask) -> str:
    """Read just the constraints list from the extract_constraints stage output.

    The raw file contains system_prompt, user_prompt, metadata, and constraints.
    We only pass the constraints list to the checker.
    """
    with task.input()['extract_constraints']['raw'].open("r") as f:
        raw = json.load(f)
    constraints_only = {"constraints": raw.get("constraints", [])}
    return json.dumps(constraints_only, indent=2)


class PotentialLeversConstraintTask(PlanTask):
    """Guardrail: verify brainstormed levers respect the user's constraints."""
    def requires(self):
        return {
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'potential_levers': self.clone(PotentialLeversTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.POTENTIAL_LEVERS_CONSTRAINT)

    def run_with_llm(self, llm: LLM) -> None:
        constraints_json = _read_constraints_json(self)
        with self.input()['potential_levers']['clean'].open("r") as f:
            stage_output_json = f.read()
        result = ConstraintChecker.execute(llm, constraints_json, stage_output_json, "potential_levers")
        result.save_raw(self.output().path)


class DeduplicatedLeversConstraintTask(PlanTask):
    """Guardrail: verify triaged levers still respect the user's constraints."""
    def requires(self):
        return {
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'deduplicate_levers': self.clone(DeduplicateLeversTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.DEDUPLICATED_LEVERS_CONSTRAINT)

    def run_with_llm(self, llm: LLM) -> None:
        constraints_json = _read_constraints_json(self)
        with self.input()['deduplicate_levers']['raw'].open("r") as f:
            stage_output_json = f.read()
        result = ConstraintChecker.execute(llm, constraints_json, stage_output_json, "deduplicated_levers")
        result.save_raw(self.output().path)


class EnrichedLeversConstraintTask(PlanTask):
    """Guardrail: verify enriched levers still respect the user's constraints."""
    def requires(self):
        return {
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'enriched_levers': self.clone(EnrichLeversTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.ENRICHED_LEVERS_CONSTRAINT)

    def run_with_llm(self, llm: LLM) -> None:
        constraints_json = _read_constraints_json(self)
        with self.input()['enriched_levers']['raw'].open("r") as f:
            stage_output_json = f.read()
        result = ConstraintChecker.execute(llm, constraints_json, stage_output_json, "enriched_levers")
        result.save_raw(self.output().path)


class VitalFewLeversConstraintTask(PlanTask):
    """Guardrail: verify the selected vital levers respect the user's constraints."""
    def requires(self):
        return {
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'focus_on_vital_few_levers': self.clone(FocusOnVitalFewLeversTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.VITAL_FEW_LEVERS_CONSTRAINT)

    def run_with_llm(self, llm: LLM) -> None:
        constraints_json = _read_constraints_json(self)
        with self.input()['focus_on_vital_few_levers']['raw'].open("r") as f:
            stage_output_json = f.read()
        result = ConstraintChecker.execute(llm, constraints_json, stage_output_json, "vital_few_levers")
        result.save_raw(self.output().path)


class CandidateScenariosConstraintTask(PlanTask):
    """Guardrail: verify generated scenarios respect the user's constraints."""
    def requires(self):
        return {
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'candidate_scenarios': self.clone(CandidateScenariosTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.CANDIDATE_SCENARIOS_CONSTRAINT)

    def run_with_llm(self, llm: LLM) -> None:
        constraints_json = _read_constraints_json(self)
        with self.input()['candidate_scenarios']['clean'].open("r") as f:
            stage_output_json = f.read()
        result = ConstraintChecker.execute(llm, constraints_json, stage_output_json, "candidate_scenarios")
        result.save_raw(self.output().path)


class SelectedScenarioConstraintTask(PlanTask):
    """Guardrail: verify the chosen scenario respects the user's constraints before planning begins."""
    def requires(self):
        return {
            'extract_constraints': self.clone(ExtractConstraintsTask),
            'select_scenario': self.clone(SelectScenarioTask),
        }

    def output(self):
        return self.local_target(FilenameEnum.SELECTED_SCENARIO_CONSTRAINT)

    def run_with_llm(self, llm: LLM) -> None:
        constraints_json = _read_constraints_json(self)
        with self.input()['select_scenario']['clean'].open("r") as f:
            stage_output_json = f.read()
        result = ConstraintChecker.execute(llm, constraints_json, stage_output_json, "selected_scenario")
        result.save_raw(self.output().path)
