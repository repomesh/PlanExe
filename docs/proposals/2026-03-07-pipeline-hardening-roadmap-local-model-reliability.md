# Pipeline Hardening Roadmap (Local Model Reliability)

Date: 2026-03-07  
Owner: EgonBot (with Bubba + neoneye validation)

## Why this proposal

Recent local-model runs show a repeatable failure pattern:
- `SelectScenarioTask` initially failed due to missing trailing required fields.
- After increasing output budget, it passed.
- `PreProjectAssessmentTask` then failed with missing trailing required fields (`combined_summary`, `go_no_go_recommendation`).
- Historical runs also show `CreateWBSLevel3Task` as a high-risk structured-output gate.

This indicates **pipeline fragility under partial/truncated JSON**, especially on large schemas and long outputs.

## Goal

Make PlanExe robust enough to complete full pipelines on capable local models (e.g., Qwen 35B class) without masking real quality problems.

---

## Roadmap

## Phase 0 — Immediate containment (same day)

### 0.1 Keep PRs tiny and mergeable
- Split unrelated fixes into separate PRs.
- Rule: one failure mode per PR.

### 0.2 Patch known hard failures with safe defaults
- `SelectScenarioTask`: default optional-safe trailing summary fields.
- `PreProjectAssessmentTask`: add safe defaults for
  - `combined_summary`
  - `go_no_go_recommendation`
- `CreateScheduleTask`: replace hard key lookup with safe `.get()` for `server_iso_utc` to avoid CLI crash.

### 0.3 Keep local config sane for structured output
- Use `num_output` high enough for large schemas (8192+ where needed).
- Keep `is_function_calling_model: false` for local LM Studio models.
- Keep JSON-structured response enforcement (`force_json`/`response_format`) where supported.

Success criteria:
- Pipeline advances beyond `PreProjectAssessmentTask` on resume.
- No `KeyError: server_iso_utc` in CLI path.

---

## Phase 1 — Structured output resilience without silent corruption (1–3 days)

### 1.1 Add model-output diagnostics per failed attempt
For each failed structured parse, store:
- raw model output,
- schema name,
- missing/invalid fields,
- retry attempt index,
- token metrics snapshot.

### 1.2 Add targeted retry policy
Current retries often repeat identical prompt/context. Improve by:
- feeding compact validation error hints into retry prompt,
- asking model to regenerate only missing/invalid fields,
- preserving already-valid fields when safe.

### 1.3 Add task-level strictness modes
- **Strict fields**: core semantic fields that must never default silently.
- **Soft fields**: summary/formatting fields allowed to default with warning.

Success criteria:
- Retries recover from truncation/type slips more often than baseline.
- Failures become easier to classify (truncation vs type drift vs schema echo).

---

## Phase 2 — Pipeline-level reliability controls (3–7 days)

### 2.1 Introduce a "Local Reliability Profile"
A documented profile that sets:
- model allowlist,
- context/output defaults,
- retry strategy,
- strictness policy per task.

### 2.2 Add preflight smoke gates
Before full run, execute a small set of schema-heavy checks:
- one scenario selection parse,
- one expert assessment parse,
- one WBS details parse.

If smoke fails, stop early with actionable guidance.

### 2.3 Failure impact reduction
Prioritize hardening for high-blast-radius tasks in topological order:
1. `PreProjectAssessmentTask`
2. `CreateWBSLevel3Task`
3. `EstimateTaskDurationsTask`

Success criteria:
- Fewer full-run failures caused by early schema crashes.
- Better Luigi resume efficiency due to fewer repeated stop points.

---

## Phase 3 — Long-term quality + governance (1–2 weeks)

### 3.1 Structured-output benchmark suite
Build regression cases from real failures:
- missing tail fields,
- schema echo outputs,
- wrong primitive types,
- nested array/object truncation.

### 3.2 Reliability scorecard per model
Track per-task pass rates and first-failure location for each model/config.
Use this to guide default local-model recommendations.

### 3.3 Documentation updates
Update provider docs with:
- known good configs,
- known failure signatures,
- preflight checklist,
- expected fallback behavior.

---

## Non-goals

- Hiding genuinely low-quality model outputs behind aggressive defaulting.
- Merging broad refactors together with urgent reliability patches.
- Claiming local-model parity with hosted frontier models without benchmark evidence.

## Proposed PR sequence

1. Tiny PR: `SelectScenarioTask` default-field resilience (if not merged yet).  
2. Tiny PR: `CreateScheduleTask` safe key access for CLI path.  
3. Tiny PR: `PreProjectAssessmentTask` missing-tail-field resilience.  
4. Follow-up PR: retry/error-context improvements in llm executor.  
5. Docs PR: local reliability profile + smoke gate docs.

## Decision request

Approve this phased roadmap and execute in small PRs, each with explicit pass/fail evidence from a resumed pipeline run.
