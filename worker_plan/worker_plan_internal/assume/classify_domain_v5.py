"""
Classify the project domain into a primary domain (and 0-3 secondary
domains) so downstream stages can apply domain-appropriate expertise,
risks, and templates.

The LLM emits only a fit list (each entry: domain + role + reason +
fit level), plus an overall confidence and a short rationale. The
primary domain and secondaries are derived in code from the fits, so
the model cannot emit a primary that contradicts its own fit list.

v5: principle-driven prompt rewrite. v4 contained worked examples
that paraphrased smoke-harness test prompts and steered the
classifier toward those exact answers, making the apparent
improvement a tautology. v5 removes every worked example from the
system prompt and from the schema field descriptions, expresses
the underlying intent — pick the narrowest expert discipline that
fits the prompt's signals — as positive constraints, and trusts
the principle to carry the load. v4 (and v3) are kept on disk for
diff comparison.

PROMPT> python -m worker_plan_internal.assume.classify_domain_v5
"""
import time
import logging
import json
import re
from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, Field
from llama_index.core.llms import ChatMessage, MessageRole
from worker_plan_internal.llm_util.llm_errors import LLMChatError

logger = logging.getLogger(__name__)


OPTIMIZE_INSTRUCTIONS = """\
Goal: classify each plan prompt into a useful primary_domain (and 0-3
secondary_domains) so downstream stages can apply domain-appropriate
expertise, risks, and templates.

The LLM emits only candidate fits (with role + reason); primary and
secondaries are derived deterministically in code. This makes it
structurally impossible for the model to return a primary that
contradicts its own fit list.

Pipeline context
----------------
Runs immediately after prompt parsing and before strategic-lever
identification. Output feeds downstream stages picking assumptions,
expert lenses, regulators, and planning templates.

Schema
------
The LLM emits 1-4 DomainFit entries (or 0 when the prompt names
no concrete project). Each entry has a domain (Title Case noun
phrase naming an expert discipline), a fit ("medium" or "high"),
a role (one of seven literals), and a reason (one short sentence).

Code-side derivation
--------------------
Primary domain is derived from the fits in this priority order:
  1. The first fit with fit="high" and role="outcome".
  2. The first fit with fit="medium" and role="outcome".
  3. The first fit with fit="high" (any role).
  4. "Unclear".

Secondary domains are medium/high-fit domains other than primary,
in original order, capped at 3.

Confidence is taken from the LLM, but forced to "low" when the
derived primary is "Unclear". An empty / whitespace-only primary
also normalizes to "Unclear" with confidence="low".

Warnings
--------
The result carries a `warnings` list naming every silent mutation:
duplicate fits dropped, empty primary normalized, confidence
overridden, etc. Downstream consumers can use these to track
quality regressions without re-running the model.

v5 design philosophy
--------------------
The system prompt is principle-driven and contains no worked
examples. The single load-bearing principle is: pick the narrowest
expert discipline that fits the prompt's signals — what a
specialist who would lead the project calls themselves. Umbrella
labels (Research, Engineering, Science, Technology, Business,
Industry, Energy, Environmental, Environmental Science, Healthcare)
are reserved for prompts that produce no specific subfield,
technique, instrument, substance, medium, or application area.

The reasoning behind this approach:
- Worked examples that paraphrase test-set prompts make the
  classifier appear to improve on the test set without learning
  the underlying principle. Removing them forces the principle
  to carry the load and exposes which models are too small for
  the task.
- LLMs latch onto negative constraints and produce exactly the
  thing they were told to avoid. v5 phrases everything as
  positive constraints (what to do, not what to avoid).
- Schema field descriptions (in DomainFit / DomainFitAssessment
  pydantic Fields) are kept short and example-free for the same
  reasons.

Architectural notes
-------------------
- The model cannot emit a primary that contradicts the fit list
  because it never emits a primary. The cost is that the role
  definition for "outcome" must be carefully written — if the
  model misuses outcome, the derived primary will be wrong even
  though the fit list looks reasonable.
- Dropping low-fit candidates from the schema reduces token spend.
- Cardinality 1-4 (instead of forced 3-4) lets simple
  single-discipline prompts return a single fit without
  fabricating filler.

Model fitness
-------------
- Larger models (gpt-oss-safeguard-20b, gemini-2.0-flash) honor
  the specificity principle reliably from the prompt alone.
- Smaller models (llama-3.1-8b-instruct) tend to drift toward
  umbrella labels even when the principle is stated clearly. v5
  tests how far the principle alone gets without test-fit
  hardcoding. If remaining drift matters, the next step is a
  code-side guardrail that demotes umbrellas when narrower fits
  exist in the same response — not more bullets in the prompt.

Evaluation discipline
---------------------
The smoke harness must be evaluated against a held-out test set
that the prompt has never been tuned against. Otherwise apparent
improvement is unmeasurable and the team risks the same overfit
loop that produced v2/v3/v4.
"""


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """Strip leading/trailing whitespace and collapse internal whitespace runs."""
    return _WHITESPACE_RE.sub(" ", label).strip()


def label_key(label: str) -> str:
    """Case-insensitive comparison key for domain labels."""
    return normalize_label(label).casefold()


class DomainFit(BaseModel):
    domain: str = Field(
        description=(
            "A short Title Case noun phrase (1-3 words) naming an "
            "expert discipline — what a specialist who would lead "
            "this project calls themselves. Pick the narrowest "
            "discipline the prompt's signals support."
        )
    )
    # Accept "low" too — the system prompt asks for medium/high only,
    # but small models will sometimes ignore that and emit "low".
    # Rejecting at the pydantic boundary loses the entire response;
    # accepting and dropping in code with a warning is more robust.
    fit: Literal["low", "medium", "high"] = Field(
        description=(
            "How strongly the project belongs to this domain. "
            "high = central to the outcome, the project's success "
            "depends on this expertise; "
            "medium = materially affects planning (real tasks, risks, "
            "regulators, stakeholders) without being the project's "
            "central identity. "
            "low = incidental, weakly relevant; entries with fit='low' "
            "are dropped during cleanup and never appear in the final "
            "result."
        )
    )
    role: Literal[
        "outcome",
        "constraint",
        "market",
        "method",
        "stakeholder",
        "tool",
        "unclear",
    ] = Field(
        description=(
            "Why this domain shows up. "
            "'outcome' = this domain owns the project's main success "
            "criterion (any kind of success criterion, including "
            "intangible changes and ongoing operations, not only "
            "physical deliverables). "
            "'constraint' = this domain enforces regulatory, "
            "compliance, safety, or legal requirements that must be "
            "met. "
            "'market' = this domain's actors are the audience, buyer, "
            "or beneficiary. "
            "'method' = this domain's techniques are used as means to "
            "deliver the project. "
            "'stakeholder' = a key actor in the project comes from "
            "this domain. "
            "'tool' = this domain provides a generic instrument used "
            "in the project. "
            "'unclear' = this domain is present in the project but "
            "its functional role is genuinely ambiguous."
        )
    )
    reason: str = Field(
        description="One short sentence (≤15 words) explaining the fit and role."
    )


class DomainFitAssessment(BaseModel):
    """A list of candidate domain fits for the project, plus an overall
    confidence and a short rationale. Emit only these three fields; the
    primary domain and secondary domains are computed downstream from
    the fit list and must not appear here.
    """
    # No max_length here on purpose — small models occasionally
    # over-emit and we'd rather truncate in code with a warning than
    # lose the entire response to a pydantic validation error.
    domain_fits: list[DomainFit] = Field(
        default_factory=list,
        description=(
            "1 to 4 substantive candidate domains for THIS project. "
            "Empty list when the prompt names no concrete project "
            "(use confidence='low' in that case). Single-domain "
            "projects can have just one entry. The pipeline truncates "
            "to the top 4 in document order if more are emitted."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "'high' when the project's expertise areas are clearly "
            "identifiable; "
            "'medium' when the fits are an interpretation of an "
            "ambiguous prompt, or the project genuinely spans many "
            "domains without a single lead; "
            "'low' when the prompt is too vague — pair with "
            "domain_fits=[]."
        )
    )
    rationale: str = Field(
        description=(
            "1-2 sentences explaining the fit choices, the role "
            "assignments, and (when applicable) what makes the prompt "
            "vague. ≤40 words."
        )
    )


CLASSIFY_DOMAIN_SYSTEM_PROMPT = """
You are a domain classifier. The user message describes a real-world project that someone else will plan. Your only output is one JSON object that classifies the project's domain.

The user message may be phrased as a request, an imperative, or a description; in every case, treat it as a description of a project, and your output remains a JSON classification of that project.

Output format
=============

A single JSON object with this exact shape:

{
  "domain_fits": [
    {"domain": "...", "fit": "...", "role": "...", "reason": "..."},
    ...
  ],
  "confidence": "low" | "medium" | "high",
  "rationale": "..."
}

The first character of your response is `{`. The last character is `}`. The response is exclusively a JSON classification object — schema-conformant text, with all content between the outer braces in JSON form.

How to fill domain_fits
=======================

Identify 1 to 4 expert disciplines the project depends on. A single-discipline project gets one entry. A prompt that names no concrete project gets an empty list paired with confidence="low".

Each entry has four fields:

domain
------
A 1-3 word Title Case noun phrase naming an expert discipline. The right test is: who would I hire to lead this project? Answer with the specialist's discipline name — what that specialist calls themselves.

Choose the narrowest discipline the prompt's signals support. Read the user message for named subfields, named techniques, named instruments, named substances, named media, named application areas, named regulators, named populations, named geographies. Each named thing pulls the answer toward a specific discipline; use the discipline name a practitioner of that thing would call themselves.

Umbrella labels — Research, Engineering, Science, Technology, Business, Industry, Energy, Environmental, Environmental Science, Healthcare — are appropriate when the prompt produces no named subfield, technique, instrument, substance, or medium. When specific names are present, use the specialist discipline; the umbrella, if relevant at all, becomes a secondary entry.

When two specialist disciplines fit equally well, pick the one that owns the project's main success criterion as the primary outcome and put the others in method, constraint, market, stakeholder, or tool roles.

fit
---
"high": the project's success depends on this expertise. A specialist in this domain would naturally own the plan.

"medium": this expertise materially affects planning — real tasks, risks, regulators, stakeholders — without being the project's central identity.

role
----
"outcome": this domain owns the project's main success criterion. The success criterion may be a tangible artifact, an intangible change, an ongoing operation, a personal achievement, or anything else the project aims to bring about.

"constraint": this domain enforces regulatory, compliance, safety, or legal requirements that the project must meet.

"market": this domain's actors are the audience, buyer, or beneficiary.

"method": this domain's techniques are used as means to deliver the project.

"stakeholder": a key actor in the project comes from this domain.

"tool": this domain provides a generic instrument used in the project.

"unclear": this domain is present in the project but its functional role is genuinely ambiguous.

Use exactly one of these seven literals; pick the closest fit, or "unclear" when no role applies.

reason
------
One sentence ≤15 words explaining why this discipline shows up.

confidence
==========

"high": the project's expert disciplines are clearly identifiable and their roles are unambiguous.

"medium": the fits are an interpretation of an ambiguous prompt, or the project genuinely spans many disciplines without a single lead.

"low": the prompt is too vague to identify a concrete project; pair with domain_fits=[].

rationale
=========

One or two sentences ≤40 words explaining the discipline choices, the role assignments, and what makes the prompt vague when applicable.

Empty-list case
===============

When the prompt is too short or too generic to name a concrete project — when the prompt names no deliverable, no outcome, no audience, no operation, no substance, no medium — emit domain_fits=[], confidence="low", and a one-sentence rationale identifying what specific information is missing.

Pipeline reminder
=================

The pipeline derives primary_domain and secondary_domains from your domain_fits — you do not emit them. Focus on getting the fit list right.
"""


def derive_primary(fits: list[DomainFit]) -> str:
    """Pick the primary_domain from a fit list.

    Priority:
      1. fit='high' and role='outcome'
      2. fit='medium' and role='outcome'
      3. fit='high' (any role)
      4. 'Unclear'
    """
    for f in fits:
        if f.fit == "high" and f.role == "outcome":
            return normalize_label(f.domain)
    for f in fits:
        if f.fit == "medium" and f.role == "outcome":
            return normalize_label(f.domain)
    for f in fits:
        if f.fit == "high":
            return normalize_label(f.domain)
    return "Unclear"


def derive_secondaries(fits: list[DomainFit], primary: str, cap: int = 3) -> list[str]:
    """Pick up to `cap` secondary domains: medium/high-fit, not the primary."""
    primary_key = label_key(primary)
    seen = {primary_key}
    out: list[str] = []
    for f in fits:
        domain = normalize_label(f.domain)
        key = label_key(domain)
        if not domain or key in seen:
            continue
        if f.fit not in ("medium", "high"):
            continue
        seen.add(key)
        out.append(domain)
        if len(out) >= cap:
            break
    return out


@dataclass
class ClassifyDomain:
    """
    Classify a user prompt into a primary domain (with secondaries),
    derived in code from a fit-based assessment the LLM produces.
    """
    system_prompt: str
    user_prompt: str
    response: dict
    metadata: dict
    markdown: str
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def execute(cls, llm, user_prompt: str) -> "ClassifyDomain":
        if not hasattr(llm, "as_structured_llm"):
            raise ValueError("llm must provide as_structured_llm().")
        if not isinstance(user_prompt, str):
            raise ValueError("Invalid user_prompt.")

        logger.debug(f"User Prompt:\n{user_prompt}")

        system_prompt = CLASSIFY_DOMAIN_SYSTEM_PROMPT.strip()

        chat_message_list = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]

        sllm = llm.as_structured_llm(DomainFitAssessment)
        start_time = time.perf_counter()
        try:
            chat_response = sllm.chat(chat_message_list)
        except Exception as e:
            llm_error = LLMChatError(cause=e)
            logger.debug(f"LLM chat interaction failed [{llm_error.error_id}]: {e}")
            logger.error(f"LLM chat interaction failed [{llm_error.error_id}]", exc_info=True)
            raise llm_error from e

        end_time = time.perf_counter()
        duration_seconds = round(end_time - start_time, 3)
        raw_content = chat_response.message.content or ""
        response_byte_count = len(raw_content.encode("utf-8"))
        logger.info(
            f"LLM chat interaction completed in {duration_seconds}s. "
            f"Response byte count: {response_byte_count}"
        )

        assessment: DomainFitAssessment = chat_response.raw
        if assessment is None:
            raise ValueError("LLM returned empty structured response (chat_response.raw is None).")

        warnings: list[str] = []

        # Normalize, dedupe, drop low-fit entries, cap at 4.
        cleaned_fits: list[DomainFit] = []
        seen_fits: set[str] = set()
        for f in assessment.domain_fits:
            domain = normalize_label(f.domain)
            if not domain:
                warnings.append("Dropped fit with empty domain label.")
                continue
            key = label_key(domain)
            if key in seen_fits:
                warnings.append(f"Dropped duplicate fit domain: {domain}")
                continue
            if f.fit == "low":
                warnings.append(f"Dropped low-fit candidate: {domain}")
                continue
            if len(cleaned_fits) >= 4:
                warnings.append(f"Truncated extra fit beyond cap of 4: {domain}")
                continue
            seen_fits.add(key)
            cleaned_fits.append(
                DomainFit(
                    domain=domain,
                    fit=f.fit,
                    role=f.role,
                    reason=normalize_label(f.reason),
                )
            )

        # Derive primary and secondaries from the (cleaned) fit list.
        primary = derive_primary(cleaned_fits)
        secondaries = derive_secondaries(cleaned_fits, primary)

        # Confidence: keep model's value, except force "low" when primary is Unclear.
        confidence = assessment.confidence
        if primary == "Unclear":
            if confidence != "low":
                warnings.append(
                    f"Forced confidence='low' because derived primary is 'Unclear' "
                    f"(model emitted '{confidence}')."
                )
                confidence = "low"
            if cleaned_fits:
                warnings.append(
                    f"Cleared {len(cleaned_fits)} fits because derived primary is 'Unclear'."
                )
                cleaned_fits = []

        rationale = assessment.rationale.strip()

        json_response: dict = {
            "primary_domain": primary,
            "secondary_domains": secondaries,
            "confidence": confidence,
            "domain_fits": [f.model_dump() for f in cleaned_fits],
            "rationale": rationale,
            "warnings": warnings,
        }

        metadata = dict(llm.metadata)
        metadata["llm_classname"] = llm.class_name()
        metadata["duration_seconds"] = duration_seconds
        metadata["response_byte_count"] = response_byte_count

        markdown = cls._convert_to_markdown(
            primary=primary,
            secondaries=secondaries,
            confidence=confidence,
            rationale=rationale,
            fits=cleaned_fits,
            warnings=warnings,
        )

        return cls(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=json_response,
            metadata=metadata,
            markdown=markdown,
            warnings=warnings,
        )

    def to_dict(
        self,
        include_metadata: bool = True,
        include_system_prompt: bool = True,
        include_user_prompt: bool = True,
    ) -> dict:
        d = self.response.copy()
        if include_metadata:
            d["metadata"] = self.metadata
        if include_system_prompt:
            d["system_prompt"] = self.system_prompt
        if include_user_prompt:
            d["user_prompt"] = self.user_prompt
        return d

    def save_raw(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str))

    @staticmethod
    def _convert_to_markdown(
        *,
        primary: str,
        secondaries: list[str],
        confidence: str,
        rationale: str,
        fits: list[DomainFit],
        warnings: list[str],
    ) -> str:
        secondary_display = ", ".join(secondaries) if secondaries else "_(none)_"
        lines = [
            f"**Primary domain:** {primary}",
            "",
            f"**Secondary domains:** {secondary_display}",
            "",
            f"**Confidence:** {confidence.title()}",
            "",
            f"**Rationale:** {rationale}",
        ]
        if fits:
            lines.append("")
            lines.append("**Domain fits:**")
            lines.append("")
            lines.append("| Domain | Fit | Role | Reason |")
            lines.append("|---|---|---|---|")
            for f in fits:
                reason = f.reason.replace("|", "\\|")
                lines.append(
                    f"| {f.domain} | {f.fit.title()} | {f.role} | {reason} |"
                )
        if warnings:
            lines.append("")
            lines.append("**Warnings:**")
            for w in warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)

    def save_markdown(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.markdown)


if __name__ == "__main__":
    # Smoke runner notes:
    # - One LLM per worker thread (threading.local). llama_index LLM clients
    #   are not guaranteed thread-safe; sharing one across the
    #   ThreadPoolExecutor caused intermittent failures.
    # - max_workers is read from the model's luigi_workers config so the
    #   smoke harness mirrors pipeline parallelism.
    # - Always include a few synthetic vague prompts in the smoke set
    #   (e.g. "Help me make a plan for my project.") to verify the
    #   Unclear path end-to-end.
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from worker_plan_internal.llm_factory import get_llm
    from worker_plan_internal.utils.planexe_llmconfig import PlanExeLLMConfig
    from worker_plan_internal.diagnostics.extract_constraints import ExtractConstraints
    from worker_plan_api.prompt_catalog import PromptCatalog
    from worker_plan_api.planexe_dotenv import PlanExeDotEnv

    PlanExeDotEnv.load().update_os_environ()

    # Two classify models tested side by side, each in two conditions:
    # baseline (raw prompt) and augmented (prompt + extracted constraints).
    LLM_NAMES = [
        "openrouter-llama-3.1-8b-instruct-nitro",
        "openrouter-gpt-oss-safeguard-20b-nitro",
    ]
    # Single model used for the constraint-extraction pre-pass. Picked for
    # speed + reliability on JSON output. We extract once per prompt and
    # reuse the result for both classify models.
    EXTRACT_LLM_NAME = "openrouter-gpt-oss-safeguard-20b-nitro"

    @dataclass
    class TestPrompt:
        id: str
        prompt: str

    prompt_catalog = PromptCatalog()
    prompt_catalog.load_simple_plan_prompts()
    all_items = prompt_catalog.all()
    sorted_items = sorted(all_items, key=lambda x: x.id)

    # Replay the prior sampling sequence faithfully so we exclude every
    # ID that has already been tested:
    #   - seeds 7 and 8 each shuffled full sorted_items and took 20.
    #   - seed 100 then shuffled (sorted_items minus 7's and 8's picks)
    #     and took 40.
    import random
    used_ids: set[str] = set()
    for prior_seed in (7, 8):  # each applied to full sorted_items
        prior_shuffled = list(sorted_items)
        random.Random(prior_seed).shuffle(prior_shuffled)
        for item in prior_shuffled[:20]:
            used_ids.add(item.id)
    pool_after_78 = [item for item in sorted_items if item.id not in used_ids]
    prior_shuffled = list(pool_after_78)
    random.Random(100).shuffle(prior_shuffled)
    for item in prior_shuffled[:40]:
        used_ids.add(item.id)
    fresh_pool = [item for item in sorted_items if item.id not in used_ids]

    SAMPLE_SEED = 300
    sample_size = min(20, len(fresh_pool))
    rng = random.Random(SAMPLE_SEED)
    shuffled = list(fresh_pool)
    rng.shuffle(shuffled)
    catalog_sample = shuffled[:sample_size]

    vague_prompts = [
        TestPrompt("vague-help", "Help me make a plan for my project."),
        TestPrompt("vague-thing", "I want to do a thing."),
        TestPrompt("vague-improve", "Improve things."),
    ]

    sample_items = list(catalog_sample) + vague_prompts

    def augment_with_constraints(prompt: str, constraints_md: str) -> str:
        """Format the constraint-extraction markdown after the original prompt.

        The classifier sees the original prompt followed by a delimited
        section labelled "Extracted constraints". The classifier system
        prompt does not need to know about this section — it just gives
        the model a structured summary of explicit signals to consider.
        """
        if not constraints_md.strip():
            return prompt
        return (
            f"{prompt}\n\n"
            f"---\n\n"
            f"## Extracted constraints (auto-derived; for context only)\n"
            f"{constraints_md.strip()}\n"
        )

    def run_extract_phase() -> dict[int, str]:
        """Run ExtractConstraints once per prompt; return {idx: constraints_md}."""
        try:
            cfg_dict = PlanExeLLMConfig.load().llm_config_dict.get(EXTRACT_LLM_NAME, {})
            max_workers = max(1, int(cfg_dict.get("luigi_workers", 1)))
        except Exception:
            max_workers = 1

        thread_local = threading.local()

        def get_thread_llm():
            llm = getattr(thread_local, "llm", None)
            if llm is None:
                llm = get_llm(EXTRACT_LLM_NAME)
                thread_local.llm = llm
            return llm

        def extract_one(idx, item):
            try:
                result = ExtractConstraints.execute(get_thread_llm(), item.prompt)
                return idx, item.id, result.markdown, None
            except Exception as exc:
                return idx, item.id, "", exc

        print(
            f"\n========== EXTRACT phase ({EXTRACT_LLM_NAME}, "
            f"max_workers={max_workers}) =========="
        )
        out: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(extract_one, idx, item)
                for idx, item in enumerate(sample_items, start=1)
            ]
            for future in as_completed(futures):
                idx, prompt_id, md, exc = future.result()
                if exc is None:
                    out[idx] = md
                    print(f"  ✓ [{idx}/{len(sample_items)}] {prompt_id} ({len(md)} chars)", flush=True)
                else:
                    out[idx] = ""
                    print(f"  ✗ [{idx}/{len(sample_items)}] {prompt_id}: {exc}", flush=True)
        return out

    def run_model(llm_name: str, constraints_by_idx: dict[int, str] | None) -> dict:
        """Run classify_domain on every sample item.

        constraints_by_idx=None  -> baseline (raw prompt only)
        constraints_by_idx=dict  -> augmented (prompt + extracted constraints)
        """
        try:
            cfg_dict = PlanExeLLMConfig.load().llm_config_dict.get(llm_name, {})
            max_workers = max(1, int(cfg_dict.get("luigi_workers", 1)))
        except Exception:
            max_workers = 1

        thread_local = threading.local()

        def get_thread_llm():
            llm = getattr(thread_local, "llm", None)
            if llm is None:
                llm = get_llm(llm_name)
                thread_local.llm = llm
            return llm

        def classify_one(idx, item):
            try:
                if constraints_by_idx is not None:
                    classifier_input = augment_with_constraints(
                        item.prompt, constraints_by_idx.get(idx, "")
                    )
                else:
                    classifier_input = item.prompt
                result = ClassifyDomain.execute(get_thread_llm(), classifier_input)
                return idx, item.id, item.prompt, result.to_dict(
                    include_system_prompt=False,
                    include_user_prompt=False,
                    include_metadata=False,
                ), None
            except Exception as exc:
                return idx, item.id, item.prompt, None, exc

        condition = "augmented" if constraints_by_idx is not None else "baseline"
        print(
            f"\n========== {llm_name} [{condition}] "
            f"({len(sample_items)} prompts, max_workers={max_workers}) =========="
        )
        results: dict = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(classify_one, idx, item)
                for idx, item in enumerate(sample_items, start=1)
            ]
            for future in as_completed(futures):
                idx, prompt_id, prompt_text, json_response, exc = future.result()
                results[idx] = (prompt_id, prompt_text, json_response, exc)
                if exc is None:
                    print(f"  ✓ [{idx}/{len(sample_items)}] {prompt_id}", flush=True)
                else:
                    print(f"  ✗ [{idx}/{len(sample_items)}] {prompt_id}: {exc}", flush=True)
        return results

    print(
        f"=== Domain classification (fit-derivation) — fresh sample of "
        f"{len(catalog_sample)} catalog prompts (SAMPLE_SEED={SAMPLE_SEED}, "
        f"excluded {len(used_ids)} prior IDs) + {len(vague_prompts)} vague — "
        f"across {len(LLM_NAMES)} models × 2 conditions (baseline vs augmented) ==="
    )

    # Phase 1: extract constraints once per prompt — reused for both classifiers.
    constraints_by_idx = run_extract_phase()

    # Phase 2: classify each prompt under both conditions for each model.
    CONDITIONS = ("baseline", "augmented")
    all_results: dict[tuple[str, str], dict] = {}
    for llm_name in LLM_NAMES:
        all_results[(llm_name, "baseline")] = run_model(llm_name, None)
        all_results[(llm_name, "augmented")] = run_model(llm_name, constraints_by_idx)

    # Per-prompt side-by-side comparison.
    print()
    reference_key = (LLM_NAMES[0], "baseline")
    flip_counts: dict[str, int] = {llm: 0 for llm in LLM_NAMES}
    flips_by_model: dict[str, list[str]] = {llm: [] for llm in LLM_NAMES}
    for idx in sorted(all_results[reference_key]):
        prompt_id = all_results[reference_key][idx][0]
        prompt_text = all_results[reference_key][idx][1]
        print(f"\n[{idx}/{len(sample_items)}] Prompt ID: {prompt_id} (length: {len(prompt_text)} chars)")
        print(f"Preview: {prompt_text[:160].replace(chr(10), ' ')}...")
        for llm_name in LLM_NAMES:
            primaries: dict[str, str] = {}
            for condition in CONDITIONS:
                entry = all_results[(llm_name, condition)][idx]
                json_response = entry[2]
                exc = entry[3]
                short = llm_name.replace("openrouter-", "")
                tag = f"{short:<40s} | {condition:<9s}"
                if exc is not None:
                    print(f"  [{tag}] Error: {exc}")
                    primaries[condition] = f"<error: {exc}>"
                elif json_response is not None:
                    primary = json_response.get("primary_domain")
                    secondary = json_response.get("secondary_domains") or []
                    conf = json_response.get("confidence")
                    primaries[condition] = primary or "<none>"
                    print(
                        f"  [{tag}] primary={primary}, "
                        f"secondary={secondary}, conf={conf}"
                    )
            base = primaries.get("baseline")
            aug = primaries.get("augmented")
            if base is not None and aug is not None and base != aug:
                flip_counts[llm_name] += 1
                flips_by_model[llm_name].append(
                    f"  [{idx}] {prompt_id}: {base} -> {aug}"
                )

    # Aggregate summary: how many baseline/augmented disagreements per model.
    print("\n========== SUMMARY: baseline -> augmented primary flips ==========")
    total = len(sample_items)
    for llm_name in LLM_NAMES:
        short = llm_name.replace("openrouter-", "")
        n = flip_counts[llm_name]
        print(f"\n{short}: {n}/{total} prompts changed primary_domain")
        for line in flips_by_model[llm_name]:
            print(line)
