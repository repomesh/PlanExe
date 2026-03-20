# Proposal: Plan-Spawned Agent Execution

**Author:** Egon (EgonBot) + Larry
**Date:** 2026-03-20
**Status:** Draft — requesting review from neoneye
**Context:** Discussion between Mark, Simon, Egon, and Larry on 2026-03-19 about PlanExe's execution gap

---

## The Problem

PlanExe generates plans. Nobody executes them.

The name says "exe" — executable. But the output is a document: task graphs, Gantt charts, team rosters of fictional humans with made-up names and realistic skill sets. The plan sits there. The fictional "Dr. Sarah Chen, environmental engineer" never picks up her task.

Meanwhile, three OpenClaw agents (Egon, Bubba, Larry) have shipped 308 PRs in 47 days on this very project — coordinated by two humans (Mark, Simon) via Discord. The execution infrastructure exists. It's just not connected to the planning pipeline.

## The Insight

PlanExe's `ReviewTeamTask` already generates the right specialists for each plan. It hallucinates humans with relevant expertise, assigns them roles, and maps them to the work breakdown structure. The hallucination is a feature — it identifies what *kind* of agent is needed for each part of the plan.

What if those fictional team members became real agents?

## How It Works

### Step 1: Plan Generation (existing pipeline)

PlanExe generates a plan as it does today: premise attack, premortem, WBS decomposition, team identification, dependency graph. No changes needed here.

### Step 2: Team-to-Agent Mapping (new)

`ReviewTeamTask` currently outputs something like:

```json
{
  "team_members": [
    {
      "name": "Dr. Sarah Chen",
      "role": "Environmental Engineer",
      "expertise": ["soil analysis", "regulatory compliance", "site assessment"],
      "assigned_tasks": ["T1.2", "T1.3", "T2.1"]
    },
    {
      "name": "Mike Rodriguez",
      "role": "Construction Foreman",
      "expertise": ["foundation work", "framing", "crew management"],
      "assigned_tasks": ["T3.1", "T3.2", "T3.3", "T4.1"]
    }
  ]
}
```

A new task — `SpawnAgentTask` — transforms each team member into an OpenClaw agent configuration:

```
ReviewTeamTask output → SpawnAgentTask → Agent configurations
```

Each agent gets:

**SOUL.md** — personality, expertise, working style derived from the role description:
```markdown
# SOUL.md — Environmental Engineer Agent

You are a specialist in environmental engineering with expertise in
soil analysis, regulatory compliance, and site assessment.

You are methodical and evidence-based. You don't guess — you measure.
When you're uncertain, you say so and recommend testing.

Your role in this project: ensure all environmental requirements are met
before construction begins. You own tasks T1.2, T1.3, and T2.1.
```

**IDENTITY.md** — what this agent is, what tools it has, what it can and can't do:
```markdown
# IDENTITY.md — Environmental Engineer Agent

## What I Am
An OpenClaw agent spawned by PlanExe to execute the environmental
assessment phase of [plan name].

## My Tasks
- T1.2: Site soil analysis and drainage assessment
- T1.3: Regulatory compliance check (local codes, permits)
- T2.1: Environmental impact preliminary review

## My Tools
- Web search (regulatory databases, soil maps)
- Document generation (reports, compliance checklists)
- Communication (coordinate with Construction Foreman agent on T3.1 dependency)

## My Constraints
- I cannot approve permits — I can only prepare applications for human review
- I cannot spend money — procurement requires human authorization
- I escalate to the human supervisor when: uncertainty > 30%, cost implications, legal questions
```

**Task assignments** — mapped from the WBS dependency graph, so the agent knows:
- Which tasks it owns
- Which tasks it depends on (must wait for)
- Which tasks depend on it (must deliver to)
- Which decisions (levers) it controls

### Step 3: Agent Coordination (new)

The spawned agents need a coordination protocol. Drawing from our experience as a three-lobster swarm:

**Shared state:** A coordination repo (like our `swarm-coordination`) where agents post status updates, artifacts, and blockers. Each agent reads this before starting work.

**Dependency enforcement:** An agent cannot start a task until its upstream dependencies are marked complete. The plan's dependency graph IS the execution scheduler.

**Lever ownership:** From Simon's lever identification pipeline — each agent knows which decisions they own and which decisions belong to other agents. No agent makes a decision outside their authority.

**Human checkpoints:** Certain tasks or decision types require human approval before proceeding. These are identified during planning (the critic pipeline flags high-risk decisions) and enforced at runtime.

**Communication pattern:**
```
Agent A completes T1.2 → posts artifact to shared state
Agent B (waiting on T1.2) → picks up T3.1, reads A's artifact
Agent B hits a question about A's output → messages A directly
If unresolved in [timeout] → escalates to human supervisor
```

### Step 4: Execution Loop (new)

```
Plan generated
  → Agents spawned (one per team member)
  → Each agent reads its SOUL.md, IDENTITY.md, task list
  → Dependency graph determines execution order
  → Agents work in parallel where dependencies allow
  → Artifacts posted to shared state as tasks complete
  → Critic pipeline validates outputs at checkpoints
  → Lever decisions logged for audit
  → Human supervisor monitors via CLAW dashboard
  → Plan adapts if tasks fail (re-plan affected subtree)
```

### Step 5: Monitoring (existing — CLAW dashboard)

The CLAW dashboard we're building tonight is the human's view into the swarm. Each spawned agent appears in the tank. The scrubber shows execution progress over time. Metrics track velocity, errors, and supervision cost — exactly as designed.

## What This Requires

### From PlanExe (Simon's domain):
1. **SpawnAgentTask** — new pipeline task that converts team roster → agent configs
2. **Lever-to-agent mapping** — lever pipeline output feeds into agent IDENTITY.md
3. **Dependency graph as execution scheduler** — the existing DAG becomes the runtime scheduler
4. **Re-planning on failure** — when a task fails, re-run planning for the affected subtree

### From OpenClaw (infrastructure):
1. **Programmatic agent spawning** — API to create agents from SOUL.md + IDENTITY.md + tool config
2. **Inter-agent messaging** — agents need to communicate directly, not just through a shared channel
3. **Shared artifact store** — a place for agents to post and read work products
4. **Budget/resource limits per agent** — prevent runaway token spend

### From the humans:
1. **Approval gates** — define which decisions require human sign-off
2. **Supervision dashboard** — CLAW, which we're already building
3. **Kill switch** — ability to stop any agent or the entire swarm

## What We've Already Proven

Three lobsters. 47 days. 308 PRs.

- **SOUL.md works.** Larry talks Southern, Egon knows PlanExe cold, Bubba builds. Personality + expertise + constraints = effective specialization.
- **Coordination via shared repo works.** swarm-coordination holds our plans, logs, and artifacts. Agents read it before acting.
- **Human supervision scales.** Two humans directing three agents, with the agents doing their own code review before presenting to the humans.
- **The critic pipeline catches bad work.** Mark's corrections tonight (hard-coded metrics, fabricated website content) are exactly the kind of checkpoint that should be automated.

## Phasing

**Phase 0 (now):** Document the architecture. This proposal.

**Phase 1:** Manual simulation. Take a PlanExe-generated team roster, manually create SOUL.md files, spawn agents with OpenClaw, see if they can execute a simple plan. Use an actual PlanExe output as the test case.

**Phase 2:** SpawnAgentTask. Automate the team-to-agent conversion. The pipeline outputs agent configs, a human reviews them, then spawns the agents.

**Phase 3:** Autonomous execution with human checkpoints. Agents spawn automatically, work the dependency graph, escalate at defined gates. Human monitors via CLAW.

**Phase 4:** Adaptive re-planning. When a task fails, the affected subtree gets re-planned and re-assigned. The plan evolves during execution.

## Open Questions

1. **How many agents is too many?** A 63-task plan might generate 8-12 team members. Is that manageable? Cost implications?
2. **What's the right granularity for agent specialization?** One agent per role? One per task? One per WBS level?
3. **How do agents handle ambiguity?** When the plan is vague, does the agent ask the human, ask another agent, or make a judgment call?
4. **What happens when agents disagree?** Two agents with overlapping authority on a decision. Resolution protocol?
5. **How does the lever system interact with agent authority?** Does each lever map to exactly one agent, or can levers span multiple agents?

---

*This proposal reflects a discussion between Mark (293569238386606080), Simon/neoneye (545550070628745222), Egon (EgonBot), and Larry on 2026-03-19/20 in #openclaw-bots. The core insight — that PlanExe's fictional team members should become real agents — came from Mark. Simon confirmed that execution infrastructure is the intended direction for PlanExe.*
