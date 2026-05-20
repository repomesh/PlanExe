---
title: "Source-Preservation Audit for the Napkin Math Pipeline"
date: 2026-05-21
status: Proposal
author: PlanExe Team
---

# Source-Preservation Audit for the Napkin Math Pipeline

**Author:** PlanExe Team
**Date:** 2026-05-21
**Status:** Proposal
**Tags:** `napkin-math`, `validation`, `audit`, `parameters`, `llm-output`

---

## Pitch

Add a deterministic source-preservation audit between parameter extraction and validation so load-bearing source signals cannot silently disappear. Every threshold-like source claim or prior-baseline signal must either be carried forward into the current `parameters.json` or be recorded in `dropped_signals` with a mechanically checkable structural reason.

## Problem

The current extraction-stage discipline verifies that every declared `key_value` connects to a downstream calculation. It does not verify that every signal stated in the source or carried forward from the prior baseline survives into the current output. Silent drops pass the audit because the absent variable was never declared in the first place.

Two failure modes motivated this proposal:

1. **Source-stated threshold absent from output** — the source names a floor, cap, target, deadline, or pass/fail condition, but the extractor does not surface it in `key_values`, `missing_values_to_estimate`, a formula input, or `unmodelled_gates`.
2. **Prior-baseline signal absent from current output** — a variable, calculation, or unmodelled gate present in a prior artifact disappears without an explicit replacement or rationale.

Both modes are invisible to the existing no-dead-end-variable audit and to reporting that only describes what the current artifact contains.

## Feasibility

The audit is feasible as an advisory deterministic script because `parameters.json` already has stable IDs, labels, formulas, dependencies, and source anchors. The source-side scan is less precise: it must infer threshold-like claims from compressed digest text, so it will produce false positives and miss unusual phrasing. That is acceptable for an advisory first phase, but strict CI gating should wait until the matching fields and false-positive rate are proven on the full napkin_math corpus.

The implementation should avoid adding plan-specific literals to prompts. Regression plans are probes only; tests should use synthetic fixtures for unit coverage and optionally run real corpus probes as non-normative integration checks.

## Proposal

Build two orthogonal audit forks that share one `dropped_signals` schema.

### Fork A: Source Digest To Current Artifact

Reads `extract_parameters_input.md` or the equivalent raw report input. It identifies threshold-like claims by structural pattern: numeric value plus language such as minimum, maximum, floor, ceiling, cap, target, deadline, must be at least, must not exceed, falls below, exceeds, or equivalent pass/fail phrasing.

For each detected source claim, the audit computes a deterministic `source_claim_id`:

```text
source_claim_id = "claim_" + sha1(normalized_source_anchor + "\n" + normalized_claim_text)[:12]
```

A source claim is considered preserved when at least one of these is true:

1. A current artifact entry declares that claim in `source_claim_ids`.
2. A current artifact entry has sufficient deterministic text overlap with the claim, using source anchor, numeric token, comparison token, and noun-token overlap.
3. A `dropped_signals` entry records the same `source_claim_id` with an allowed structural reason.

The explicit `source_claim_ids` field is the preferred long-term mechanism. Text overlap is a compatibility fallback for older outputs and should be reported as lower-confidence.

### Fork B: Prior Baseline To Current Artifact

Reads a prior `parameters.json` and the current `parameters.json`. It computes the prior signal set from every `id` and `output_name` across:

- `key_values`
- `missing_values_to_estimate`
- `recommended_first_calculations`
- `derived_questions`
- `unmodelled_gates`

A prior signal is considered preserved when at least one of these is true:

1. The same `id` or `output_name` appears in the current artifact.
2. A current formula depends on the prior signal name and the producer still exists under a compatible output name.
3. A `dropped_signals` entry records the prior signal with `reason: "replaced_by"` or `reason: "redundant_with"` and points to an existing current ID.
4. A `dropped_signals` entry records another allowed structural reason.

Fork A protects against omissions that the prior baseline also missed. Fork B protects against regressions relative to a known earlier artifact.

## Schema

The extract-stage schemas gain two optional additions.

First, any emitted entry may carry source-claim references:

```jsonc
"source_claim_ids": ["claim_ab12cd34ef56"]
```

Second, the top-level artifact may include `dropped_signals`:

```jsonc
"dropped_signals": [
  {
    "id": "prior_or_claim_id",
    "origin": "source_digest",
    "source_claim_id": "claim_ab12cd34ef56",
    "source_anchor": "review_plan",
    "expected_section": "key_values",
    "dropped_from": null,
    "reason": "replaced_by",
    "replacement_id": "current_signal_id",
    "redundant_with_id": null,
    "cap_kind": null,
    "rationale": "Equivalent threshold is represented by a clearer current margin input."
  }
]
```

Field semantics:

- `id` is the prior signal ID for Fork B, or the `source_claim_id` for Fork A.
- `origin` is one of `source_digest` or `prior_baseline`.
- `source_claim_id` is required when `origin == "source_digest"`.
- `source_anchor` names the source section when known; otherwise use `prior_baseline`.
- `expected_section` is the section where the signal would normally land.
- `dropped_from` is required only when `origin == "prior_baseline"` and names the prior section.
- `reason` is one of `replaced_by`, `cap_pressure`, `out_of_scope`, `moved_to_unmodelled_gate`, or `redundant_with`.
- `replacement_id` is required for `replaced_by` and must reference an existing current ID or output name.
- `redundant_with_id` is required for `redundant_with` and must reference an existing current ID or output name.
- `cap_kind` is required for `cap_pressure` and must name the capped array.
- `rationale` is a one-sentence structural justification, capped at 25 words.

Hard limit: at most 8 `dropped_signals`. If more than 8 signals must be dropped, the audit should surface an overflow finding instead of encouraging a long confession list.

## Validation Rules

The audit validates `dropped_signals` before trusting it:

1. `reason` must be in the closed enum.
2. `replacement_id` and `redundant_with_id` must reference existing current IDs or output names.
3. `cap_pressure` must name a capped array in `cap_kind`, and that array must actually be at its cap in the current artifact.
4. `moved_to_unmodelled_gate` must reference an existing `unmodelled_gates` entry through `replacement_id`.
5. `source_claim_id` values must match the deterministic `claim_<12 hex>` shape.
6. `rationale` must be non-empty, plan-neutral, and at most 25 words.

Malformed `dropped_signals` entries are audit failures. They should not be accepted as explanations.

## Prompt Rule

The extract prompts should gain a corpus-agnostic source-preservation rule:

```text
Source preservation rule:

Every threshold-like source claim must either appear in the current
artifact, be represented by a declared source_claim_id on a current
entry, or be recorded in dropped_signals with a structural reason.
Silent omission is not allowed.

When running an evaluation iteration with a prior baseline, every
prior-baseline signal must either carry forward, be replaced by a
current signal named in dropped_signals, or be recorded with another
allowed structural reason.

Do not use dropped_signals to excuse weak extraction. Each entry must
name a defensible structural reason and point to the current signal
when the signal was replaced, made redundant, or moved to unmodelled
gates.
```

The prompt must not mention corpus plan names, literal values, expected output IDs, or domain-specific probe details.

## Audit Script

Add `experiments/napkin_math/audit_source_preservation.py`. No LLM call.

Inputs:

- `--digest` — path to `extract_parameters_input.md`
- `--parameters` — path to the current `parameters.json`
- `--prior` — optional path to the prior baseline `parameters.json`
- `--report-json` — optional output path for a machine-readable report
- `--strict` — exit non-zero on unjustified drops

Behaviour:

1. Parse and validate the current artifact shape.
2. Scan the digest for threshold-like claims and compute `source_claim_id` values.
3. Build the current signal index from IDs, output names, labels, source text, formulas, dependencies, unmodelled gates, and `source_claim_ids`.
4. Run Fork A preservation checks.
5. If `--prior` is present, build the prior signal set and run Fork B checks.
6. Validate every `dropped_signals` explanation.
7. Emit a human-readable report and, when requested, a JSON report.

Exit code is 0 when clean, 1 when strict mode finds unjustified drops, and 2 for malformed input JSON.

## Integration

The audit runs after `extract-parameters-from-digest` or `extract-parameters-from-full` and before `validate-parameters`.

Initial integration should be advisory:

1. Manual invocation during prompt-development work.
2. Optional step documented in `run-napkin-math-pipeline`.
3. Later orchestrator integration that writes `audit_source_preservation.json` next to `parameters.json`.
4. Strict mode only after false positives are measured and reduced across the corpus.

The existing `validate_parameters.py` should stay focused on internal structural consistency. Source preservation is a separate audit because it needs external artifacts: the digest and optional prior baseline.

## What This Proposal Does Not Do

- It does not audit raw-source to compressed-digest preservation. Compression intentionally drops content, so that needs a separate design.
- It does not solve compress-LLM run-to-run variance.
- It does not make source preservation a CI gate in the first implementation.
- It does not retro-edit existing gitignored outputs.
- It does not require plan-specific prompt text or probe-specific rules.

## Implementation Phases

1. **Schema and docs** — document `source_claim_ids` and `dropped_signals` in both extract prompts and the napkin_math README.
2. **Advisory script** — implement the audit with synthetic unit fixtures for Fork A, Fork B, and malformed `dropped_signals`.
3. **Corpus probe run** — run against a subset of existing outputs and record false positives, false negatives, and useful catches.
4. **Pipeline note** — document manual invocation in the orchestrator skill without changing orchestration behaviour.
5. **Orchestrator integration** — write `audit_source_preservation.json` as a normal intermediate artifact.
6. **Strict policy decision** — decide whether any subset of findings should become blocking.

## Success Metrics

- Synthetic tests catch an omitted source threshold, a dropped prior missing value, a dropped prior derived question, and a malformed replacement reference.
- On corpus probes, every reported finding is classified as true positive, false positive, or accepted tradeoff.
- The audit catches at least one silent drop that the current no-dead-end-variable audit misses.
- False positives are low enough that reviewers can inspect them during prompt work without ignoring the report.
- No corpus literals are introduced into extract prompts.

## Risks

- **False positives from regex scanning** — mitigate with advisory rollout, source anchors, numeric-token checks, and `source_claim_ids`.
- **LLM overuses `dropped_signals`** — mitigate with hard caps, validation rules, and strict replacement references.
- **Prior baseline was wrong or incomplete** — mitigate by treating Fork B as regression evidence, not ground truth.
- **Schema bloat** — keep fields optional and local to napkin_math artifacts until the audit proves useful.
- **Multilingual blind spots** — start with English structural patterns and add multilingual phrase tables only after measuring misses.

## Acceptance

- [ ] Proposal follows `docs/proposals/AGENTS.md` formatting rules.
- [ ] `source_claim_ids` and `dropped_signals` are documented in both extract system prompts.
- [ ] `experiments/napkin_math/README.md` documents the new optional fields and audit workflow.
- [ ] `audit_source_preservation.py` lands under `experiments/napkin_math/`.
- [ ] Unit tests cover source-claim detection, prior-baseline diffing, malformed `dropped_signals`, cap-pressure validation, and replacement-ID validation.
- [ ] A synthetic regression fixture demonstrates a previously silent drop is caught.
- [ ] A corpus probe report is produced without adding corpus literals to prompts.

## Open Questions

- Should `source_claim_ids` be required on new extract outputs once the field is introduced, or remain optional until the matching fallback has enough data?
- Should strict mode ever apply to Fork A regex findings, or only to Fork B and explicit `source_claim_ids`?
- Should `dropped_signals` be capped at 8 or 5?
- Should the JSON report be consumed by Self-Improve as a prompt-optimization signal?
