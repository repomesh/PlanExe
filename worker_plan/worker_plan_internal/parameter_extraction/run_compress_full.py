"""Run CompressReportSection for each PlanExe section using the same input
the corresponding Luigi node ingests, plus that node's own output appended.

- compress_strategic_decisions: classify_domain.md + strategic_decisions.md
- compress_review_plan:         ReviewPlanTask inputs + review_plan.md
- compress_premortem:           PremortemTask inputs + premortem.md
- compress_expert_criticism:    ExpertReviewTask inputs + expert_criticism.md

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
    # (header_filename_as_seen_by_llm, sample_dir_filename, is_json)
    files: list[tuple[str, str, bool]]


# strategic_decisions Luigi node is a markdown renderer with no LLM input
# (StrategicDecisionsMarkdownTask just formats levers JSON), so we use
# classify_domain.md as the upstream artifact and append the node output.
_STRATEGIC_DECISIONS_JOB = CompressJob(
    name="strategic_decisions",
    section_type=ReportSectionTypeEnum.STRATEGIC_DECISIONS,
    title="Strategic Decisions (classify_domain + strategic_decisions)",
    files=[
        ("classify_domain.md", "classify_domain.md", False),
        ("strategic_decisions.md", "strategic_decisions.md", False),
    ],
)

# ReviewPlanTask query order — see plan/nodes/review_plan.py.
_REVIEW_PLAN_JOB = CompressJob(
    name="review_plan",
    section_type=ReportSectionTypeEnum.REVIEW_PLAN,
    title="Review Plan (full Luigi input + output)",
    files=[
        ("strategic_decisions.md", "strategic_decisions.md", False),
        ("scenarios.md", "scenarios.md", False),
        ("assumptions.md", "consolidate_assumptions_short.md", False),
        ("project-plan.md", "project_plan.md", False),
        ("data-collection.md", "data_collection.md", False),
        ("related-resources.md", "related_resources.md", False),
        ("swot-analysis.md", "swot_analysis.md", False),
        ("team.md", "team.md", False),
        ("pitch.md", "pitch.md", False),
        ("expert-review.md", "expert_criticism.md", False),
        ("work-breakdown-structure.csv", "wbs_project_level1_and_level2_and_level3.csv", False),
        ("review_plan.md", "review_plan.md", False),
    ],
)

# PremortemTask query order — see plan/nodes/premortem.py.
_PREMORTEM_JOB = CompressJob(
    name="premortem",
    section_type=ReportSectionTypeEnum.PREMORTEM,
    title="Premortem (full Luigi input + output)",
    files=[
        ("strategic_decisions.md", "strategic_decisions.md", False),
        ("scenarios.md", "scenarios.md", False),
        ("assumptions.md", "consolidate_assumptions_short.md", False),
        ("project-plan.md", "project_plan.md", False),
        ("data-collection.md", "data_collection.md", False),
        ("related-resources.md", "related_resources.md", False),
        ("swot-analysis.md", "swot_analysis.md", False),
        ("team.md", "team.md", False),
        ("pitch.md", "pitch.md", False),
        ("expert-review.md", "expert_criticism.md", False),
        ("work-breakdown-structure.csv", "wbs_project_level1_and_level2_and_level3.csv", False),
        ("review-plan.md", "review_plan.md", False),
        ("questions-and-answers.md", "questions_and_answers.md", False),
        ("premortem.md", "premortem.md", False),
    ],
)

# ExpertReviewTask query order — see plan/nodes/expert_review.py.
# pre_project_assessment.json is fed through format_json_for_use_in_query so
# the serialisation matches the Luigi task exactly.
_EXPERT_CRITICISM_JOB = CompressJob(
    name="expert_criticism",
    section_type=ReportSectionTypeEnum.EXPERT_CRITICISM,
    title="Expert Criticism (full Luigi input + output)",
    files=[
        ("initial-plan.txt", "plan.txt", False),
        ("strategic_decisions.md", "strategic_decisions.md", False),
        ("scenarios.md", "scenarios.md", False),
        ("pre-project assessment.json", "pre_project_assessment.json", True),
        ("project_plan.md", "project_plan.md", False),
        ("SWOT Analysis.md", "swot_analysis.md", False),
        ("expert_criticism.md", "expert_criticism.md", False),
    ],
)

JOBS: tuple[CompressJob, ...] = (
    _STRATEGIC_DECISIONS_JOB,
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
    for header, filename, is_json in job.files:
        path = sample_dir / filename
        if not path.exists():
            logger.warning("[%s] Missing input: %s", job.name, path)
            continue
        if is_json:
            content = format_json_for_use_in_query(
                json.loads(path.read_text(encoding="utf-8"))
            )
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
