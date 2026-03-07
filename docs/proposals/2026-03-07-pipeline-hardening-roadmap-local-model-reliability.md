# Pipeline Hardening Roadmap for Local-Model Reliability

Date: 2026-03-07  
Author: EgonBot  
Reviewers: neoneye, Bubba

## 1) Executive summary

This proposal defines a practical roadmap to make PlanExe’s pipeline significantly more reliable when using local models (LM Studio/Ollama class), while preserving correctness and auditability.

Recent runs show a consistent pattern: once one truncation gate is fixed, the next schema-heavy task becomes the new failure point. The system is not failing randomly; it is exposing deterministic weak points where strict structured output meets long responses, multi-part schemas, and repeated LLM calls.

The roadmap below focuses on:
1. **Containment now** (small safe patches that unblock progress),
2. **Resilience next** (better retry + diagnostics),
3. **Reliability controls** (preflight gates and profile-based execution),
4. **Long-term governance** (benchmarks and model scorecards).

The key rule throughout: **no mega-PRs**. One failure mode per PR, with explicit evidence.

---

## 2) Problem statement and observed failure chain

### 2.1 What we have observed in real runs

Across recent local runs:
- `SelectScenarioTask` failed on missing trailing required fields; raising `num_output` improved it.
- Later, `PreProjectAssessmentTask` failed on missing tail fields in `ExpertDetails` (`combined_summary`, `go_no_go_recommendation`).
- Historical testing identified `CreateWBSLevel3Task` as a high-amplification gate due to repeated schema-constrained generations.
- Separate CLI path produced `KeyError: 'server_iso_utc'`, which is an engineering bug (not model behavior).

### 2.2 Why this matters

This failure pattern creates three costs:
- **Operational cost:** long runs die late, leaving many blocked downstream tasks.
- **Token cost:** retries repeat with limited new information, burning budget.
- **Engineering cost:** oversized mixed-scope PRs become hard to review/merge.

### 2.3 Root-cause categories

Current failures largely cluster into:
1. **Output truncation** (missing tail fields),
2. **Schema/type drift** (wrong primitive/list/object type),
3. **Schema-echo responses** (model restates structure instead of filling values),
4. **Code-path assumptions** (hard key lookups in non-API paths).

---

## 3) Design principles for hardening

1. **Safety over convenience:** defaults are only allowed for low-risk summary fields, never core decision fields without explicit warning.
2. **Determinism over guessing:** each retry should include concrete validation feedback, not blind repetition.
3. **Small PR discipline:** split by failure mode; avoid combined refactor + bugfix bundles.
4. **Evidence-first merges:** every patch should include run evidence (task advanced, error signature changed, or failure eliminated).
5. **No silent corruption:** if defaults are used, emit telemetry and trace markers.

---

## 4) Roadmap

## Phase 0 — Immediate containment (same day)

Objective: stop known crashes and unblock forward movement with minimal-risk edits.

### Actions

1. **Merge tiny unblocker patches only**
   - Keep PR scope to one defect class.
   - Enforce explicit file-count and diff-size checks before merge.

2. **Harden known truncation points with safe defaults**
   - `SelectScenarioTask`: default low-risk trailing summary field(s).
   - `PreProjectAssessmentTask`: default `combined_summary` and `go_no_go_recommendation` with warning markers (empty string sentinel acceptable as first unblock).

3. **Fix deterministic code bug in scheduling path**
   - Replace hard `start_time_dict['server_iso_utc']` access with safe `.get('server_iso_utc', '')`.

4. **Confirm baseline local config sanity**
   - `is_function_calling_model: false` for LM Studio local adapters.
   - `num_output` sized for schema-heavy tasks.
   - structured response enforcement kept where supported.

### Exit criteria
- Pipeline resumes and advances beyond `PreProjectAssessmentTask`.
- No recurrence of `server_iso_utc` crash in CLI path.
- All containment PRs remain small and independently reviewable.

---

## Phase 1 — Structured-output resilience (1–3 days)

Objective: improve recovery from predictable validation failures without hiding true model weaknesses.

### 1.1 Failure-intelligent retry path

Current retries often repeat the same prompt/context and predictably fail again. Upgrade retries to include compact, model-readable error context:
- schema name,
- missing fields,
- invalid types,
- short corrective instruction (regenerate only invalid portions).

### 1.2 Attempt-level diagnostics

For each failed parse, persist:
- raw output sample (truncated safely for logs),
- missing/invalid field map,
- attempt index,
- token metrics snapshot,
- model + config profile used.

This enables precise postmortems and model comparison.

### 1.3 Field strictness policy

Introduce explicit categories:
- **Hard-required semantic fields:** no silent defaults.
- **Soft-required synthesis fields:** defaults allowed with warning + trace.

This balances reliability with data integrity.

### Exit criteria
- Retry success rate for truncation/type cases improves over baseline.
- Failure classification is explicit in logs (truncation vs type drift vs schema echo).
- No increase in silent low-quality outputs.

---

## Phase 2 — Pipeline-level reliability controls (3–7 days)

Objective: reduce expensive full-run failures by failing fast when model/profile is unsuitable.

### 2.1 Local Reliability Profile

Define a documented profile that ties together:
- approved local models,
- context/output defaults,
- retry strategy,
- per-task strictness.

This converts ad-hoc tuning into repeatable operations.

### 2.2 Preflight smoke gates

Before full pipeline execution, run a minimal structured-output smoke suite:
1. scenario selection parse,
2. expert assessment parse,
3. one WBS details parse.

If smoke gate fails, halt early with prescriptive next actions (config adjustment/model switch/strictness notes).

### 2.3 Blast-radius prioritization

Prioritize hardening by dependency impact and call amplification:
1. `PreProjectAssessmentTask`,
2. `CreateWBSLevel3Task`,
3. `EstimateTaskDurationsTask`.

### Exit criteria
- Fewer late-stage catastrophic run failures.
- Higher Luigi resume efficiency (fewer repeated crash points).
- Lower token burn per successful completed pipeline.

---

## Phase 3 — Reliability governance and benchmarking (1–2 weeks)

Objective: institutionalize learning so gains persist across models and contributors.

### 3.1 Regression corpus from real failures

Build a benchmark set for:
- tail-field truncation,
- schema echoing,
- primitive type confusion,
- nested JSON/list truncation.

### 3.2 Model scorecard

Track per model/profile:
- first failure task,
- task-level pass rate,
- retry recovery rate,
- token cost to completion.

Use this to maintain recommended default local profiles.

### 3.3 Docs and operational runbooks

Update docs with:
- known-good local profiles,
- known failure signatures and remediations,
- preflight protocol,
- troubleshooting decision tree.

### Exit criteria
- New local model candidates can be screened predictably.
- Operations team has stable runbook-driven behavior.

---

## 5) Implementation plan (PR sequencing)

1. Tiny PR: `SelectScenarioTask` truncation resilience (if not already merged).  
2. Tiny PR: `CreateScheduleTask` key access fix (if not already merged).  
3. Tiny PR: `PreProjectAssessmentTask` tail-field resilience.  
4. Small PR: failure-intelligent retries in LLM executor.  
5. Small PR: preflight smoke gate and local reliability profile docs.  
6. Follow-up docs PR: benchmark + scorecard framework.

Each PR must include:
- exact scope statement,
- evidence from resumed run,
- rollback note,
- explicit non-goals.

---

## 6) Risks and trade-offs

### Risk A: Over-defaulting hides model quality issues
Mitigation: defaults only for soft synthesis fields + warning traces.

### Risk B: Retry logic increases complexity
Mitigation: add in small increments, with isolated tests and telemetry.

### Risk C: Profile divergence across contributors
Mitigation: central local reliability profile and docs-first process.

### Risk D: Token cost rises with diagnostics
Mitigation: compact error prompts, bounded log size, and preflight gating to avoid doomed full runs.

---

## 7) Success metrics

Primary metrics:
- completion rate of full local runs,
- first-failure task moves deeper or disappears,
- reduced repeated failures at same task after resume,
- reduced token cost per successful completion.

Secondary metrics:
- average PR size (files/LOC) for reliability patches,
- mean time from failure report to merged fix,
- number of merges reverted due to scope creep.

---

## 8) Decision request

Approve this phased roadmap and execute it as a sequence of small, evidence-backed PRs.

Immediate next step after approval: merge/prepare the single-purpose `PreProjectAssessmentTask` resilience patch and validate via Luigi resume that the pipeline clears that gate.
