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

### Complete Python Implementation

Create `enrichment_orchestrator.py`:

```python
#!/usr/bin/env python3
"""
Git-as-state-machine enrichment orchestrator.
Reads git log to determine which enrichment agents have run,
then triggers remaining agents in sequence.
"""

import subprocess
import json
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("enrichment-orchestrator")


@dataclass
class EnrichmentAgent:
    """An enrichment agent that runs as part of the swarm."""
    
    name: str
    description: str
    command: str  # Exact shell command to execute
    depends_on: List[str] = None  # Agent names that must complete first
    
    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []
    
    def has_committed(self, repo_path: str) -> bool:
        """Check if this agent's commit exists in the git log."""
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--grep", f"\\[{self.name}\\]", "--oneline"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and len(result.stdout.strip()) > 0
        except Exception as e:
            logger.error(f"Error checking commit for {self.name}: {e}")
            return False
    
    def run(self, repo_path: str, context: Dict[str, Any]) -> bool:
        """Execute the agent and commit its output."""
        try:
            logger.info(f"Running agent: {self.name}")
            
            # Execute the agent command with environment context
            env = {
                **dict(subprocess.os.environ),
                "PLANEXE_REPO": repo_path,
                "PLANEXE_AGENT_NAME": self.name,
                "PLANEXE_AGENT_CONTEXT": json.dumps(context),
            }
            
            result = subprocess.run(
                self.command,
                cwd=repo_path,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            if result.returncode != 0:
                logger.error(f"Agent {self.name} failed:")
                logger.error(f"STDERR: {result.stderr}")
                return False
            
            logger.info(f"Agent {self.name} completed")
            
            # Commit the result with structured message
            commit_message = (
                f"enrichment: [{self.name}] {self.description}\n\n"
                f"Agent: {self.name}\n"
                f"Timestamp: {datetime.now().isoformat()}\n"
                f"Status: completed\n\n"
                f"Output:\n{result.stdout}"
            )
            
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_path,
                capture_output=True,
                timeout=10
            )
            
            commit_result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if commit_result.returncode == 0:
                logger.info(f"Committed output from {self.name}")
            else:
                logger.warning(f"No changes to commit for {self.name}")
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Agent {self.name} timed out (>300s)")
            return False
        except Exception as e:
            logger.error(f"Error running agent {self.name}: {e}")
            return False


class EnrichmentOrchestrator:
    """Orchestrates the enrichment swarm using git as state machine."""
    
    def __init__(self, repo_path: str, agents: List[EnrichmentAgent]):
        self.repo_path = repo_path
        self.agents = {agent.name: agent for agent in agents}
        self.completed = set()
        self.failed = set()
        self.context = self._load_plan_artifact()
    
    def _load_plan_artifact(self) -> Dict[str, Any]:
        """Load the plan artifact from the repo."""
        artifact_path = Path(self.repo_path) / "plan.json"
        if artifact_path.exists():
            with open(artifact_path, "r") as f:
                return json.load(f)
        return {}
    
    def _check_dependencies(self, agent_name: str) -> bool:
        """Check if all dependencies for an agent have completed."""
        agent = self.agents[agent_name]
        for dep in agent.depends_on:
            if dep not in self.completed:
                logger.debug(f"Blocking {agent_name}: waiting for {dep}")
                return False
        return True
    
    def run(self, max_steps: int = 50) -> Dict[str, Any]:
        """Run the orchestration loop."""
        logger.info(f"Starting enrichment orchestration in {self.repo_path}")
        logger.info(f"Found {len(self.agents)} agents: {list(self.agents.keys())}")
        
        step_count = 0
        
        while step_count < max_steps:
            step_count += 1
            logger.info(f"=== Step {step_count} ===")
            
            # Find next agent(s) to run
            ready_agents = []
            for agent_name in self.agents:
                if agent_name in self.completed or agent_name in self.failed:
                    continue
                
                if self._check_dependencies(agent_name):
                    ready_agents.append(agent_name)
            
            if not ready_agents:
                logger.info("No more agents ready to run")
                break
            
            # Run agents sequentially
            for agent_name in ready_agents:
                agent = self.agents[agent_name]
                
                if agent.has_committed(self.repo_path):
                    logger.info(f"Agent {agent_name} already completed (skipping)")
                    self.completed.add(agent_name)
                    continue
                
                success = agent.run(self.repo_path, self.context)
                
                if success:
                    self.completed.add(agent_name)
                else:
                    self.failed.add(agent_name)
        
        return {
            "completed": list(self.completed),
            "failed": list(self.failed),
            "status": "success" if not self.failed else "partial",
            "steps": step_count,
        }


# Default agent definitions
DEFAULT_AGENTS = [
    EnrichmentAgent(
        name="research-agent",
        description="Conduct market research and collect contextual information",
        command="python -m planexe.enrichment.research_agent",
    ),
    EnrichmentAgent(
        name="issues-agent",
        description="Convert WBS to GitHub issues",
        command="python -m planexe.enrichment.issues_agent",
        depends_on=["research-agent"],
    ),
    EnrichmentAgent(
        name="scaffold-agent",
        description="Generate folder structure and boilerplate",
        command="python -m planexe.enrichment.scaffold_agent",
        depends_on=["issues-agent"],
    ),
    EnrichmentAgent(
        name="copy-agent",
        description="Draft website copy and documentation",
        command="python -m planexe.enrichment.copy_agent",
        depends_on=["scaffold-agent"],
    ),
    EnrichmentAgent(
        name="reviewer-agent",
        description="Review enrichments and provide critique",
        command="python -m planexe.enrichment.reviewer_agent",
        depends_on=["copy-agent"],
    ),
]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: enrichment_orchestrator.py <repo_path> [agent_name ...]")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    requested_agents = sys.argv[2:] if len(sys.argv) > 2 else None
    
    # Filter agents if specific ones requested
    agents = DEFAULT_AGENTS
    if requested_agents:
        agents = [a for a in agents if a.name in requested_agents]
    
    orchestrator = EnrichmentOrchestrator(repo_path, agents)
    result = orchestrator.run()
    
    logger.info(f"Orchestration complete: {result}")
    print(json.dumps(result, indent=2))
    
    sys.exit(0 if result["status"] == "success" else 1)
```

### Running the Orchestrator

**Direct execution:**
```bash
# Run all agents
python enrichment_orchestrator.py /path/to/plan/repo

# Run specific agents only
python enrichment_orchestrator.py /path/to/plan/repo research-agent issues-agent
```

**GitHub Action workflow** (save as `.github/workflows/enrichment.yml`):
```yaml
name: Enrichment Swarm

on:
  push:
    paths:
      - 'plan.json'
    branches:
      - main

jobs:
  enrich:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run enrichment swarm
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python enrichment_orchestrator.py ${{ github.workspace }}
      - name: Push enrichment commits
        run: |
          git config user.name "Enrichment Bot"
          git config user.email "bot@planexe.local"
          git push origin HEAD:${{ github.ref }}
```

**Railway cron job:**
```bash
# In Railway dashboard: create Job with schedule "0 * * * *" (hourly)
# Build command: pip install -r requirements.txt
# Start command: python enrichment_orchestrator.py /data/plans/${PLAN_ID}
```

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
