# Prompt Adherence Check for PlanExe

## Problem

PlanExe's pipeline has a "normalization bias." Each of the ~70 nodes nudges the plan toward what a reasonable project *should* look like, and the cumulative drift over the full pipeline is significant. The user's stated reality gets overridden by the LLM's priors about what's plausible.

This manifests as:
- **Stated facts ignored.** The user says "the East Wing has already been demolished" but the plan includes demolition permitting steps.
- **Requirements softened.** The user says "100% renewable energy" and the plan targets 60-80%.
- **Intent diluted.** The user's tone is "this is happening, execute it" but the plan spends 40% on feasibility studies.
- **Unsolicited caveats.** The plan adds qualifications, risk disclaimers, and scope reductions the user didn't ask for.
- **Generic PM filler.** The plan relies on boilerplate project management language instead of addressing the specific problem.

Existing pipeline steps (Premise Attack, Premortem, Expert Criticism, Self Audit) assess plan *quality* — whether the plan is internally consistent, well-structured, and risk-aware. None of them check whether the plan actually does what the user asked.

## Goal

A pipeline step that checks the final plan against the original user prompt and produces a scored report showing which user directives were honored, softened, or ignored. The user can scan the report and immediately see the degree of prompt drift.

## Architecture

Two-phase LLM approach: extract directives from the prompt, then score each one against the final plan.

### Phase 1 — Extract Directives

Read `plan.txt` (the original user prompt) and extract a structured list of directives. Each directive is one thing the user stated or implied that the plan must respect.

```python
class DirectiveType(str, Enum):
    CONSTRAINT = "constraint"        # "Budget: DKK 500M", "Timeline: 12 months"
    STATED_FACT = "stated_fact"      # "The East Wing has already been demolished"
    REQUIREMENT = "requirement"      # "Build a casino", "Reeducate teachers"
    BANNED = "banned"                # "Banned words: blockchain/NFT"
    INTENT = "intent"               # "I'm not targeting revenue", tone/posture signals
```

Each directive has:
- `directive_id`: "D1", "D2", etc.
- `directive_type`: one of the types above
- `text`: the user's words (short quote or paraphrase)
- `importance_5`: 1 (minor detail) to 5 (core requirement)

The LLM is instructed to extract 5-15 directives, prioritizing things that are easy to dilute: stated facts about the world, hard numbers, explicit scope boundaries, banned words, and the user's posture (execute vs. study).

### Phase 2 — Score Against Final Plan

Read the extracted directives plus the final plan artifacts (executive summary, project plan, consolidated assumptions). For each directive, score adherence.

```python
class AdherenceCategory(str, Enum):
    FULLY_HONORED = "fully_honored"
    PARTIALLY_HONORED = "partially_honored"
    SOFTENED = "softened"               # requirement weakened
    IGNORED = "ignored"                 # not addressed at all
    CONTRADICTED = "contradicted"       # plan says the opposite
    UNSOLICITED_CAVEAT = "unsolicited_caveat"  # plan adds qualifications user didn't ask for
```

Each scoring result has:
- `directive_id`: references a Phase 1 directive
- `adherence_5`: 1 (ignored/contradicted) to 5 (fully honored)
- `category`: one of the categories above
- `evidence`: direct quote from the plan (under 200 chars)
- `explanation`: how the plan handled this directive and why the score was given

### Output Files

- `prompt_adherence_raw.json` — full structured data (directives + scores + metadata)
- `prompt_adherence.md` — human-readable report

### Markdown Report Structure

1. **Summary table** — all directives sorted by severity (importance_5 x (6 - adherence_5), worst offenders first):

```
| ID | Directive | Type | Importance | Adherence | Category |
|----|-----------|------|------------|-----------|----------|
| D3 | "East Wing already demolished" | stated_fact | 5/5 | 1/5 | contradicted |
| D1 | "Budget: DKK 500M" | constraint | 5/5 | 3/5 | softened |
| D7 | "No feasibility studies" | intent | 4/5 | 2/5 | ignored |
```

2. **Overall adherence score** — weighted average: `sum(adherence_5 * importance_5) / sum(5 * importance_5)` as a percentage. A plan that fully honors everything scores 100%.

3. **Detail section** — for each directive scoring adherence_5 ≤ 3, the full explanation and evidence quotes from both the prompt and the plan.

### Pipeline Placement

After `self_audit`, before `report`. The task reads:
- `setup` — plan.txt (the original user prompt)
- `executive_summary` — the final plan summary
- `project_plan` — the detailed plan
- `consolidate_assumptions_markdown` — accumulated assumptions that may have drifted

The report task includes `prompt_adherence.md` in the final HTML output.

### FilenameEnum Entries

```python
PROMPT_ADHERENCE_RAW = "prompt_adherence_raw.json"
PROMPT_ADHERENCE_MARKDOWN = "prompt_adherence.md"
```

### Code Structure

```
worker_plan/worker_plan_internal/
    diagnostics/
        prompt_adherence.py          — Phase 1 + Phase 2 logic, Pydantic models, markdown generation
    plan/nodes/
        prompt_adherence.py          — Luigi task (PromptAdherenceTask)
```

Follows the same pattern as `premortem.py` / `nodes/premortem.py`:
- Business logic in `diagnostics/prompt_adherence.py`
- Luigi wiring in `plan/nodes/prompt_adherence.py`
- Pydantic structured output via `llm.as_structured_llm()`
- `LLMExecutor` for model fallback and retry

### Scope Boundaries

**In scope:**
- Extract directives from plan.txt
- Score each directive against the final plan
- Produce JSON + markdown report
- Integrate as a Luigi pipeline step
- Include in the final HTML report

**Out of scope:**
- Fixing the drift (this step surfaces it, doesn't correct it)
- Tracing where in the pipeline drift was introduced (that's RCA's job)
- Judging plan quality (that's self_audit's job)
- Comparing multiple plans against each other
