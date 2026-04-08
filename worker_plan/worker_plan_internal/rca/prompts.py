# worker_plan/worker_plan_internal/rca/prompts.py
"""Pydantic models and prompt builders for RCA."""
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole


# -- Pydantic models for structured LLM output --------------------------------

class IdentifiedFlaw(BaseModel):
    """A discrete flaw found in a pipeline output file."""
    description: str = Field(description="One-sentence description of the flaw")
    evidence: str = Field(description="Direct quote from the file demonstrating the flaw")
    severity: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="HIGH: fabricated data or missing critical analysis. MEDIUM: weak reasoning or vague claims. LOW: minor gaps."
    )


class FlawIdentificationResult(BaseModel):
    """Result of analyzing a file for flaws."""
    flaws: list[IdentifiedFlaw] = Field(description="List of discrete flaws found in the file")


class UpstreamCheckResult(BaseModel):
    """Result of checking an upstream file for a flaw precursor."""
    found: bool = Field(description="True if this file contains the flaw or a precursor to it")
    evidence: str | None = Field(description="Direct quote from the file if found, null otherwise")
    explanation: str = Field(description="How this connects to the downstream flaw, or why this file is clean")


class SourceCodeAnalysisResult(BaseModel):
    """Result of analyzing source code at a flaw's origin node."""
    category: Literal["prompt_fixable", "domain_complexity", "missing_input"] = Field(
        description=(
            "prompt_fixable: the prompt forgot to ask for something or has a gap that can be fixed by editing the prompt. "
            "domain_complexity: the topic is inherently uncertain, contentious, or requires domain expertise that no prompt change can resolve. "
            "missing_input: the user's plan prompt didn't provide enough context for the pipeline to work with."
        )
    )
    likely_cause: str = Field(description="What in the prompt, logic, or domain caused the flaw")
    relevant_code_section: str = Field(description="The specific code or prompt text responsible")
    suggestion: str = Field(description="How to fix or prevent this flaw")


# -- Prompt builders -----------------------------------------------------------

def build_flaw_identification_messages(
    filename: str,
    file_content: str,
    user_flaw_description: str,
) -> list[ChatMessage]:
    """Build messages for Phase 1: identifying discrete flaws in a file."""
    system = (
        "You are analyzing an intermediary file from a project planning pipeline.\n"
        "The user has described a specific flaw they observed. Your job:\n\n"
        "1. FIRST, locate the user's specific flaw in the file. Find the passage that "
        "corresponds to what the user described. This flaw MUST be the first item in your list.\n"
        "2. THEN, identify any additional discrete flaws that are closely related to the "
        "user's concern (e.g., other instances of the same problem pattern, or flaws that "
        "share the same root cause). Do NOT list every possible flaw in the file — only "
        "those connected to what the user raised.\n\n"
        "For each flaw, provide a short description (one sentence), a direct quote "
        "from the file as evidence (keep quotes under 200 characters), and a severity level.\n"
        "Only identify real flaws — do not flag stylistic preferences or minor formatting issues.\n"
        "Severity levels:\n"
        "- HIGH: fabricated data, invented statistics, or missing critical analysis\n"
        "- MEDIUM: weak reasoning, vague unsupported claims, or shallow treatment\n"
        "- LOW: minor gaps that don't significantly impact the plan"
    )
    user = (
        f"User's flaw description:\n{user_flaw_description}\n\n"
        f"Filename: {filename}\n"
        f"File content:\n{file_content}"
    )
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(role=MessageRole.USER, content=user),
    ]


def build_upstream_check_messages(
    flaw_description: str,
    evidence_quote: str,
    upstream_filename: str,
    upstream_file_content: str,
) -> list[ChatMessage]:
    """Build messages for Phase 2: checking if a flaw exists in an upstream file."""
    system = (
        "You are tracing a flaw through a project planning pipeline to find where it originated.\n"
        "A downstream file contains a flaw. You are examining an upstream file that was an input "
        "to the node that produced the flawed output.\n\n"
        "Determine if this upstream file CAUSED or CONTRIBUTED to the downstream flaw.\n"
        "This means the upstream file contains content that was carried forward, transformed, "
        "or amplified into the downstream flaw. Merely discussing a related topic is NOT enough.\n\n"
        "If YES: quote the specific sentence or phrase (under 200 characters) and explain "
        "the causal mechanism — how this upstream content led to the downstream flaw.\n"
        "If NO: explain why this file is clean regarding this specific flaw.\n\n"
        "Be strict. Only say YES if you can identify a clear causal link, not just topical overlap."
    )
    user = (
        f"Flaw: {flaw_description}\n"
        f"Evidence from downstream: {evidence_quote}\n\n"
        f"Upstream filename: {upstream_filename}\n"
        f"Upstream file content:\n{upstream_file_content}"
    )
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(role=MessageRole.USER, content=user),
    ]


def build_source_code_analysis_messages(
    flaw_description: str,
    evidence_quote: str,
    source_code_contents: list[tuple[str, str]],
) -> list[ChatMessage]:
    """Build messages for Phase 3: analyzing source code at flaw origin.

    Args:
        source_code_contents: list of (filename, content) tuples
    """
    system = (
        "A flaw was introduced at this pipeline node. The flaw exists in its output "
        "but NOT in any of its inputs, so this node created it.\n\n"
        "First, classify the root cause into one of three categories:\n"
        "- prompt_fixable: The prompt has a gap or oversight that can be fixed by editing "
        "the prompt text. Example: the prompt asks for budget estimates but doesn't require "
        "sourcing or validation.\n"
        "- domain_complexity: The topic is inherently uncertain, politically sensitive, or "
        "requires specialized domain expertise that no prompt change can fully resolve. "
        "Example: caste enumeration in India is politically contentious regardless of how "
        "the prompt is worded.\n"
        "- missing_input: The user's original plan description didn't provide enough detail "
        "for this node to produce quality output. Example: the plan says 'open a shop' "
        "without specifying location, budget, or target market.\n\n"
        "Then examine the source code to identify the specific cause. Be specific — point "
        "to lines or prompt phrases. Focus on the system prompt text and data transformation logic."
    )
    source_sections = []
    for fname, content in source_code_contents:
        source_sections.append(f"--- {fname} ---\n{content}")
    source_text = "\n\n".join(source_sections)

    user = (
        f"Flaw: {flaw_description}\n"
        f"Evidence from output: {evidence_quote}\n\n"
        f"Source code files:\n{source_text}"
    )
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(role=MessageRole.USER, content=user),
    ]
