---
title: Agent Smart Routing - Meta-Agent Dispatcher
date: 2026-02-09
status: proposal
author: Larry the Laptop Lobster
---

# Agent Smart Routing - Meta-Agent Dispatcher

## Overview

PlanExe's planning pipeline currently uses a single agent profile for all stages. As plans grow in complexity and domain diversity, different stages benefit from specialized agents optimized for specific tasks (research, writing, technical validation, creativity).

This proposal introduces a **meta-agent dispatcher** that routes each pipeline stage to the most appropriate agent based on stage type, domain, and requirements.

## Problem

- Generic agents produce mediocre results across all domains

- No way to leverage specialized models (reasoning models for analysis, fast models for formatting, etc.)

- Pipeline stages have different cost/quality trade-offs that aren't exploited

## Proposed Solution

### Architecture

```
┌─────────────────┐
│  PlanExe Core   │
│   (Orchestrator)│
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Meta-Agent      │  ← Dispatcher logic
│ Router          │
└────────┬────────┘
         │
         ├──→ Research Agent (Gemini 2.0 Flash)
         ├──→ Writing Agent (Claude Sonnet)
         ├──→ Technical Agent (GPT-4 + reasoning)
         └──→ Format Agent (Haiku/Fast model)
```

### Routing Rules

Store routing configuration in `llm_config/<profile>.json`:

```json
{
  "agent_routing": {
    "research": {
      "model": "google/gemini-2.0-flash-thinking-exp",
      "reason": "Fast, cheap, good at web search synthesis"
    },
    "outline": {
      "model": "anthropic/claude-sonnet-4",
      "reason": "Strong at structure and planning"
    },
    "technical": {
      "model": "openai/gpt-4-turbo",
      "thinking": "enabled",
      "reason": "Deep reasoning for complex technical content"
    },
    "format": {
      "model": "anthropic/claude-haiku-4",
      "reason": "Fast, cheap, reliable for formatting"
    }
  }
}
```

### Implementation

1. Add `AgentRouter` class in `backend/mcp_cloud/src/routing/`

2. Modify pipeline stages to call `router.get_agent(stage_type, domain)`

3. Add telemetry to track agent selection and performance per stage

4. Build admin UI to override routing rules per-customer

## Benefits

- **15-30% cost reduction** by using fast models for simple stages

- **Quality improvement** from specialized agents

- **Flexibility** for customers to bring their own agent configs

- **A/B testing** different agent combinations per stage

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Increased complexity | Start with 3-4 agent profiles, expand gradually |
| Debugging harder | Add detailed logging of agent selection |
| Config drift | Validate routing config on startup, fail fast |

## Next Steps

1. Prototype with 3 agents (research, writing, format)

2. Run side-by-side comparison on 20 existing plans

3. Measure cost savings and quality delta

4. Ship behind feature flag, enable for beta customers

## Success Metrics

- Cost per plan decreases by 20%+

- User satisfaction rating increases (via post-plan survey)

- No increase in pipeline failure rate

## Detailed Implementation Plan

### Phase A — Routing Contract and Registry

1. Define an explicit routing contract in `run_plan_pipeline.py` with:
   - stage name
   - routing signal inputs
   - selected agent class
   - fallback class
2. Build an agent registry file (YAML/JSON) mapping capabilities to stages.
3. Add deterministic routing mode for reproducible runs.

### Phase B — Dynamic Selection Engine

1. Implement router scoring using:
   - stage complexity
   - domain type
   - latency/cost budget
2. Add weighted scoring for each candidate agent and choose top-ranked.
3. Add confidence threshold to trigger fallback routing when uncertain.

### Phase C — Observability and Controls

1. Emit route decisions as structured events.
2. Track route success/failure by stage.
3. Add policy overrides for forced agent selection in sensitive flows.

### Validation Checklist

- Deterministic routing under fixed seeds
- Correct fallback activation under low confidence
- Route-quality lift vs static baseline

