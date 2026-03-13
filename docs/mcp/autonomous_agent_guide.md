# Autonomous Agent Guide for PlanExe

This guide is for AI agents (Claude, GPT, Codex, etc.) that consume PlanExe via MCP. It covers the end-to-end workflow for autonomous plan creation without human intervention.

## When to use PlanExe

Use PlanExe when an agent needs to plan a **multi-phase project** with real-world constraints — the kind of thing that takes weeks to months. Examples:

- Launching a product or service
- Setting up infrastructure (factory, clinic, data center)
- Organizational change (governance, team restructuring)
- Policy implementation at scale

**Do not use PlanExe** for simple tasks (checklists, single-step operations, code generation). Use a normal LLM response for those.

## Autonomous workflow

### Step 1: Discover capabilities

```
Call: example_prompts
```

Read the returned examples to understand what a good prompt looks like. PlanExe prompts are flowing prose (~300-800 words), not structured markdown.

### Step 2: Draft a strong prompt

Before calling `plan_create`, draft a prompt that covers:

| Dimension | What to include |
|-----------|----------------|
| **Objective** | What the project achieves. Be specific. |
| **Scope** | What's included and excluded. Geographic/temporal bounds. |
| **Constraints** | Budget range, timeline, regulatory requirements, technical limits. |
| **Stakeholders** | Who's involved — team, beneficiaries, regulators, funders. |
| **Resources** | Available budget, team size, existing infrastructure. |
| **Success criteria** | Measurable outcomes. How do you know the project succeeded? |

Write as flowing prose. Weave specs, constraints, and targets naturally into sentences. Do not use markdown headers or bullet lists in the prompt itself.

### Step 3: Select model profile (optional)

```
Call: model_profiles
```

Choose a profile based on quality/speed tradeoff:
- **baseline** — Fast, good for most projects (~10-15 min)
- **premium** — Higher quality, slower (~15-25 min)
- **frontier** — Best quality, slowest

### Step 4: Create the plan

```
Call: plan_create(prompt="...", model_profile="baseline")
```

Returns a `plan_id` (UUID). Store this — you'll need it for all subsequent calls.

### Step 5: Monitor progress

```
Call: plan_status(plan_id="...")
```

Poll every 5 minutes. State transitions:
- `pending` → Plan is queued
- `processing` → Pipeline is running
- `completed` → Report is ready
- `failed` → Terminal error (use `plan_resume` or `plan_retry`)
- `stopped` → User called `plan_stop` (use `plan_resume` to continue or `plan_retry` to restart)

### Step 6: Handle failures

When `plan_status` returns `state: "failed"`, check the `error` dict for failure diagnostics:

| Field | Meaning |
|-------|---------|
| `error.failure_reason` | Category: `generation_error`, `worker_error`, `inactivity_timeout`, `internal_error`, `version_mismatch` |
| `error.failed_step` | Pipeline step that was active when the failure occurred |
| `error.message` | Human-readable error message |
| `error.recoverable` | `true` → try `plan_resume`; `false` → use `plan_retry` |

If `recoverable` is `true`, resume first (preserves progress):

```
Call: plan_resume(plan_id="...")  # Continue from where it stopped
```

If `recoverable` is `false` or resume fails, do a full restart:

```
Call: plan_retry(plan_id="...")   # Discard all progress, start fresh
```

If diagnostics are `null` (legacy plan), default to trying `plan_resume` first, then `plan_retry`.

### Step 7: Retrieve output

```
Call: plan_file_info(plan_id="...", artifact="report")
```

The `download_url` points to the self-contained HTML report. The `zip` artifact contains all intermediary files (markdown, JSON, CSV).

## Error handling for agents

| Scenario | Action |
|----------|--------|
| `plan_status` returns `failed` | Check `recoverable` field: if `true`, call `plan_resume` (preserves progress); if `false`, call `plan_retry`. If diagnostics are `null`, try `plan_resume` first, then `plan_retry`. |
| `plan_status` stays `pending` > 5 min | Worker may be down. Report to user. |
| `plan_status` `timing.last_progress_at` unchanged > 10 min | Plan likely stalled. Call `plan_stop`, then `plan_retry`. Fall back to file `updated_at` timestamps if `last_progress_at` is `null`. |
| Lost `plan_id` | Call `plan_list` to recover recent plans. |
| Invalid API key | Error code `INVALID_USER_API_KEY`. Prompt user to check their key. |

## Agent self-planning pattern

An advanced pattern: use PlanExe to plan the agent's own work.

1. Agent receives a complex task from the user
2. Agent calls PlanExe to generate a strategic plan
3. Agent reads the plan's WBS (work breakdown structure) from the zip
4. Agent executes the plan step by step, tracking progress against the WBS

Key files in the zip for agent consumption:
- `018-2-wbs_level1.json` — High-level work packages
- `018-5-wbs_level2.json` — Detailed tasks within each package
- `023-2-wbs_level3.json` — Sub-tasks with effort estimates
- `004-2-pre_project_assessment.json` — Feasibility assessment
- `003-6-distill_assumptions_raw.json` — Key assumptions to validate

## Prompt writing tips for agents

1. **Be specific about geography** — "Copenhagen, Denmark" not "a city"
2. **Include budget ranges** — "EUR 500K-1M" not "reasonable budget"
3. **Set a timeline** — "18-month implementation" not "as soon as possible"
4. **Name the team** — "5-person core team with 3 contractors" not "a team"
5. **Define success** — "500 active users within 6 months" not "good adoption"
