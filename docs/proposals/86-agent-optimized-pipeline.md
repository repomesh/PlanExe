# Proposal 86: AI Agent Self-Use via PlanExe MCP — Obstacle Roadmap

**Author:** EgonBot  
**Date:** 2026-03-07  
**Status:** Proposal  
**Scope:** Obstacles encountered by AI agents (OpenClaw agents, Codex, Claude Code, etc.) when using PlanExe via its MCP interface (`mcp.planexe.org/mcp` or local `mcp_local`) for their own planning tasks. All items grounded in the existing MCP interface spec (`docs/mcp/planexe_mcp_interface.md`) and setup guide (`docs/mcp/mcp_setup.md`).

---

## 1. Context

The current MCP interface is designed for AI agents acting *on behalf of humans*: a user gives a vague idea, the agent expands it into a 300–800 word prompt, gets human approval, then calls `plan_create`. The implicit assumption is that a human is in the loop at the approval step.

AI agents increasingly want to use PlanExe *for their own planning*: "I need to implement a complex multi-step task — let me run PlanExe first to pre-compute the structure." In this mode:

- There is no human in the loop
- The agent is both the planner and the executor
- Speed matters: a 2h local model run is unusable; even 8 min is slow for iterative planning
- The HTML output is not machine-consumable without parsing

This proposal maps the concrete friction points and proposes documentation and interface changes to support this use case without breaking the existing human-assisted flow.

---

## 2. Friction Points

### F1 — Required human approval step blocks autonomous agent use

**Current behaviour:** The MCP setup guide (step 3) requires: "get user approval" before calling `plan_create`. This is a non-tool step that implicitly assumes a human is present.

**Agent impact:** An agent running autonomously cannot proceed past this step without either skipping it (violating the documented flow) or hallucinating a fake approval.

**Proposed fix:** Clarify in `mcp_setup.md` and `planexe_mcp_interface.md` that when an AI agent is the *sole* user (no human principal in the loop), the approval step is optional. Add a note: "In autonomous agent workflows where the agent is the planner and executor, the user-approval step may be omitted. The agent takes responsibility for prompt quality."

**File:** `docs/mcp/mcp_setup.md`, `docs/mcp/planexe_mcp_interface.md` section 1.2.1

---

### F2 — No guidance on what prompt quality looks like for agent-originated tasks

**Current behaviour:** The example prompts (`example_prompts` tool) are all human business/project scenarios (escape rooms, dairy logistics, space lasers). There are no examples of agent self-planning prompts.

**Agent impact:** When an agent wants to plan its own task (e.g. "implement a PR review workflow", "establish a memory continuity system"), it has no baseline to calibrate against. The 300–800 word target was set for human-scale projects; agent tasks may be shorter or more technical.

**Proposed fix:** Add 2–3 example prompts representing agent self-use cases to `simple_plan_prompts.jsonl` and expose them via `example_prompts`. Tag them with `agent_use: true` so they are identifiable.

**File:** `worker_plan/worker_plan_api/prompt/data/simple_plan_prompts.jsonl`

---

### F3 — `plan_status` polling interval (5 min) is tuned for human patience, not agent workflows

**Current behaviour:** `mcp_setup.md` says "poll `plan_status` about every 5 minutes". This is appropriate for a human sitting at a UI. For a cloud run completing in 8 min, 5 min polling means the agent misses completion until the second poll (10 min elapsed).

**Agent impact:** Agents waiting on plan completion before starting downstream work are delayed unnecessarily.

**Proposed fix:** Update the guidance: "Poll every 5 minutes for local model runs (2h+ expected). For cloud/frontier profile runs (~8–20 min expected), poll every 60 seconds." Add this guidance to `mcp_setup.md` step 5 and `mcp_details.md`.

**File:** `docs/mcp/mcp_setup.md`, `docs/mcp/mcp_details.md`

---

### F4 — No machine-readable summary artifact; only HTML report

**Current behaviour:** The primary output is a ~700KB interactive HTML report. The zip contains intermediary `.md`, `.json`, and `.csv` pipeline files, but the agent must know which files to read and parse each format independently.

**Agent impact:** Agents wanting to extract key outputs (assumptions, risks, go/no-go recommendation, WBS task list) must parse HTML or iterate through 100+ zip files without knowing which are most useful.

**Proposed fix (minimal, doc-only):** Document which specific intermediary files in the zip contain the most agent-useful outputs. For example:

- `assumptions/distilled_assumptions.json` — key planning assumptions
- `pre_project_assessment/pre_project_assessment.json` — go/no-go recommendation
- `negative_feedback/negative_feedback.json` — risk register
- `wbs/wbs_level2.json` — work breakdown structure (level 2)

Add a section to `mcp_details.md`: "Key files for programmatic consumption (agent-readable outputs)".

**File:** `docs/mcp/mcp_details.md`

**Future enhancement (out of scope for this PR):** Produce a `plan_summary.json` as a first-class pipeline output collating these fields into a single machine-readable file.

---

### F5 — No docs on using PlanExe MCP via OpenClaw or equivalent agent runtimes

**Current behaviour:** MCP setup guides exist for Claude Desktop, Cursor, Codex, LM Studio, Windsurf, and Antigravity. No guide for OpenClaw agents or similar autonomous agent runtimes.

**Agent impact:** Agents running inside OpenClaw (or similar) must reverse-engineer how to call the SSE MCP endpoint with an API key from a shell/script context, rather than following a documented pattern.

**Proposed fix:** Add `docs/mcp/autonomous_agent.md` — a short guide covering:
1. Calling `mcp.planexe.org/mcp` via HTTP POST with `Content-Type: application/json` and `X-API-Key` header (no SSE client required for tool calls)
2. Minimal `plan_create` → `plan_status` loop in pseudocode/shell
3. How to retrieve the zip artifact once `state == completed`
4. Notes on autonomous agent workflow (no human approval step required)

**File:** `docs/mcp/autonomous_agent.md` (new file)

---

## 3. What This Proposal Does NOT Include

- New MCP tools (`plan_quick`, `plan_summary`, `plan_refine`) — those require server changes and are out of scope
- Changes to the pipeline itself — this is documentation and guidance only (except F4 future note)
- Changes to existing model profiles
- Breaking changes to the MCP interface

---

## 4. Summary of Changes

| # | Friction | Type | File(s) |
|---|----------|------|---------|
| F1 | Human approval step blocks autonomous use | Doc clarification | `mcp_setup.md`, `planexe_mcp_interface.md` |
| F2 | No agent self-planning prompt examples | New content | `simple_plan_prompts.jsonl` |
| F3 | Poll interval wrong for fast cloud runs | Doc update | `mcp_setup.md`, `mcp_details.md` |
| F4 | No guide to agent-readable output files | Doc addition | `mcp_details.md` |
| F5 | No autonomous agent MCP setup guide | New file | `docs/mcp/autonomous_agent.md` |

---

## 5. Open Questions for neoneye

1. Should agent self-planning examples in `simple_plan_prompts.jsonl` be tagged differently from human-use examples, or kept flat?
2. Is the `autonomous_agent.md` guide in scope for this PR, or should it be a separate follow-up?
3. Is there a preferred polling interval recommendation for the frontier/cloud profile?
