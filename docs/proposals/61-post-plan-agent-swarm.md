# Post-Plan Agent Swarm Proposal

## Overview

After plan generation, PlanExe activates a specialized agent swarm. Each agent takes the plan artifact as input, does one job, and hands off. The GitHub repo (see plan-to-repo proposal) serves as the shared workspace — same role the codebase plays in Codebuff.

## Agents

### Repo Agent

Provisions a GitHub repo, pushes plan artifact, README, folder scaffold. (Ties into plan-to-repo proposal.)

### Scaffold Agent

Reads plan phases and generates folder structure, basic website boilerplate, and project scaffolding appropriate to the plan type (SaaS, physical business, nonprofit, etc.)

### Research Agent

Enriches the plan with live data: market size, competitor intel, pricing benchmarks, regulatory considerations. Commits findings to /research in the plan repo.

### Issues Agent

Converts plan phases and tasks into GitHub issues and milestones. Creates an instant actionable task board on the repo.

### Domain Agent

Suggests domain names aligned with the plan's business concept, checks availability, optionally registers (with user credit authorization).

### Reviewer Agent

Critiques the plan for logical gaps, missing assumptions, and weak phases. Opens a GitHub issue or PR with suggested revisions.

## Orchestration Pattern

- Inspired by Codebuff's multi-agent architecture (File Picker → Planner → Editor → Reviewer)
- Sequential where order matters (Repo Agent first), parallel where independent (Research + Issues + Domain can run simultaneously)
- Each agent is stateless — reads from plan artifact + repo, writes back to repo
- Model-per-agent: heavyweight model for Reviewer, lightweight for Issues/Domain

## Credit Model

- Basic swarm (Repo + Scaffold + Issues): included with plan generation
- Research Agent: costs additional credits (external API calls)
- Domain Agent: costs credits if registration triggered
- Reviewer Agent: costs credits (heavyweight model inference)

## Implementation Notes

- Builds on plan-to-repo infrastructure
- Agent definitions follow Codebuff-style TypeScript agent definition pattern
- PlanExe orchestrates via job queue; agents are stateless workers
