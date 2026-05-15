"""Run CompressReportSection for each PlanExe section using the same input
the corresponding Luigi node ingests, plus that node's own output appended.

- compress_selected_scenario:   SelectScenarioTask inputs + selected_scenario.json
- compress_review_plan:         ReviewPlanTask inputs + review_plan.md
- compress_premortem:           PremortemTask inputs + premortem.md
- compress_expert_criticism:    ExpertReviewTask inputs + expert_criticism.md

For "what plan are we actually modelling?" the selected_scenario is the right
source. The full Strategic Decisions section also contains rejected
alternatives whose numbers should NOT be extracted as parameters, so that
section is not compressed here.

The file-name headers mirror the ``File '<name>':\\n<content>`` format each
Luigi task uses when it builds its LLM query, so the compressor sees the same
surface the original LLM saw. ``pre_project_assessment.json`` is serialised
with ``format_json_for_use_in_query`` to match expert_review.py.

The total concatenated input runs ~50K-60K tokens for premortem/review_plan,
which does not fit in a 16K-context model. The default model below has a
much larger context. Override via the ``COMPRESS_FULL_LLM`` env var if you
want to test a different LLM.

The PlanExe-web sample directory and output directory are also overridable
via ``COMPRESS_FULL_SAMPLE_DIR`` and ``COMPRESS_FULL_OUTPUT_DIR``.

PROMPT> python -m worker_plan_internal.parameter_extraction.run_compress_full
"""
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from worker_plan_api.planexe_dotenv import PlanExeDotEnv
from worker_plan_internal.format_json_for_use_in_query import format_json_for_use_in_query
from worker_plan_internal.llm_factory import get_llm
from worker_plan_internal.parameter_extraction.compress_report_section import (
    CompressReportSection,
    ReportSectionTypeEnum,
)

logger = logging.getLogger(__name__)


_DEFAULT_LLM = "openrouter-gemini-2.5-flash-lite-preview-09-2025"
_DEFAULT_SAMPLE_DIR = "/Users/neoneye/git/PlanExe-web/20260215_nuuk_clay_workshop"
_DEFAULT_OUTPUT_DIR = "/Users/neoneye/git/PlanExeGroup/PlanExe/output/v8"


@dataclass
class CompressJob:
    """One compress target: which section it represents, which files to
    concatenate as the input, and how to label them in the prompt.
    """

    name: str
    section_type: ReportSectionTypeEnum
    title: str
    # Each entry is (header_seen_by_llm, sample_dir_filename, is_json,
    # optional_json_subfield). When the optional subfield is set, the file
    # is loaded as JSON and only that top-level key's value is serialised
    # (mirrors Luigi tasks that read a single subfield like 'levers' or
    # 'scenarios' before passing to format_json_for_use_in_query).
    files: list[tuple[str, str, bool, str | None]]


# SelectScenarioTask query order — see plan/nodes/select_scenario.py.
# levers_vital_few and candidate_scenarios are wrapped in
# format_json_for_use_in_query to match the Luigi serialisation. The
# selected_scenario.json output is appended so the compressor sees both the
# inputs the selector saw AND the commitment it made.
_SELECTED_SCENARIO_JOB = CompressJob(
    name="selected_scenario",
    section_type=ReportSectionTypeEnum.SELECTED_SCENARIO,
    title="Selected Scenario",
    files=[
        ("plan.txt", "plan.txt", False, None),
        ("purpose.md", "identify_purpose.md", False, None),
        ("plan_type.md", "plan_type.md", False, None),
        ("levers_vital_few.json", "vital_few_levers_raw.json", True, "levers"),
        ("candidate_scenarios.json", "candidate_scenarios.json", True, "scenarios"),
        ("selected_scenario.json", "selected_scenario.json", True, None),
    ],
)

# ReviewPlanTask query order — see plan/nodes/review_plan.py.
_REVIEW_PLAN_JOB = CompressJob(
    name="review_plan",
    section_type=ReportSectionTypeEnum.REVIEW_PLAN,
    title="Review Plan",
    files=[
        ("strategic_decisions.md", "strategic_decisions.md", False, None),
        ("scenarios.md", "scenarios.md", False, None),
        ("assumptions.md", "consolidate_assumptions_short.md", False, None),
        ("project-plan.md", "project_plan.md", False, None),
        ("data-collection.md", "data_collection.md", False, None),
        ("related-resources.md", "related_resources.md", False, None),
        ("swot-analysis.md", "swot_analysis.md", False, None),
        ("team.md", "team.md", False, None),
        ("pitch.md", "pitch.md", False, None),
        ("expert-review.md", "expert_criticism.md", False, None),
        ("work-breakdown-structure.csv", "wbs_project_level1_and_level2_and_level3.csv", False, None),
        ("review_plan.md", "review_plan.md", False, None),
    ],
)

# PremortemTask query order — see plan/nodes/premortem.py.
_PREMORTEM_JOB = CompressJob(
    name="premortem",
    section_type=ReportSectionTypeEnum.PREMORTEM,
    title="Premortem",
    files=[
        ("strategic_decisions.md", "strategic_decisions.md", False, None),
        ("scenarios.md", "scenarios.md", False, None),
        ("assumptions.md", "consolidate_assumptions_short.md", False, None),
        ("project-plan.md", "project_plan.md", False, None),
        ("data-collection.md", "data_collection.md", False, None),
        ("related-resources.md", "related_resources.md", False, None),
        ("swot-analysis.md", "swot_analysis.md", False, None),
        ("team.md", "team.md", False, None),
        ("pitch.md", "pitch.md", False, None),
        ("expert-review.md", "expert_criticism.md", False, None),
        ("work-breakdown-structure.csv", "wbs_project_level1_and_level2_and_level3.csv", False, None),
        ("review-plan.md", "review_plan.md", False, None),
        ("questions-and-answers.md", "questions_and_answers.md", False, None),
        ("premortem.md", "premortem.md", False, None),
    ],
)

# ExpertReviewTask query order — see plan/nodes/expert_review.py.
# pre_project_assessment.json is fed through format_json_for_use_in_query so
# the serialisation matches the Luigi task exactly.
_EXPERT_CRITICISM_JOB = CompressJob(
    name="expert_criticism",
    section_type=ReportSectionTypeEnum.EXPERT_CRITICISM,
    title="Expert Criticism",
    files=[
        ("initial-plan.txt", "plan.txt", False, None),
        ("strategic_decisions.md", "strategic_decisions.md", False, None),
        ("scenarios.md", "scenarios.md", False, None),
        ("pre-project assessment.json", "pre_project_assessment.json", True, None),
        ("project_plan.md", "project_plan.md", False, None),
        ("SWOT Analysis.md", "swot_analysis.md", False, None),
        ("expert_criticism.md", "expert_criticism.md", False, None),
    ],
)

JOBS: tuple[CompressJob, ...] = (
    _SELECTED_SCENARIO_JOB,
    _REVIEW_PLAN_JOB,
    _PREMORTEM_JOB,
    _EXPERT_CRITICISM_JOB,
)


def build_blob(job: CompressJob, sample_dir: Path) -> str:
    """Concatenate the job's input files using the same header format the
    matching Luigi task uses when it builds its LLM query.
    """
    parts: list[str] = []
    total_bytes = 0
    for header, filename, is_json, json_subfield in job.files:
        path = sample_dir / filename
        if not path.exists():
            logger.warning("[%s] Missing input: %s", job.name, path)
            continue
        if is_json:
            data = json.loads(path.read_text(encoding="utf-8"))
            if json_subfield is not None:
                if not isinstance(data, dict) or json_subfield not in data:
                    logger.warning(
                        "[%s] %s: subfield %r not found at top level; skipping",
                        job.name, filename, json_subfield,
                    )
                    continue
                data = data[json_subfield]
            content = format_json_for_use_in_query(data)
        else:
            content = path.read_text(encoding="utf-8")
        parts.append(f"File '{header}':\n{content}")
        total_bytes += len(content)
        logger.info("[%s]  + %s (%d bytes)", job.name, header, len(content))
    logger.info(
        "[%s] Concatenated %d files, %d total bytes",
        job.name,
        len(parts),
        total_bytes,
    )
    return "\n\n".join(parts)


def run_job(job: CompressJob, llm, sample_dir: Path, output_dir: Path) -> None:
    blob = build_blob(job, sample_dir)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            start = time.perf_counter()
            result = CompressReportSection.execute(
                llm=llm,
                section_markdown=blob,
                section_type=job.section_type,
                section_title=job.title,
            )
            elapsed = time.perf_counter() - start
            result.save_raw(output_dir / f"compress_{job.name}_raw.json")
            result.save_markdown(output_dir / f"compress_{job.name}.md")
            scored = result.metadata["per_bucket"]["numeric_values"].get("scored_items", [])
            verified = sum(1 for s in scored if s.get("quote_verified"))
            kept = len(result.response["numeric_values"])
            logger.info(
                "[%s] Done in %.1fs — numeric_values: llm produced %d, %d verified, kept top %d",
                job.name,
                elapsed,
                len(scored),
                verified,
                kept,
            )
            return
        except Exception as e:
            last_error = e
            logger.warning(
                "[%s] Attempt %d failed: %s: %s",
                job.name,
                attempt + 1,
                type(e).__name__,
                str(e)[:200],
            )
    logger.error(
        "[%s] GIVE UP after 3 attempts. Last error: %s", job.name, last_error
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    PlanExeDotEnv.load().update_os_environ()

    sample_dir = Path(os.environ.get("COMPRESS_FULL_SAMPLE_DIR", _DEFAULT_SAMPLE_DIR))
    output_dir = Path(os.environ.get("COMPRESS_FULL_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR))
    llm_name = os.environ.get("COMPRESS_FULL_LLM", _DEFAULT_LLM)

    if not sample_dir.exists():
        raise SystemExit(
            f"Sample directory not found at {sample_dir}. "
            "Set COMPRESS_FULL_SAMPLE_DIR to a real path."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    llm = get_llm(llm_name)
    logger.info("Using LLM: %s", llm_name)
    logger.info("Sample dir: %s", sample_dir)
    logger.info("Output dir: %s", output_dir)

    for job in JOBS:
        run_job(job, llm, sample_dir, output_dir)


if __name__ == "__main__":
    main()
