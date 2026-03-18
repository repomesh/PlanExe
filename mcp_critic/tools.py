"""
Tool handlers for mcp_critic.

Each function wraps a diagnostic class from worker_plan_internal.
Errors return partial results rather than crashing.
"""
import logging
import time
from typing import Optional

from mcp_critic.config import build_llm_executor

logger = logging.getLogger(__name__)


def run_premise_attack(
    prompt: str,
    model_profile: Optional[str] = None,
    output_format: str = "json",
) -> dict:
    """
    Run PremiseAttack (5-lens ensemble) over the given prompt.

    Args:
        prompt: The plan/idea to stress-test.
        model_profile: Optional model profile (baseline/premium/frontier/custom).
        output_format: "json" (default) or "markdown".

    Returns:
        dict with keys: verdict, lenses, metadata (json) or markdown (str).
    """
    from worker_plan_internal.diagnostics.premise_attack import (
        PremiseAttack,
        DEFAULT_SYSTEM_PROMPTS,
    )

    llm_executor = build_llm_executor(model_profile=model_profile)
    start = time.perf_counter()

    try:
        result = PremiseAttack.execute(llm_executor=llm_executor, user_prompt=prompt)
    except Exception as e:
        logger.error("PremiseAttack.execute failed", exc_info=True)
        return {
            "error": str(e),
            "verdict": "ERROR",
            "lenses": [],
            "metadata": {"duration_seconds": int(time.perf_counter() - start)},
        }

    if output_format == "markdown":
        return {"markdown": result.markdown}

    lens_names = [name for (_, name, _) in DEFAULT_SYSTEM_PROMPTS]
    lenses = []
    for i, doc in enumerate(result.response_list):
        lens_name = lens_names[i] if i < len(lens_names) else f"Lens {i + 1}"
        lenses.append({
            "name": lens_name,
            "core_thesis": doc.core_thesis,
            "reasons": doc.reasons,
            "second_order_effects": doc.second_order_effects,
            "evidence": doc.evidence,
            "bottom_line": doc.bottom_line,
        })

    models_used = []
    for m in result.metadata.get("models", []):
        name = m.get("model_name") or m.get("llm_classname") or "unknown"
        if name not in models_used:
            models_used.append(name)

    # Derive overall verdict: REJECT if any lens rejects (bottom_line starts with REJECT)
    has_reject = any("REJECT" in (l.get("bottom_line") or "").upper() for l in lenses)
    verdict = "REJECT" if has_reject else "PROCEED"

    return {
        "verdict": verdict,
        "lenses": lenses,
        "metadata": {
            "duration_seconds": result.metadata.get("duration", int(time.perf_counter() - start)),
            "models_used": models_used,
            "lens_count": len(lenses),
        },
    }


def run_premortem(
    prompt: str,
    speed_vs_detail: str = "fast_but_skip_details",
    model_profile: Optional[str] = None,
    output_format: str = "json",
) -> dict:
    """
    Run Premortem analysis over the given prompt.

    Args:
        prompt: The plan to analyze for failure modes.
        speed_vs_detail: "fast_but_skip_details" or "all_details_but_slow".
        model_profile: Optional model profile.
        output_format: "json" (default) or "markdown".

    Returns:
        dict with keys: assumptions_to_kill, failure_modes, metadata (json) or markdown (str).
    """
    from worker_plan_internal.diagnostics.premortem import Premortem
    from worker_plan_api.speedvsdetail import SpeedVsDetailEnum

    llm_executor = build_llm_executor(model_profile=model_profile)

    svd_map = {
        "fast_but_skip_details": SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS,
        "all_details_but_slow": SpeedVsDetailEnum.ALL_DETAILS_BUT_SLOW,
    }
    svd = svd_map.get(speed_vs_detail.lower(), SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS)

    try:
        result = Premortem.execute(
            llm_executor=llm_executor,
            speed_vs_detail=svd,
            user_prompt=prompt,
        )
    except Exception as e:
        logger.error("Premortem.execute failed", exc_info=True)
        return {
            "error": str(e),
            "assumptions_to_kill": [],
            "failure_modes": [],
        }

    if output_format == "markdown":
        return {"markdown": result.markdown}

    return {
        "assumptions_to_kill": result.response.get("assumptions_to_kill", []),
        "failure_modes": result.response.get("failure_modes", []),
        "metadata": result.metadata,
    }


def run_swot(
    prompt: str,
    model_profile: Optional[str] = None,
    output_format: str = "json",
) -> dict:
    """
    Run SWOT analysis over the given prompt.

    Args:
        prompt: The plan/project to analyze.
        model_profile: Optional model profile.
        output_format: "json" (default) or "markdown".

    Returns:
        dict with SWOT keys.
    """
    from worker_plan_internal.swot.swot_phase2_conduct_analysis import (
        swot_phase2_conduct_analysis,
        CONDUCT_SWOT_ANALYSIS_BUSINESS_SYSTEM_PROMPT,
    )
    from worker_plan_internal.llm_factory import get_llm, get_llm_names_by_priority
    import os

    resolved_profile = model_profile or os.environ.get("PLANEXE_MODEL_PROFILE", "").strip() or None
    llm_model_name = os.environ.get("LLM_MODEL", "").strip() or None

    if llm_model_name:
        llm = get_llm(llm_name=llm_model_name)
    else:
        names = get_llm_names_by_priority(model_profile=resolved_profile)
        if not names:
            return {"error": "No LLM models found in config."}
        llm = get_llm(llm_name=names[0], model_profile=resolved_profile)

    try:
        result = swot_phase2_conduct_analysis(
            llm=llm,
            user_prompt=prompt,
            system_prompt=CONDUCT_SWOT_ANALYSIS_BUSINESS_SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.error("swot_phase2_conduct_analysis failed", exc_info=True)
        return {"error": str(e)}

    if output_format == "markdown":
        # Simple markdown rendering
        lines = ["# SWOT Analysis\n"]
        for key in ("strengths", "weaknesses", "opportunities", "threats", "recommendations", "strategic_objectives"):
            lines.append(f"## {key.replace('_', ' ').title()}\n")
            for item in result.get(key, []):
                lines.append(f"- {item}")
            lines.append("")
        return {"markdown": "\n".join(lines)}

    return result


def run_critique(
    prompt: str,
    tools: Optional[list] = None,
    model_profile: Optional[str] = None,
    output_format: str = "json",
) -> dict:
    """
    Run all (or selected) critic tools and return a combined verdict.

    Args:
        prompt: The plan to critique.
        tools: List of tool names to run. Defaults to all: ["premise_attack", "premortem", "swot"].
        model_profile: Optional model profile.
        output_format: "json" (default) or "markdown".

    Returns:
        Combined dict with results from all selected tools.
    """
    if tools is None:
        tools = ["premise_attack", "premortem", "swot"]

    output = {}
    errors = []

    if "premise_attack" in tools:
        try:
            output["premise_attack"] = run_premise_attack(
                prompt=prompt, model_profile=model_profile, output_format=output_format
            )
        except Exception as e:
            logger.error("critique: premise_attack failed", exc_info=True)
            errors.append({"tool": "premise_attack", "error": str(e)})

    if "premortem" in tools:
        try:
            output["premortem"] = run_premortem(
                prompt=prompt, model_profile=model_profile, output_format=output_format
            )
        except Exception as e:
            logger.error("critique: premortem failed", exc_info=True)
            errors.append({"tool": "premortem", "error": str(e)})

    if "swot" in tools:
        try:
            output["swot"] = run_swot(
                prompt=prompt, model_profile=model_profile, output_format=output_format
            )
        except Exception as e:
            logger.error("critique: swot failed", exc_info=True)
            errors.append({"tool": "swot", "error": str(e)})

    if errors:
        output["errors"] = errors

    return output
