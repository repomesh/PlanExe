import logging
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Optional

from llama_index.core.llms.llm import LLM

from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, LLMModelBase, LLMAttempt
from worker_plan_internal.report.report_generator import ReportGenerator, ReportDocumentItem

logger = logging.getLogger(__name__)

PING_LLM_PROMPT = "Reply with 'PONG' and one short sentence confirming you can answer requests."
PING_LLM_REPORT_TITLE = "PlanExe LLM Ping"


@dataclass
class PingLLMResult:
    prompt: str
    response_text: str
    attempts: list[LLMAttempt]
    duration_seconds: float
    started_at: datetime
    error_message: Optional[str] = None


def _validate_run_dir(run_id_dir: Path) -> None:
    if not run_id_dir.exists():
        raise FileNotFoundError(f"The run_id_dir does not exist: {run_id_dir!r}")
    if not run_id_dir.is_dir():
        raise NotADirectoryError(f"The run_id_dir is not a directory: {run_id_dir!r}")
    if not (run_id_dir / FilenameEnum.START_TIME.value).exists():
        raise FileNotFoundError(
            f"The '{FilenameEnum.START_TIME.value}' file does not exist in the run_id_dir: {run_id_dir!r}"
        )
    if not (run_id_dir / FilenameEnum.INITIAL_PLAN_RAW.value).exists():
        raise FileNotFoundError(
            f"The '{FilenameEnum.INITIAL_PLAN_RAW.value}' file does not exist in the run_id_dir: {run_id_dir!r}"
        )


def _describe_llm_model(llm_model: LLMModelBase) -> str:
    model_name = getattr(llm_model, "name", None)
    if isinstance(model_name, str) and model_name:
        return model_name
    inner_llm = getattr(llm_model, "llm", None)
    if inner_llm is not None:
        return inner_llm.__class__.__name__
    return repr(llm_model)


def _build_attempts_table(attempts: list[LLMAttempt]) -> str:
    if not attempts:
        return "<p>No attempts were recorded.</p>"

    rows = []
    for index, attempt in enumerate(attempts):
        status = "success" if attempt.success else "failed"
        exception_text = escape(repr(attempt.exception)) if attempt.exception else ""
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(_describe_llm_model(attempt.llm_model))}</td>"
            f"<td>{escape(attempt.stage)}</td>"
            f"<td>{status}</td>"
            f"<td>{attempt.duration:.2f}s</td>"
            f"<td>{exception_text}</td>"
            "</tr>"
        )

    rows_html = "\n".join(rows)
    return (
        "<table>"
        "<thead>"
        "<tr><th>#</th><th>LLM</th><th>Stage</th><th>Status</th><th>Duration</th><th>Error</th></tr>"
        "</thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def _build_ping_report_html(result: PingLLMResult) -> str:
    success_attempt = next((attempt for attempt in result.attempts if attempt.success), None)
    selected_llm = _describe_llm_model(success_attempt.llm_model) if success_attempt else "None"

    error_section = ""
    if result.error_message:
        error_section = (
            "<h3>Error</h3>"
            f"<pre>{escape(result.error_message)}</pre>"
        )

    response_text = result.response_text or "(no response)"
    return (
        "<p><strong>Status:</strong> "
        f"{'ok' if result.error_message is None else 'failed'}</p>"
        "<p><strong>Started:</strong> "
        f"{escape(result.started_at.isoformat())}</p>"
        "<p><strong>Duration:</strong> "
        f"{result.duration_seconds:.2f} seconds</p>"
        "<p><strong>Selected LLM:</strong> "
        f"{escape(selected_llm)}</p>"
        f"{error_section}"
        "<h3>Prompt</h3>"
        f"<pre>{escape(result.prompt)}</pre>"
        "<h3>Response</h3>"
        f"<pre>{escape(response_text)}</pre>"
        "<h3>Attempts</h3>"
        f"{_build_attempts_table(result.attempts)}"
    )


def _write_ping_report(output_path: Path, result: PingLLMResult) -> None:
    rg = ReportGenerator()
    ping_html = _build_ping_report_html(result)
    rg.report_item_list.append(ReportDocumentItem("LLM Ping", ping_html))
    rg.save_report(output_path, title=PING_LLM_REPORT_TITLE, execute_plan_section_hidden=True)


def run_ping_llm_report(
    run_id_dir: Path,
    llm_models: list[LLMModelBase],
    prompt: str = PING_LLM_PROMPT,
) -> PingLLMResult:
    _validate_run_dir(run_id_dir)

    llm_executor = LLMExecutor(llm_models=llm_models)
    started_at = datetime.now().astimezone()
    start_time = time.perf_counter()
    error: Optional[Exception] = None
    response_text = ""

    def execute_function(llm: LLM) -> str:
        return llm.complete(prompt).text

    try:
        response_text = llm_executor.run(execute_function)
    except Exception as exc:
        error = exc
        logger.error("PING_LLM execution failed: %s", exc, exc_info=True)

    duration_seconds = time.perf_counter() - start_time
    result = PingLLMResult(
        prompt=prompt,
        response_text=response_text,
        attempts=llm_executor.attempts,
        duration_seconds=duration_seconds,
        started_at=started_at,
        error_message=str(error) if error else None,
    )

    report_path = run_id_dir / FilenameEnum.REPORT_HTML.value
    _write_ping_report(report_path, result)

    if error is None:
        pipeline_complete_path = run_id_dir / FilenameEnum.PIPELINE_COMPLETE.value
        pipeline_complete_path.write_text("LLM ping completed.\n", encoding="utf-8")

    if error is not None:
        raise error

    return result
