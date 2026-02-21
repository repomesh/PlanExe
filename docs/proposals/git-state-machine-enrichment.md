# Post-Plan Enrichment: Git as State Machine

## Core Idea

Each enrichment agent commits its output to the plan's GitHub repo. The git log IS the state. No separate state store needed.

## How It Works

Each enrichment agent:
1. Reads from the repo (plan artifact + prior enrichment commits)
2. Does its work
3. Commits output to the repo with a structured commit message
4. Signals completion

The orchestrator:
1. Reads the repo commit log
2. Determines which agents haven't run yet
3. Triggers the next agent
4. Repeats until all agents complete

## State Transitions (Example)

```
commit a1b2 — [repo-agent] plan artifact initialized
commit c3d4 — [research-agent] market research added
commit e5f6 — [issues-agent] WBS converted to GitHub issues
commit g7h8 — [scaffold-agent] folder structure + boilerplate committed
commit i9j0 — [copy-agent] website copy drafted
commit k1l2 — [reviewer-agent] critique and revision suggestions
```

Each commit = a state transition. Full audit trail. Human-readable.

## Properties

**Durable:** Survives crashes. Restart from last commit, no data loss.

**Resumable:** Any agent is idempotent — if its output commit exists, skip it. Resume mid-swarm after failure.

**Auditable:** Full enrichment history as git log. Each agent's contribution is isolated to its commit(s).

**Reviewable:** Humans (or Simon) can review enrichment between commits, approve/reject, branch at any point.

**Parallelizable:** Independent agents (Research + Domain + Scaffold) can run on separate branches, merge when complete.

## The Orchestrator

Simple loop:
```python
def run_enrichment_swarm(repo_url: str, agents: list[Agent]):
    for agent in agents:
        if not agent.has_committed(repo_url):
            agent.run(repo_url)
            # agent commits its output
        # else: already done, skip
```

The orchestrator itself can be:
- A GitHub Action triggered by the initial plan commit
- A Railway job triggered by a webhook
- An OpenClaw session running a loop

## Relationship to Session State

Session state (in-memory) is optimal for single-task, single-session work (coding agent fixing one bug). Git state is optimal for multi-step enrichment that:
- Spans hours or days
- Involves human review between steps
- Needs to be resumable after failure
- Benefits from parallel enrichment branches

These aren't mutually exclusive. An agent can use in-memory session state *within* its own run, then commit the result to git when done.

## Open Questions

1. Should enrichment run sequentially or in parallel branches?
2. What triggers the orchestrator — plan generation webhook, or on-demand?
3. Should humans approve enrichment commits via PR before merge?
4. How does credit metering work — per agent run, or per enrichment session?
