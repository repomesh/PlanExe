# `compress_report_section` premortem failure — analysis (2026-05-17)

## Symptom

Running `prepare_extract_input.py` against
`/Users/neoneye/git/PlanExe-web/20251110_4DWW_India` with the default LLM
(`openrouter-gemini-2.5-flash-lite-preview-09-2025`) fails to produce
`compress_premortem.md`. The driver logs:

```
ERROR __main__ [premortem] GIVE UP after 3 attempts. Last error:
  Bucket 'gates_and_thresholds' failed after 3 attempts. Last error:
  ValidationError: 1 validation error for GatesAndThresholdsOnly
  Invalid JSON: trailing characters at line 1 column 413
  [type=json_invalid, input_value='{"line_english":"If SME ...0% across all cohorts"}', input_type=str]
WARNING: compressed section 'premortem' not produced; skipping
```

Two consecutive runs reproduced the failure. The other three compressed
sections (`selected_scenario`, `review_plan`, `expert_criticism`) emitted
clean output on the same runs.

## Failure pattern from the logs

Inside the premortem section the driver retried twice (six bucket attempts
total per outer attempt × three outer attempts = 18 LLM calls), and the
buckets that failed were always the same two:

| Outer attempt | First failing bucket | Trailing-character column |
|---:|---|---:|
| 1 | `gates_and_thresholds` | 366, 366, 413 |
| 2 | `numeric_values`        | 434, 443, line 8 col 4 |
| 3 | `gates_and_thresholds` | 498, 425, 413 |

Every failure is the same pydantic verdict —
`Invalid JSON: trailing characters at line N column M` — and the captured
`input_value` always starts with a valid-looking `{"line_english": "..."`.
The model is emitting a syntactically valid JSON object, then continuing
with extra characters that break the strict single-object schema validator.

The other compressed sections hit isolated retries on the same buckets
(notably the small-model `Could not extract json string from output`
fallback on `section_summary`) but recovered within three attempts. Only
premortem exhausts the budget.

## Why premortem specifically

The premortem source has more compress-resistant structure than the other
three sections:

- **More entities to fit in one bucket.** The source defines 9 assumptions
  (A1–A9) plus 9 failure modes (FM1–FM9) with 5×5 risk-level tuples; the
  `gates_and_thresholds` bucket has to triage these into ≤8 items, each
  with a quoted source string and per-field metadata.
- **Multi-clause if/then sentences.** Premortem rows nest a binding
  condition, a stakeholder, and a consequence in one sentence (e.g. A1
  "agree to a binding PMO casting vote *despite political pressures*").
  The bucket prompt asks for one-line `If <failure>, then <consequence>`
  rewrites — the model often glues two well-formed JSON objects together
  trying to keep both halves.
- **Quote-rich source.** Assumption text contains single quotes, em-dashes,
  parenthetical asides, and embedded percentages; structured-output models
  occasionally close one object and start another instead of escaping
  properly.

Other sections that share the same multi-bucket schema do not have this
combination, so the failure does not surface there.

## Root-cause hypothesis

The default LLM is a small Gemini Flash Lite preview that already produces
trailing-character noise on the other sections (recoverable within three
retries). Premortem content pushes the noise rate above the retry budget.
The proximate cause is not the source text — it is the model's tendency to
emit `{...}` then continue writing instead of stopping, combined with a
strict single-object validator that refuses to take the prefix.

## Is it fixable?

Yes, at three levels. From cheapest to deepest:

1. **Post-process the raw response before pydantic parses it.** Strip
   anything after the first balanced JSON object using a brace counter,
   then hand the prefix to the validator. The model already produces a
   valid prefix; the validator just refuses the suffix. This is a small
   patch in `compress_report_section.py` — wrap the `sllm.chat` call so
   trailing characters are trimmed before `chat_response.raw` is read.
   Risk: low. Removes the specific failure mode without changing prompts
   or models.

2. **Tighten the bucket prompts.** Add one explicit guardrail line to
   `GATES_AND_THRESHOLDS_BUCKET_PROMPT` and `NUMERIC_VALUES_BUCKET_PROMPT`
   (and the others) saying: *"Emit one JSON object and stop. Do not append
   any prose, code fence, or second object."* Small models often respect
   that line when it appears late in the prompt. Risk: low. Does not fix
   the underlying brittleness, but reduces the failure rate.

3. **Raise the model floor for compress_report_section.** Override
   `COMPRESS_FULL_LLM` to a model whose structured-output handler is more
   disciplined (`openrouter-gemini-2.0-flash-001`,
   `openrouter-openai-gpt-4o-mini`, or higher). The script already
   supports this via env var. Costs more per run but eliminates the
   single-section gap.

The right combination for production is probably (1) + (2): the trimmer
removes the known failure mode regardless of which model is in use, and
the prompt guardrail shrinks the population of failures the trimmer has to
handle. (3) becomes a fallback for plans where (1) and (2) still leave a
section uncompressed.

## Operational note for this plan

For `20251110_4DWW_India`, the bundled digest currently lacks the
premortem section. The remaining seven sections (executive_summary,
project_plan, selected_scenario, assumptions, review_plan, expert_criticism,
data_collection) carry enough overlap that parameter extraction is still
useful; the cost is reduced signal on unmodelled existential gates that
premortem typically surfaces. If a third retry with the default model
still fails, escalating to option (3) above is the appropriate next step.
