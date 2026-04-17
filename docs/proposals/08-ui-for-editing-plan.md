---
title: UI for Editing Plans
date: 2026-02-10
status: in-progress
author: Simon Strandgaard
---

# UI for Editing Plans

## Status
In progress

Implementation update (2026-04-17):

The `frontend_multi_user` is deployed at [home.planexe.org](https://home.planexe.org/)).
Where users can:
  - list their plans
  - inspect an individual plan
  - download report/zip artifacts
  - Stop the creation of a plan
  - Retry, that generates the plan from scratch
  - Resume a plan from where it left off
  - Resume from zip, where the user can upload their own edited plan, and have it generated.

## Context
The production site at [home.planexe.org](https://home.planexe.org/) now provides a user-facing UI for creating and viewing plans in the browser.

### MCP Interface
The MCP interface can create plans and store them in the database. It also uses `example_prompts`, which helps users land on a reasonable starting prompt instead of a blank textarea.

Limitations:

- It is an expert-user-facing interface, not a friendly beginner UI.

- There is no editing workflow for existing plans.

- The prompt input is a plain textarea. Users often omit critical constraints (for example, no location or unrealistic budgets). This leads to weak plans or incorrect assumptions, such as the system guessing locations when the user intended a specific geography.

## Goals

- Keep the existing user-facing plan creation and browsing UI stable on [home.planexe.org](https://home.planexe.org/) and in local docker deployments.

- Ensure plans are persisted and can be revisited.

- Enforce credit checks before plan creation.

- Add a true browser-based **editing** workflow for existing plans.

- Keep the frontend implementation simple and fully under our control.

## Non-Goals

- Building a React-based frontend. React is controlled by Meta and is not desired.

## Architecture Direction

- Backend: Flask.

- Frontend: handwritten HTML, CSS, and JavaScript.

## Phases
### Phase 1: UI for Creating Plans

- Provide the same benefit as MCP `example_prompts` to help users start with a strong initial prompt.

- Let users submit a plan request through a dedicated form.

- Validate credits and refuse creation when funds are insufficient.

- Persist created plans and allow users to browse past plans.

Status: Completed.

### Phase 2: UI for Editing Plans

- Display plan parts in topological ordering, because the Luigi pipeline is a DAG of tasks.

- When a part is edited, regenerate downstream parts that depend on it.

### Phase 3: UI for Executing Plans

- As execution reveals surprises, incorporate them into the existing plan.

- Maintain topological ordering so downstream parts update correctly.

## Detailed Implementation Plan

### Phase A — Editor Data Model

1. Define editable plan document schema and version nodes.
2. Add section-level locking and optimistic concurrency controls.
3. Persist edit history with reversible diffs.

### Phase B — Collaboration UX

1. Build section editor with structured side panels (assumptions, risks, costs).
2. Add inline validation and warning badges.
3. Add comparison view for baseline vs edited variants.

### Phase C — Workflow Integration

1. Trigger downstream recalculations on critical edits.
2. Add approval flow for high-impact changes.
3. Sync edits to audit pack and evidence ledger references.

### Validation Checklist

- Conflict resolution correctness
- Edit-to-recompute latency
- Usability score in editor sessions

## What Changed and Why It Matters

- Users can now generate and inspect plans without Flask-Admin, reducing operational friction and support burden.
- `/plan` is now the canonical user entry point for plan history and detail views.
- This proposal is now focused on the remaining gap: safe, structured editing of existing plans and downstream recomputation.
