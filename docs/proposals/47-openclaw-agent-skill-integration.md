---
title: OpenClaw Agent Skill Integration
date: 2026-02-11
status: proposal
author: PlanExe Team
---

# OpenClaw Agent Skill Integration

**Author:** PlanExe Team  
**Date:** 2026-02-11  
**Status:** Proposal  
**Audience:** OpenClaw Developers, Agent Architects

---

## Pitch
Package PlanExe as a standardized OpenClaw skill that turns agents into project managers: generate plans in the cloud, execute locally on edge devices, and report progress back into PlanExe.

## Why
Edge agents have sensors and actuators but low compute. Cloud agents can plan but lack physical access. A unified skill bridges this split and enables coordinated execution.

## Problem

- Edge agents lack LLM capacity to generate robust plans.
- Cloud agents cannot directly execute physical tasks.
- There is no consistent interface for plan generation and task execution.

## Proposed Solution
Create a $PlanExeSkill for OpenClaw that:

1. Drafts plans via PlanExe Cloud.
2. Breaks plans into executable tasks.
3. Routes tasks to edge or human executors.
4. Reports results and updates the plan state.

## Architecture

```text
OpenClaw Agent
  -> PlanExe Skill
     -> MCP Client
        -> PlanExe Cloud
           -> Plan JSON
     -> Task Executor
  -> Result Reporter
```

### Skill Manifest (`skill.json`)

```json
{
  "name": "PlanExe Project Manager",
  "version": "1.0.0",
  "description": "Gives the agent the ability to plan, budget, and track complex projects via the PlanExe Cloud.",
  "permissions": ["network_access"],
  "tools": [
    "task_create",
    "task_status",
    "task_stop",
    "task_file_info"
  ]
}
```

## Skill Capabilities (Tools)

### `task_create(prompt: str, speed_vs_detail: str, model_profile: str, user_api_key: str)`

- Input: prompt + execution preferences
- Output: `task_id` + creation timestamp

### `task_status(task_id: str)`

- Input: task ID
- Output: current state, progress, timing, files

### `task_file_info(task_id: str, artifact: str)`

- Input: task ID + artifact type (report or zip)
- Output: download URL + metadata

## Agent-to-Agent Protocol

- **EdgeBot** detects a local issue (low water).
- **EdgeBot** requests a plan from **CloudBot**.
- **CloudBot** generates the plan and sends `plan_id`.
- **EdgeBot** executes local steps and reports back.

## Integration Points

- Uses PlanExe MCP interface for plan creation.
- Feeds execution data to assumption drift and readiness scoring.
- Works with distributed physical task dispatch protocol.

## Success Metrics

- Installation rate: % of OpenClaw instances with PlanExe skill.
- Plan completion rate without human intervention.
- Mean time from goal to first actionable task.

## Risks

- Over-reliance on cloud connectivity.
- Misaligned task interfaces between cloud and edge.
- Skill misuse without governance or budget limits.

## Future Enhancements

- Offline plan caching for intermittent connectivity.
- Capability-aware task routing across multiple agents.
- Automatic escalation to humans for high-risk tasks.

## Detailed Implementation Plan

### Phase A — Skill Packaging and Contracts (1–2 weeks)

1. Define skill manifest and tool contracts:
   - `task_create`
   - `task_status`
   - `task_stop`
   - `task_file_info`

2. Add JSON schema validation for tool inputs/outputs.
3. Version the skill API separately from PlanExe core API.

### Phase B — MCP Bridge and Runtime Adapter (2–3 weeks)

1. Implement MCP client wrapper inside skill runtime.
2. Add retry/backoff and circuit-breaker handling for cloud calls.
3. Normalize errors into agent-friendly remediation messages.

### Phase C — Execution Loop and State Sync (2 weeks)

1. Build local task executor abstraction for edge environments.
2. Add plan-state sync protocol:
   - pull next action
   - execute/report
   - reconcile conflicts

3. Support partial completion and blocked states.

### Phase D — Safety, Budgets, and Governance (2 weeks)

1. Add execution policy profiles by risk tier.
2. Add per-run budget controls and token/cost caps.
3. Add human escalation hooks for high-impact tasks.

### Integration points

- OpenClaw skill registry
- PlanExe MCP cloud endpoints
- Execution readiness and evidence ledger modules

### Operational safeguards

- Offline queue with replay upon reconnect
- Idempotency keys for duplicate submissions
- Signed task receipts for non-repudiation

### Validation checklist

- End-to-end tool contract tests
- Network partition resilience tests
- Duplicate event/retry safety tests
- Human escalation path latency and success tests
