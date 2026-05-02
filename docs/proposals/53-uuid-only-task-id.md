---
title: "UUID-only task_id: remove timestamp-style run IDs"
date: 2026-02-13
status: proposal
author: PlanExe
---

# UUID-only task_id: remove timestamp-style run IDs

**Status:** Proposal  
**Date:** 2026-02-13  
**Audience:** Core backend + frontend maintainers

---

## Overview

PlanExe currently uses two ID styles for executions:

- Timestamp-style: `PlanExe_19841231_195936`
- UUID-style: `920da16e-f1fa-4ed6-bd5f-882d50950bec`

This proposal standardizes on **UUID only** and removes generation/support for the timestamp-style ID.

---

## Why change

Mixed ID formats create ambiguity and extra branching in code paths, tests, and docs. UUID-only identifiers are simpler, globally unique, and already align with `TaskItem.id` semantics in multi-user flows.

---

## Decision

1. New execution IDs are always UUIDs.
2. Stop generating `PlanExe_YYYYMMDD_HHMMSS` IDs.
3. Remove toggles that choose between timestamp vs UUID.
4. Keep route parameter name compatibility (`run_id`) only where needed for now, but value format is UUID.

---

## Required code changes

## 1) ID generation (source of truth)

### `/Users/neoneye/git/PlanExeGroup/PlanExe/worker_plan/worker_plan_api/generate_run_id.py`

- Remove `RUN_ID_PREFIX = "PlanExe_"` dependency for run creation.
- Change `generate_run_id(...)` to always return a plain UUID string.
- Remove the timestamp branch and `use_uuid` switch behavior.
- Update function docstring to describe UUID-only behavior.

### `/Users/neoneye/git/PlanExeGroup/PlanExe/worker_plan/worker_plan_api/tests/test_generate_run_id.py`

- Remove timestamp-format test (`test_generate_run_id_timestamp`).
- Update UUID test to validate plain UUID format (no `RUN_ID_PREFIX` expectations).

---

## 2) Worker API request model and run creation

### `/Users/neoneye/git/PlanExeGroup/PlanExe/worker_plan/app.py`

- In `StartRunRequest`, remove `use_uuid_as_run_id`.
- In `create_run_directory`, call UUID-only `generate_run_id(...)`.
- Keep existing `/runs/...` endpoints if desired for transport compatibility, but all returned IDs are UUIDs.
- Review purge defaults that currently use `RUN_ID_PREFIX` and switch to UUID-safe behavior.

---

## 3) Frontend multi user cleanup

### `/Users/neoneye/git/PlanExeGroup/PlanExe/frontend_multi_user/src/app.py`

- Remove unused `Config.use_uuid_as_run_id` and any dead references.
- Verify all references to task execution identifiers assume UUID-only values.

---

## 4) Purge behavior and old assumptions

### `/Users/neoneye/git/PlanExeGroup/PlanExe/worker_plan/worker_plan_internal/utils/purge_old_runs.py`

- Current purge uses prefix matching. With UUID-only IDs, prefix assumptions should be removed or replaced.

Suggested direction:

- Default to purge by age only, or
- Use configurable regex for UUID directories/files.

---

## 5) Documentation updates

Update docs that mention `PlanExe_...` run IDs to UUID-only examples.

Likely touchpoints:

- `/Users/neoneye/git/PlanExeGroup/PlanExe/docs/token_counting.md`
- `/Users/neoneye/git/PlanExeGroup/PlanExe/docs/plan.md` (if run-id examples remain)
- Any API examples in worker/frontend docs using prefixed timestamp IDs

---

## Naming note (optional but recommended)

Even if route path names stay `/runs/{run_id}`, the semantic model has shifted to UUID task IDs. A follow-up rename pass can improve clarity:

- `run_id` -> `task_id`
- `run_id_dir` -> `task_dir`

This is mostly mechanical and can be staged after UUID-only rollout.

---

## Rollout plan

1. Implement UUID-only generation + remove toggles.
2. Update purge behavior.
3. Update tests/docs.
4. Run one migration pass for any tooling that assumes `PlanExe_` prefix.

---

## Acceptance criteria

- No new run/task IDs use timestamp format.
- No UI or API option exists to request timestamp IDs.
- Multi-user flow create UUID directory names.
- Tests and docs contain UUID-only examples.
