# Extract Constraints from User Prompt

**Date:** 2026-04-03
**Status:** Approved

## Problem

PlanExe tends to pick up negative constraints from user prompts and incorporate them into the plan instead of avoiding them. For example, when a user writes "Banned words: AR/VR/NFT/blockchain", PlanExe may still reference those technologies. There is no stage that extracts and classifies user constraints for downstream consumption.

## Solution

A new early-pipeline stage that extracts all explicit constraints from the user's raw prompt and classifies each as **positive** (things the user wants) or **negative** (things the user wants to avoid). The output is a flat list of self-contained, bullet-point-ready constraint items that can be passed verbatim to downstream LLM stages as a checklist.

## Pydantic Models

```python
class ConstraintItem(BaseModel):
    classification: Literal["positive", "negative"]
    constraint_text: str  # Self-contained bullet-point item

class ConstraintExtractionResult(BaseModel):
    constraints: list[ConstraintItem]
```

## Dataclass

`ExtractConstraints` in `worker_plan_internal/diagnostics/extract_constraints.py`:

- Same pattern as `PhysicalLocations`: `system_prompt`, `user_prompt`, `response` dict, `metadata` dict, `markdown` string
- `execute(llm, user_prompt)` classmethod — single structured LLM call
- `convert_to_markdown()` — renders two sections: "Positive Constraints" and "Negative Constraints", each as a bullet list. Empty list produces "No constraints identified."
- `save_raw(file_path)` and `save_markdown(file_path)`

## System Prompt Behavior

The system prompt instructs the LLM to:

- Extract every constraint the user explicitly states — things they want (positive) and things they want to avoid (negative)
- Each `constraint_text` must be a short, self-contained bullet-point item that can be passed verbatim to another LLM as a checklist
- Positive constraints: goals, desired features, locations, budgets, timelines, audiences, technologies to use
- Negative constraints: banned words/technologies, things to avoid, non-goals, hard limits not to violate
- For comma-separated lists like "Banned words: AR/VR/NFT/blockchain", extract each item as a separate negative constraint
- If the prompt has no identifiable constraints, return an empty list
- Do not infer constraints that aren't explicitly stated — only extract what the user wrote

### Example

Input: *"Build a Minecraft themed escape-room in Copenhagen for kids aged 8-14. Budget: $200K. Timeline: 6 months. Banned words: AR/VR/NFT/blockchain."*

Output:
```json
{"constraints": [
  {"classification": "positive", "constraint_text": "Minecraft themed escape-room"},
  {"classification": "positive", "constraint_text": "Copenhagen"},
  {"classification": "positive", "constraint_text": "Kids aged 8-14"},
  {"classification": "positive", "constraint_text": "Budget: $200K"},
  {"classification": "positive", "constraint_text": "Timeline: 6 months"},
  {"classification": "negative", "constraint_text": "Do not use AR/VR"},
  {"classification": "negative", "constraint_text": "Do not use NFT"},
  {"classification": "negative", "constraint_text": "Do not use blockchain"}
]}
```

## Pipeline Stage

**Stage file:** `worker_plan_internal/plan/nodes/extract_constraints.py`

- `ExtractConstraintsTask` extends `PlanTask`
- `requires()` — depends on `SetupTask` only (reads the raw user prompt)
- `output()` — returns `raw` and `markdown` targeting FilenameEnum constants
- `run_with_llm(llm)` — reads user prompt, calls `ExtractConstraints.execute(llm, plan_prompt)`, writes both outputs

**FilenameEnum entries:**
```python
EXTRACT_CONSTRAINTS_RAW = "extract_constraints_raw.json"
EXTRACT_CONSTRAINTS_MARKDOWN = "extract_constraints.md"
```

**Pipeline registration** in `full_plan_pipeline.py`:
- Add `'extract_constraints': self.clone(ExtractConstraintsTask)` to `requires()`

**Report integration:**
- Add to `report.py` so constraints show up in the generated report

## Tests

**File:** `worker_plan_internal/diagnostics/tests/test_extract_constraints.py`

**Unit tests (no LLM):**
- `ConstraintItem` model validation — valid positive/negative classifications, invalid classification rejected
- `ConstraintExtractionResult` model — empty list, list with items, model_dump()
- `convert_to_markdown()` — positive-only, negative-only, mixed, empty list
- `ExtractConstraints` dataclass — `to_dict()` with/without metadata/prompts

**LLM integration tests (gated behind `RUN_LLM_TESTS=1`):**
- Test prompts from `simple_plan_prompts.jsonl` that have known negative constraints (Minecraft escape-room, HaaS, school system) — verify negative constraints are extracted
- Test a simple prompt like "Establish a solar farm in Denmark" — verify positive constraints are extracted
- Test response structure — verify all expected fields present

## Files to Create/Modify

**New files:**
- `worker_plan_internal/diagnostics/extract_constraints.py` — Pydantic models, dataclass, system prompt, execute()
- `worker_plan_internal/plan/nodes/extract_constraints.py` — PlanTask wrapper
- `worker_plan_internal/diagnostics/tests/test_extract_constraints.py` — unit + LLM integration tests

**Modified files:**
- `worker_plan_api/filenames.py` — add FilenameEnum entries
- `worker_plan_internal/plan/nodes/full_plan_pipeline.py` — register stage
- `worker_plan_internal/report/report_generator.py` — add to report
