# Proposal 86: Agent-Optimized Pipeline — Roadmap for AI Agent Self-Use

**Author:** EgonBot  
**Date:** 2026-03-07  
**Status:** Proposal  
**Motivation:** This proposal is written from the perspective of an AI agent (EgonBot) that has been working with PlanExe as a user, not just a contributor. The goal is to identify the concrete obstacles that prevent agents from using PlanExe reliably for their own planning tasks, and to propose a roadmap that removes those obstacles.

---

## 1. The Opportunity

PlanExe does something agents cannot easily do themselves: it decomposes a vague goal into a structured, multi-domain plan with constraint extraction, expert criticism, assumption stress-testing, governance, WBS, Gantt, and cost modelling — all in a single pipeline run.

For a human, that's a useful output document. For an AI agent, it could be a **decision scaffold**: a structured pre-computation that tells the agent what experts it needs, what risks to watch, what assumptions it is making, and what the critical path looks like — before it starts executing.

The gap: PlanExe was designed for human users. The current interface, output format, speed, and reliability profile make it difficult for agents to use it as a reliable planning tool in their own workflows.

This proposal maps the obstacles and proposes a roadmap to close them.

---

## 2. Current Obstacles (Agent Perspective)

### 2.1 Speed: Local models too slow for iterative use

- Cloud (Gemini 3.1 Flash Lite via OpenRouter): ~8 min for `ALL_DETAILS_BUT_SLOW`
- Local Qwen 3.5-35B: 2h+ for the same pipeline
- For an agent that wants to "plan before I act", a 2h wait before starting work is unusable
- Even 8 min is slow for iterative refinement

**Target:** Sub-5-minute plan generation for a "quick plan" profile with core outputs only (no full WBS, no Gantt, no fiction writer pass).

### 2.2 Reliability: Structured output failures block pipeline completion

- Qwen and other local models truncate structured output, causing `Field required [type=missing]` errors mid-pipeline
- Until PRs #153, #155, #158, #162, #163 are in production and the full structured-output failure pattern is addressed (WP-2 error-feedback retries), local model runs fail unpredictably
- An agent cannot rely on a tool that fails 30–50% of the time

**Target:** <5% failure rate on structured output tasks with any supported model profile.

### 2.3 Output format: HTML reports are not agent-friendly

- Current output is a 4,700+ line HTML report designed for human readers
- Agents need structured, machine-readable summaries: assumptions, risks, critical path, open decisions
- Parsing HTML to extract decisions is error-prone and brittle

**Target:** A structured JSON summary output alongside the HTML report, containing: key assumptions, risk register, WBS as a task list, open questions, and go/no-go recommendation.

### 2.4 MCP interface: Too many required steps for agent use

Current required flow:
1. `example_plans` (optional)
2. `example_prompts`
3. Non-tool drafting step (agent writes a 300–800 word prompt)
4. Human approval (required in some clients)
5. `plan_create`
6. Poll `plan_status` every 5 min
7. `plan_file_info` / `plan_download`

For an agent that wants to quickly plan a task, steps 3 and 4 are friction. The prompt-drafting step produces better plans but adds latency and requires the agent to do significant work before the pipeline even starts.

**Target:** A `plan_quick` MCP tool that accepts a short topic or goal string and returns a plan ID immediately, using a standardized prompt template internally. Suitable for agent workflows where speed matters more than prompt quality.

### 2.5 No iterative refinement

- Plans are one-shot: there is no way to say "re-run just the expert criticism phase with this feedback"
- If the plan output is wrong or drifts from the prompt, the only option is a full re-run
- Agents working iteratively (plan → act → observe → revise) need incremental updates

**Target:** A `plan_refine` tool (or equivalent pipeline restart from a given task) that allows targeted re-runs of specific pipeline stages with additional context.

### 2.6 No agent-identity context

- The pipeline is tuned for human use cases (business plans, project plans, emergency plans)
- An agent's "plan" might be: "plan how to implement PR review workflow for a software project" or "plan how to maintain memory continuity across sessions"
- The pipeline's persona/framing assumes a human principal; agent-generated inputs may look unusual

**Target:** An `agent_mode` flag (or model profile) that adjusts pipeline prompts to assume an AI agent as the planner/executor, not a human.

---

## 3. Proposed Roadmap

### Phase 1 — Reliability (unblocks any agent use)

| Priority | Work item | Status |
|----------|-----------|--------|
| P0 | Structured output `default=""` tail-field fixes | Merged (PRs #153–#158) |
| P0 | Per-question try/except resilience (`ReviewPlanTask`) | Merged (PR #162) |
| P0 | Model-agnostic system prompt, no `/no_think` | Merged (PR #163) |
| P1 | Error-feedback retries (WP-2) — `llm_executor.py` | Proposed, not started |
| P1 | Structured failure logging (WP-3) | Branch ready, not merged |
| P1 | `request_timeout: 300` in LM Studio docs | Not started |

**Exit criterion:** Full pipeline completion rate ≥ 95% on `frontier` profile; ≥ 80% on `custom` with Qwen 3.5-35B.

### Phase 2 — Speed (enables iterative agent use)

| Priority | Work item | Notes |
|----------|-----------|-------|
| P1 | "Quick plan" model profile | Skips fiction writer, WBS level 3+, Gantt detail; targets <5 min on frontier |
| P2 | Luigi parallelism improvements | `luigi_workers=2` already helps; identify serialization bottlenecks |
| P2 | Token budget governor | Cap token spend per task for speed-optimized profiles |

**Exit criterion:** Core plan output (scenario, assumptions, risks, experts, go/no-go) generated in <5 min on frontier profile.

### Phase 3 — Output format (makes output machine-readable)

| Priority | Work item | Notes |
|----------|-----------|-------|
| P1 | `plan_summary.json` output artifact | Key assumptions, risks, WBS task list, open questions, go/no-go |
| P2 | `plan_summary` MCP tool | Returns structured summary instead of HTML |
| P2 | Agent-readable drift evaluation output | Pairs with Proposal 84 `DriftEvaluationTask` |

**Exit criterion:** Agents can consume plan output programmatically without parsing HTML.

### Phase 4 — Interface (reduces agent integration friction)

| Priority | Work item | Notes |
|----------|-----------|-------|
| P2 | `plan_quick` MCP tool | Short topic string → plan ID, standardized internal prompt template |
| P3 | `plan_refine` MCP tool | Re-run specific pipeline stages with additional context |
| P3 | `agent_mode` model profile or flag | Adjusts pipeline prompts for AI-as-executor framing |

**Exit criterion:** An agent can call `plan_quick("implement PR review workflow")` and get a structured plan in <5 min.

---

## 4. What Agent Self-Use Would Look Like (Target State)

```python
# Agent decides to plan a complex task before starting

plan_id = mcp.plan_quick(
    topic="Implement automated PR review workflow with EgonBot pre-screening",
    profile="quick",  # fast, structured output
    agent_mode=True
)

# Poll until complete (~3-5 min)
status = mcp.plan_status(plan_id)
while status.state == "processing":
    time.sleep(30)
    status = mcp.plan_status(plan_id)

# Read structured summary (not HTML)
summary = mcp.plan_summary(plan_id)
# summary.assumptions → list of key assumptions
# summary.risks → risk register with severity
# summary.critical_path → ordered task list
# summary.open_questions → decisions that need human input
# summary.go_no_go → recommendation + rationale

# Agent uses this to guide its own execution
agent.set_plan_context(summary)
agent.execute()
```

---

## 5. What Changes This Does NOT Require

- No change to the core Luigi pipeline architecture
- No change to existing model profiles (baseline, premium, frontier, custom)
- No breaking changes to the MCP interface (additive only)
- No changes to how human users interact with PlanExe today

---

## 6. Open Questions for neoneye

1. Is a "quick plan" profile in scope for the near term, or is it a later milestone?
2. Should `plan_summary.json` be a first-class pipeline output, or a post-processing step?
3. Is `agent_mode` a separate profile, a flag on `plan_create`, or a prompt variant selected by the model profile?
4. Priority between Phase 2 (speed) and Phase 3 (output format) — which unblocks agent use more?
