---
title: TaskItem Activity Log Decomposition and Secure Downloads
date: 2026-02-18
status: completed
author: PlanExe Team
---

# TaskItem Activity Log Decomposition and Secure Downloads

**Author:** PlanExe Team  
**Date:** 2026-02-18  
**Status:** Completed (implemented on 2026-02-18)  
**Tags:** `taskitem`, `security`, `performance`, `mcp`, `cost-visibility`

---

## Pitch
Move `track_activity.jsonl` out of `run_zip_snapshot` and store it as an internal `TaskItem` field so we stop repeatedly unzipping/re-zipping large artifacts on download, while preventing accidental exposure of provider API keys.

## Problem
Current behavior couples two very different payloads inside one zip snapshot:

- `activity_overview.json` (small, user-facing, cost/token summary)
- `track_activity.jsonl` (large, internal, sensitive event log)

This causes operational and security issues:

- The server repeatedly performs unzip -> remove `track_activity.jsonl` -> recompress before user download.
- `track_activity.jsonl` is typically 16-40 MB, creating avoidable CPU, memory, and latency overhead.
- `track_activity.jsonl` includes provider secrets (for example OpenRouter keys) and must never be downloadable by end users.
- MCP and UI still require token/cost visibility from `activity_overview.json`, so we cannot remove all activity artifacts.

## Feasibility
This is feasible with an incremental migration and backward compatibility:

- Add new internal storage fields to `TaskItem` for activity logs.
- Keep `run_zip_snapshot` contract unchanged for user download, except it no longer contains `track_activity.jsonl`.
- Populate new fields for new runs immediately.
- Backfill old runs lazily (on first internal access) or with a one-time migration job.

Potential constraints:

- Database size growth if raw JSONL is stored directly in a text column.
- Some historical snapshots may have malformed zip contents and need defensive parsing.
- Existing MCP/UI code paths may assume both files are in zip.

## Proposal
Split storage responsibilities by audience and sensitivity.

### 1) Data model changes
Add internal fields on `TaskItem`:

- `run_track_activity_jsonl` (`TEXT` or large-object reference): internal-only log payload.
- `run_track_activity_bytes` (`INT`): original byte size for observability.
- `run_activity_overview_json` (`JSON`): normalized summary used by MCP/UI.
- `run_artifact_layout_version` (`INT`): schema version to track migration state.

If row-size pressure becomes an issue, store `run_track_activity_jsonl` in private object storage and keep only a reference on `TaskItem`.

### 2) Artifact writing path
At run finalization:

1. Parse and persist `track_activity.jsonl` to `TaskItem.run_track_activity_jsonl`.
2. Parse and persist `activity_overview.json` to `TaskItem.run_activity_overview_json`.
3. Build `run_zip_snapshot` without `track_activity.jsonl`.

### 3) Download behavior
For user-facing download endpoints (MCP + `home.planexe.org/plan`):

- Serve `run_zip_snapshot` directly.
- Remove all unzip/sanitize/recompress logic.

Result: no sensitive-log stripping at request time because sensitive log is never in the downloadable artifact.

### 4) API behavior
Expose cost/token information from `run_activity_overview_json`:

- `input_tokens` and `output_tokens` by model.
- Optional provider-reported cost per inference call when present.
- Explicit null/unknown handling for providers that do not return costs.

Do not expose `run_track_activity_jsonl` on user-facing APIs.

### 5) Access control
Restrict `run_track_activity_jsonl` to trusted internal roles only (server/admin/debug paths).  
Add explicit serializer denylist to prevent accidental exposure in generic `TaskItem` JSON serialization.

### 6) Migration plan

1. **Phase A (write-new/read-old):** new runs write split fields; reads still support legacy zip extraction fallback.
2. **Phase B (backfill):** batch job extracts historical logs once and writes fields.
3. **Phase C (cutover):** remove fallback extraction and delete runtime recompression flow.
4. **Phase D (hardening):** add alerts/tests to ensure downloadable zip never includes `track_activity.jsonl`.

## Integration Points
- Task pipeline finalization where `run_zip_snapshot` is currently assembled.
- MCP endpoints that expose run cost/token summaries.
- `home.planexe.org/plan` download endpoint and cost panels.
- Admin/internal debugging tools that rely on full activity traces.

## Success Metrics
- 0 user-download responses requiring unzip/recompress sanitization.
- 0 incidents of `track_activity.jsonl` exposure to end users.
- P95 artifact-download latency reduced (target: at least 30% improvement).
- Reduced CPU time on download endpoint (target: at least 50% reduction for large artifacts).
- 100% MCP/UI cost panels served from `run_activity_overview_json` without zip extraction.

## Risks
- Storing large JSONL directly in DB can increase storage and replication costs.
- Incomplete migration could cause mixed behavior across old/new tasks.
- Internal tooling might rely on old zip layout and break during transition.

Mitigations:

- Prefer object storage reference if DB bloat exceeds threshold.
- Ship feature-flagged rollout with dual-read until migration completion.
- Add contract tests for artifact contents and API serialization.

## Implementation Notes
- Treat `track_activity.jsonl` as sensitive by default and never include it in user-export bundles.
- Keep `activity_overview` as the canonical user-facing cost source.
- Add automated regression test: unzip any downloadable snapshot and assert `track_activity.jsonl` is absent.

## Completed Implementation (2026-02-18)
Implemented code paths:

- New `TaskItem` fields added and wired:
  - `run_track_activity_jsonl`
  - `run_track_activity_bytes`
  - `run_activity_overview_json`
  - `run_artifact_layout_version`
- Worker finalization now writes split activity fields and builds `run_zip_snapshot` without `track_activity.jsonl`.
- `frontend_multi_user` and `mcp_cloud` download paths now serve new-layout zips directly and only sanitize legacy snapshots.
- `worker_plan` zip endpoint now excludes `track_activity.jsonl`.
- UI telemetry/cost views now read `run_activity_overview_json` first, with legacy zip fallback.
- Admin tooling exposes internal track-activity download in an admin-only endpoint.

This completes the operational objective of removing unzip/recompress work for new runs while preserving backward compatibility for legacy runs.

## Issues Encountered and Resolutions
1. Retry path kept stale artifact fields
- Issue: `/plan/retry` cleared `generated_report_html` and `run_zip_snapshot` but initially left new split fields populated.
- Impact: stale telemetry/cost/internal activity metadata could appear until rerun completion.
- Resolution: updated retry reset to also clear `run_track_activity_jsonl`, `run_track_activity_bytes`, `run_activity_overview_json`, and `run_artifact_layout_version`.

2. Existing AGENTS guidance conflicted with new design
- Issue: root guidance still mandated runtime sanitization of `run_zip_snapshot` for all downloads.
- Impact: this contradicted the completed split-artifact model where new snapshots are already safe.
- Resolution: updated AGENTS guidance to enforce: never include `track_activity.jsonl` when creating downloadable zips; sanitize legacy snapshots only.

3. Security invariant lacked explicit regression coverage
- Issue: tests covered metadata/download flow but did not explicitly assert stripping of `track_activity.jsonl`.
- Resolution: added regression tests for both frontend legacy-zip sanitization and MCP legacy-zip sanitization to ensure `track_activity.jsonl` is absent from downloadable artifacts.

## Remaining Work (Optional)
- Phase B backfill job is still optional operational work: historical tasks can be migrated from zip-only storage into split fields to reduce fallback usage.
- Phase C hard cutover (removing fallback sanitization entirely) can be done after backfill confidence is high.
