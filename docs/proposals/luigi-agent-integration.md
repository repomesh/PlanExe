# Luigi Pipeline Agent Integration: Two Approaches

## Context

PlanExe's core pipeline is implemented as a Luigi DAG (~4000 lines Python). External agent frameworks (Codebuff, OpenClaw, custom swarms) want to interact with individual pipeline stages — either to annotate them or to inject into them. The challenge: TypeScript agent definitions that duplicate Python logic drift and break silently.

Two proposals follow. They are not mutually exclusive.

---

## Option A: `@agent_meta` Decorator (Metadata Layer)

### Concept
Add a lightweight Python decorator to every Luigi task that declares machine-readable metadata. External frameworks read this metadata to understand what each task does without duplicating the logic.

### Implementation

```python
from planexe.agent_meta import agent_meta

@agent_meta(
    name="identify_risks",
    description="Identifies project risks from assumptions and context. Returns structured risk registry.",
    tools=["read_context", "read_assumptions"],
    outputs=["risk_registry"],
    stage="risk_assumptions",
    tags=["analysis", "risk"],
)
class IdentifyRisks(luigi.Task):
    ...
```

### Auto-generated manifest
At startup or build time, PlanExe generates `.agents/manifest.json`:

```json
{
  "tasks": [
    {
      "name": "identify_risks",
      "description": "...",
      "tools": ["read_context", "read_assumptions"],
      "outputs": ["risk_registry"],
      "stage": "risk_assumptions"
    }
  ]
}
```

### Benefits
- Single source of truth: metadata lives next to the Python code
- Framework-agnostic: any agent framework can read the manifest
- Low engineering cost: decorator pattern, ~50 lines to implement
- Drift-proof: changing the task forces the developer to look at the decorator

### Limitations
- Still read-only from agent frameworks — they can read what tasks exist but can't inject into execution
- Requires discipline: developers must keep metadata accurate when changing task logic

---

## Option C: RPC Injection Interface

### Concept
Expose each Luigi task stage as an RPC endpoint. External agent frameworks call the Python pipeline directly rather than duplicating logic in TypeScript. The TypeScript agent definitions become thin RPC wrappers.

### Implementation sketch

```python
# planexe/rpc/task_runner.py
from fastapi import FastAPI
from planexe.pipeline import TASK_REGISTRY

app = FastAPI()

@app.post("/run/{task_name}")
async def run_task(task_name: str, context: dict):
    task_class = TASK_REGISTRY[task_name]
    result = await task_class.run_with_context(context)
    return result

@app.get("/tasks")
async def list_tasks():
    return [task.agent_meta for task in TASK_REGISTRY.values()]
```

TypeScript agent (thin wrapper):
```typescript
export default {
  id: "identify-risks",
  async *handleSteps(context) {
    yield {
      tool: "http_post",
      url: "http://planexe:8001/run/identify_risks",
      body: context
    }
  }
}
```

### Benefits
- No drift: TypeScript agents call Python, never duplicate it
- Framework-agnostic: any HTTP client can invoke pipeline stages
- Enables true injection: agents can pre/post-process at any stage
- Composable: stages can be called independently or as part of the full DAG

### Limitations
- Higher engineering cost than Option A
- Requires careful API design (context schema, error handling, auth)
- Full DAG execution still goes through Luigi; RPC is for individual stage invocation

---

## Recommendation

**Do A now** — cheap, immediate, makes the codebase self-documenting for agent frameworks. Generate `manifest.json` and it becomes the source of truth for any TypeScript definitions.

**Plan C for next quarter** — RPC injection is the right long-term answer once the manifest (Option A) has proven out which stages external frameworks actually want to call. Build the RPC surface around real usage, not speculation.

---
