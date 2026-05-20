# 141 — Source-preservation audit for the napkin_math pipeline

## Problem

The current extraction-stage discipline (no-dead-end-variables, threshold-pairing) verifies that every declared `key_value` connects to a downstream calculation. It does NOT verify that every signal stated in the source or carried forward from the prior baseline survives into the current output. Silent drops pass the audit because the absent variable was never declared in the first place.

Two failure modes observed during the v50 prompt-cleanup work:

1. **Source-stated threshold absent from output.** The plan names a floor / cap / target the extractor recognises but does not surface in `key_values` or `missing_values_to_estimate`, and does not record the drop. Downstream stages cannot test the gate; the user has no signal that the gate was even considered.
2. **Prior-baseline signal absent from current version.** A variable / calculation / unmodelled-gate present in v49 disappears in v50 without explanation. The change may be a structural improvement (replaced by a better-named or better-decomposed equivalent) or a silent regression. The depends-on audit cannot tell the difference.

Both modes are invisible to the existing audit and to chat-level reporting that focuses only on what the current artifact contains.

## Goal

Every signal the source or prior baseline names as load-bearing must be **either** carried forward into the current output **or** explicitly recorded in a `dropped_signals` field with a structural rationale (`replaced_by:<id>`, `cap_pressure`, `out_of_scope`, `unmodelled_external`, `redundant_with:<id>`, …). The audit fails when an unjustified drop is detected.

The rule is corpus-agnostic. It applies to any plan in any domain.

## Two forks of the audit

### Fork A — Source / digest → current artifact

Reads the source digest (`extract_parameters_input.md` or the equivalent raw report). Identifies threshold-like claims by structural pattern (numeric values paired with comparison words: "at least", "no more than", "minimum", "maximum", "must clear", "if X exceeds Y", etc.). For each claim, checks whether the current artifact references it via a `key_value`, `missing_values_to_estimate`, formula RHS, or `unmodelled_gates` entry, or records it in `dropped_signals`.

### Fork B — Prior baseline → current artifact

Reads the prior-version artifact (e.g. v49 `parameters.json`) and the current-version artifact. Computes the full prior signal set: every `id` across `key_values`, `missing_values_to_estimate`, `derived_questions`, `recommended_first_calculations`, `unmodelled_gates`. For each prior id, checks whether the current artifact carries an equivalent (same id, or referenced via `dropped_signals` with `replaced_by:<current_id>`).

Both forks share the same `dropped_signals` schema. They are orthogonal sources of evidence about completeness: Fork A protects against silent omissions of source-named claims; Fork B protects against silent regressions on the verification corpus.

## Schema extension

The extract-stage artifact schemas (currently the JSON shape at the end of `extract-parameters-from-digest/system-prompt.txt` and the parallel `extract-parameters-from-full`) gain an optional top-level field:

```jsonc
"dropped_signals": [
  {
    "id": "<snake_case id of the dropped signal>",
    "source_anchor": "<source section or 'prior_baseline'>",
    "dropped_from": "<key_values | missing_values_to_estimate | recommended_first_calculations | derived_questions | unmodelled_gates>",
    "reason": "<one of: replaced_by:<new_id> | cap_pressure | out_of_scope | unmodelled_external | redundant_with:<other_id>>",
    "rationale": "<one-sentence structural justification (≤25 words)>"
  }
]
```

Hard limit: at most 8 entries. If more than 8 source/prior signals must be dropped, that itself is a structural problem to surface, not a list to inflate.

Allowed `reason` values are a closed enumeration so the audit script can mechanically classify each drop. The `rationale` field is for human readers and must restate the reason in plan-neutral terms.

## System-prompt rule additions

Inserted into the extract skill's `system-prompt.txt` between the existing "Threshold pairing rule" and "Combined viability gate preservation" sections:

```text
Source preservation rule:

Every threshold-like claim the source states (a floor, cap, ceiling,
minimum, maximum, target, deadline, or stated pass/fail condition)
must either appear in the current artifact (as a key_value,
missing_values_to_estimate, formula input, or unmodelled_gates
entry) OR be recorded in dropped_signals with a structural rationale.
Silent omission is not allowed.

The same rule applies to prior-baseline signals when the extract is
being run as part of an evaluation iteration. Every id present in
the prior baseline must either carry forward (same id, or replaced
by a new id explicitly named via reason='replaced_by:<new_id>') or
be recorded in dropped_signals.

Allowed reasons for a drop:
- replaced_by:<id>     — superseded by a structurally equivalent
                         current entry with a different id
- cap_pressure         — the hard limit on key_values, missing,
                         calcs, or derived_questions forced this
                         drop; the dropped signal is the
                         least-load-bearing per a stated criterion
- out_of_scope         — the signal exists in the source but the
                         current modelling frame does not cover it;
                         must say what scope decision excluded it
- unmodelled_external  — the signal is binary and depends on an
                         external actor; belongs in unmodelled_gates
                         but cannot be simulated
- redundant_with:<id>  — the signal is structurally equivalent to
                         another already-declared current entry

Do not use dropped_signals as a confession of laziness. Every drop
must have a structural reason a future reader can defend.
```

## Deterministic audit script

A new Python script, `experiments/napkin_math/audit_source_preservation.py`. No LLM call. Inputs:

- `--digest` — path to `extract_parameters_input.md`
- `--parameters` — path to the current `parameters.json`
- `--prior` — optional path to the prior baseline `parameters.json` (for Fork B)
- `--strict` — if set, exits non-zero on any unjustified drop

Behaviour:

1. **Fork A scan.** Regex over the digest's compressed-section bullets for threshold patterns (numeric value with one of: "minimum", "maximum", "floor", "ceiling", "cap", "must be at least", "must not exceed", "if X exceeds", "if X falls below"). For each detected claim, compute a stable claim-hash and look it up against the current artifact's id pool and `dropped_signals` array. Unreferenced claims are flagged.
2. **Fork B comparison.** Diff the prior artifact's id set against the current artifact's id set. Each prior-only id must appear in the current `dropped_signals` (matched by `id`) or be flagged as a silent regression.
3. **Report.** Plain-text output listing unjustified drops with section anchors. Exit code 0 if clean (or `--strict` not set), 1 otherwise.

The regex over threshold patterns is intentionally lossy — it will miss claims phrased in unusual ways and will sometimes false-positive. The goal is not perfect coverage; it is to surface silent drops that any reasonable extractor would have spotted. False positives are cheaper than silent regressions.

## Pipeline integration

The audit runs after `extract-parameters-from-digest` (or `extract-parameters-from-full`) and before `validate-parameters`. It is advisory — failures emit a report but do not block the downstream pipeline unless `--strict` is passed.

`run-napkin-math-pipeline` documentation gains a note that the audit step exists. The orchestrator skill is not modified in this PR; the audit is invoked manually until the orchestrator is updated separately.

## What this proposal does NOT do

- Does not add Fork A coverage at the compress stage. The compress LLM legitimately drops content from the source by design (compression). Auditing compress preservation is a separate problem with different shape.
- Does not add Fork A coverage at downstream stages (`generate-bounds`, `monte-carlo`, etc.). Most of those stages are deterministic Python; preservation there is a code property, not an LLM-output property.
- Does not address compress-LLM run-to-run variance. That is a separate orchestration problem.
- Does not enforce strict mode in CI. The audit lands as advisory only; making it gating is a follow-up policy decision.
- Does not retro-edit existing v50 `parameters.json` outputs. Those are gitignored. Re-running the extract under the new prompt rule will produce compliant outputs naturally.

## Acceptance for this proposal

- [ ] `dropped_signals` schema field documented in the extract system prompts
- [ ] Source-preservation rule added to both extract skill system prompts
- [ ] `audit_source_preservation.py` lands under `experiments/napkin_math/` with a small test suite covering the threshold-pattern regex and the prior-baseline diff logic
- [ ] One regression run against an existing v50 output that demonstrates the audit catches a previously-silent drop (the Mars `registration_volume_buffer_fraction` drop is the natural fixture)
- [ ] Discipline change reflected in `OPTIMIZE_INSTRUCTIONS` blocks if the rule has implications for the compress prompts (most likely not, but check)
- [ ] No corpus literals introduced in the prompt edits or the proposal text

## Open questions

- Should the audit emit a machine-readable report (`audit_source_preservation.json`) alongside the human-readable one, for use by downstream Self-Improve runs? Probably yes, defer to implementation.
- Should `cap_pressure` drops require naming the cap (`cap_pressure:key_values` vs `cap_pressure:missing_values_to_estimate`)? Yes, but the closed-enumeration mechanism above doesn't naturally express that. Either widen the enumeration or add a `cap_kind` subfield.
- The threshold-pattern regex needs a multilingual variant for non-English plans. Punt to a follow-up; the napkin_math baseline is currently English-only.
- When Fork B's prior baseline is missing (no v49 exists for this plan), Fork B is skipped. The audit reports "Fork B skipped: no prior baseline" rather than erroring.
- Should `dropped_signals` itself be capped lower than 8 to discourage drift? Maybe 5. Defer to implementation feedback.
