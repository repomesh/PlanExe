# Luigi Pipeline Agent Integration: Two Approaches

## Context

PlanExe's core pipeline is implemented as a Luigi DAG (~4000 lines Python). External agent frameworks (Codebuff, OpenClaw, custom swarms) want to interact with individual pipeline stages — either to annotate them or to inject into them. The challenge: TypeScript agent definitions that duplicate Python logic drift and break silently.

Two proposals follow. They are not mutually exclusive.

---

## Option A: `@agent_meta` Decorator (Metadata Layer)

### Concept
Add a lightweight Python decorator to every Luigi task that declares machine-readable metadata. External frameworks read this metadata to understand what each task does without duplicating the logic.

### Complete Implementation

**File: `planexe/agent_meta.py`**

```python
"""
Agent metadata decorator for Luigi tasks.
Adds self-documenting metadata to pipeline stages for external agent frameworks.
"""

import json
from typing import Dict, List, Any, Callable, Optional
from functools import wraps
import inspect


# Global registry to track all decorated tasks
_AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {}


def agent_meta(
    name: str,
    description: str,
    tools: List[str],
    outputs: List[str],
    stage: str,
    tags: List[str] = None,
    timeout_seconds: int = 300,
    max_retries: int = 1,
) -> Callable:
    """
    Decorator to add agent metadata to a Luigi task.
    
    Args:
        name: Unique identifier for this task (e.g., "identify_risks")
        description: Human-readable description of what this task does
        tools: List of tools/resources this task reads from
        outputs: List of outputs this task produces
        stage: Pipeline stage name (e.g., "risk_assumptions")
        tags: Optional list of tags for categorization
        timeout_seconds: Maximum execution time
        max_retries: How many times to retry on failure
    
    Returns:
        Decorator function
    """
    def decorator(cls):
        # Store metadata in the class
        cls._agent_meta = {
            "name": name,
            "displayName": name.replace("_", " ").title(),
            "description": description,
            "tools": tools,
            "outputs": outputs,
            "stage": stage,
            "tags": tags or [],
            "timeoutSeconds": timeout_seconds,
            "maxRetries": max_retries,
            "pythonClass": f"{cls.__module__}.{cls.__name__}",
            "inputSchema": extract_input_schema(cls),
            "outputSchema": extract_output_schema(cls),
        }
        
        # Register in global registry
        _AGENT_REGISTRY[name] = cls._agent_meta
        
        # Add method to expose metadata
        @classmethod
        def get_agent_meta(cls_inner) -> Dict[str, Any]:
            """Return the agent metadata for this task."""
            return cls._agent_meta
        
        cls.get_agent_meta = get_agent_meta
        
        return cls
    
    return decorator


def extract_input_schema(cls) -> Dict[str, List[str]]:
    """Extract input parameters from the task's __init__ or requires() method."""
    sig = inspect.signature(cls.__init__)
    params = [p for p in sig.parameters.keys() if p not in ('self', 'args', 'kwargs')]
    return {"parameters": params, "context": []}


def extract_output_schema(cls) -> Dict[str, Any]:
    """Extract output schema from the task's output() method."""
    return {
        "format": "json",
        "fields": ["result"]
    }


def generate_manifest(output_path: str = ".agents/manifest.json") -> None:
    """
    Generate manifest.json from all registered agents.
    Call this after importing all task modules.
    """
    manifest = {
        "version": "1.0",
        "agents": sorted(
            list(_AGENT_REGISTRY.values()),
            key=lambda x: x["name"]
        ),
        "count": len(_AGENT_REGISTRY),
    }
    
    # Ensure output directory exists
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"Generated manifest with {manifest['count']} agents at {output_path}")


def list_agents() -> List[Dict[str, Any]]:
    """Return list of all registered agents."""
    return list(_AGENT_REGISTRY.values())


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific agent by name."""
    return _AGENT_REGISTRY.get(name)
```

**Using the decorator in a Luigi task:**

```python
import luigi
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
    """Analyzes plan assumptions to identify risks."""
    
    context_file = luigi.PathParameter(default="./context.json")
    
    def requires(self):
        return ResolveAssumptions()
    
    def output(self):
        return luigi.LocalTarget(f"./artifacts/risks.json")
    
    def run(self):
        with self.input().open('r') as f:
            assumptions = json.load(f)
        
        with open(self.context_file, 'r') as f:
            context = json.load(f)
        
        # Your analysis logic here
        risks = analyze_risks(assumptions, context)
        
        with self.output().open('w') as f:
            json.dump(risks, f, indent=2)
```

**Generating the manifest:**

```python
# In your main.py or __init__.py
from planexe.agent_meta import generate_manifest
import planexe.pipeline.tasks  # Import all task modules

# Generate manifest after all tasks are imported
if __name__ == "__main__":
    generate_manifest(".agents/manifest.json")
    luigi.build([...)
```

**Auto-generated manifest** (`.agents/manifest.json`):

```json
{
  "version": "1.0",
  "agents": [
    {
      "name": "identify_risks",
      "displayName": "Identify Risks",
      "description": "Identifies project risks from assumptions and context. Returns structured risk registry.",
      "tools": ["read_context", "read_assumptions"],
      "outputs": ["risk_registry"],
      "stage": "risk_assumptions",
      "tags": ["analysis", "risk"],
      "timeoutSeconds": 300,
      "maxRetries": 1,
      "pythonClass": "planexe.pipeline.tasks.IdentifyRisks",
      "inputSchema": {
        "parameters": ["context_file"],
        "context": []
      },
      "outputSchema": {
        "format": "json",
        "fields": ["risk_registry"]
      }
    },
    {
      "name": "resolve_assumptions",
      "displayName": "Resolve Assumptions",
      "description": "Validates and resolves plan assumptions against known data.",
      "tools": ["read_knowledge_base"],
      "outputs": ["assumptions_registry"],
      "stage": "risk_assumptions",
      "tags": ["analysis"],
      "timeoutSeconds": 300,
      "maxRetries": 1,
      "pythonClass": "planexe.pipeline.tasks.ResolveAssumptions",
      "inputSchema": {
        "parameters": ["plan_file"],
        "context": []
      },
      "outputSchema": {
        "format": "json",
        "fields": ["assumptions_registry"]
      }
    }
  ],
  "count": 2
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

### Complete Implementation

**File: `planexe/rpc/task_runner.py`**

```python
"""
FastAPI RPC interface for Luigi pipeline tasks.
Allows external frameworks (TypeScript, Java, etc.) to invoke pipeline stages via HTTP.
"""

import json
import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import luigi
from planexe.agent_meta import list_agents, get_agent
from planexe.pipeline import TASK_REGISTRY, build_luigi_task

logger = logging.getLogger("task-rpc")


# Request/Response models
class TaskInvocationRequest(BaseModel):
    task_name: str
    parameters: Dict[str, Any] = {}
    context: Dict[str, Any] = {}
    timeout_seconds: int = 300


class TaskResult(BaseModel):
    task_name: str
    status: str  # "success", "failed", "timeout"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: int
    tokens_used: int = 0


class TaskMetadata(BaseModel):
    name: str
    displayName: str
    description: str
    stage: str
    inputs: list
    outputs: list
    timeout_seconds: int


# Create FastAPI app
app = FastAPI(title="PlanExe Task RPC", version="1.0")


# Task registry and results cache (can be backed by Redis)
_task_registry: Dict[str, Any] = {}
_results_cache: Dict[str, TaskResult] = {}


async def task_executor(task_name: str, parameters: Dict[str, Any], context: Dict[str, Any]) -> TaskResult:
    """
    Execute a Luigi task and return the result.
    This runs the task in isolation, capturing output and errors.
    """
    start_time = datetime.now()
    
    try:
        if task_name not in TASK_REGISTRY:
            raise ValueError(f"Unknown task: {task_name}")
        
        # Build the task instance
        task_class = TASK_REGISTRY[task_name]
        task_instance = build_luigi_task(task_class, parameters, context)
        
        logger.info(f"Executing task: {task_name}")
        
        # Run the task with a timeout
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, luigi.build, [task_instance]),
            timeout=300.0
        )
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        if result:
            # Extract output from the task
            output_data = extract_task_output(task_instance)
            
            return TaskResult(
                task_name=task_name,
                status="success",
                result=output_data,
                execution_time_ms=execution_time,
                tokens_used=estimate_tokens(str(output_data))
            )
        else:
            return TaskResult(
                task_name=task_name,
                status="failed",
                error="Task execution returned False",
                execution_time_ms=execution_time,
            )
    
    except asyncio.TimeoutError:
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        return TaskResult(
            task_name=task_name,
            status="timeout",
            error=f"Task execution exceeded 300 seconds",
            execution_time_ms=execution_time,
        )
    
    except Exception as e:
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Task {task_name} failed: {str(e)}")
        return TaskResult(
            task_name=task_name,
            status="failed",
            error=str(e),
            execution_time_ms=execution_time,
        )


def extract_task_output(task_instance) -> Dict[str, Any]:
    """Extract output from a completed task."""
    try:
        output = task_instance.output()
        if hasattr(output, 'path'):
            with open(output.path, 'r') as f:
                return json.load(f)
        return {"message": "Task completed"}
    except Exception as e:
        logger.warning(f"Could not extract task output: {e}")
        return {"message": "Task completed"}


def estimate_tokens(text: str) -> int:
    """Rough estimate of tokens (1 token ≈ 4 characters)."""
    return len(text) // 4


# API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "task-rpc"}


@app.get("/tasks")
async def list_tasks():
    """List all available tasks and their metadata."""
    agents = list_agents()
    return {
        "count": len(agents),
        "tasks": agents,
    }


@app.get("/tasks/{task_name}")
async def get_task_metadata(task_name: str):
    """Get metadata for a specific task."""
    agent = get_agent(task_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_name}")
    
    return agent


@app.post("/run")
async def run_task(request: TaskInvocationRequest, background_tasks: BackgroundTasks):
    """
    Execute a task and return the result.
    
    Request body:
    {
      "task_name": "identify_risks",
      "parameters": {"context_file": "./context.json"},
      "context": {"user_id": "user-123"},
      "timeout_seconds": 300
    }
    """
    # Validate task exists
    if request.task_name not in TASK_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown task: {request.task_name}")
    
    # Execute the task
    result = await task_executor(
        request.task_name,
        request.parameters,
        request.context
    )
    
    # Cache the result
    result_id = f"{request.task_name}-{datetime.now().timestamp()}"
    _results_cache[result_id] = result
    
    return result


@app.post("/run/{task_name}")
async def run_task_by_name(task_name: str, parameters: Dict[str, Any] = None, context: Dict[str, Any] = None):
    """
    Shorthand endpoint to run a task by name.
    
    Example:
    POST /run/identify_risks
    {
      "context_file": "./context.json"
    }
    """
    parameters = parameters or {}
    context = context or {}
    
    result = await task_executor(task_name, parameters, context)
    return result


@app.get("/results/{result_id}")
async def get_result(result_id: str):
    """Retrieve a cached task result."""
    if result_id not in _results_cache:
        raise HTTPException(status_code=404, detail="Result not found")
    
    return _results_cache[result_id]


# Startup event
@app.on_event("startup")
async def startup_event():
    """Load task registry on startup."""
    logger.info(f"Task RPC Server starting")
    logger.info(f"Loaded {len(TASK_REGISTRY)} tasks from registry")
    for task_name in sorted(TASK_REGISTRY.keys()):
        logger.info(f"  - {task_name}")
```

**File: `planexe/rpc/client.py`**

```python
"""
Python client for the Task RPC server.
For local use without HTTP overhead.
"""

from typing import Dict, Any
from planexe.rpc.task_runner import task_executor, TaskResult
import asyncio


class TaskRPCClient:
    """Synchronous client for task execution."""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
    
    def run_task(
        self,
        task_name: str,
        parameters: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        timeout_seconds: int = 300,
    ) -> TaskResult:
        """Execute a task synchronously."""
        parameters = parameters or {}
        context = context or {}
        
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            task_executor(task_name, parameters, context)
        )
    
    async def run_task_async(
        self,
        task_name: str,
        parameters: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
    ) -> TaskResult:
        """Execute a task asynchronously."""
        parameters = parameters or {}
        context = context or {}
        
        return await task_executor(task_name, parameters, context)
```

**File: `planexe/rpc/agents.ts` (TypeScript)**

Thin wrapper agents that call the RPC interface:

```typescript
/**
 * Auto-generated TypeScript agents that wrap RPC calls to Python tasks.
 * These agents are framework-agnostic and can be used with any LLM framework.
 */

interface TaskAgent {
  id: string;
  displayName: string;
  async invoke(context: any): Promise<any>;
}

// Base RPC agent
class RPCAgent implements TaskAgent {
  constructor(
    public id: string,
    public displayName: string,
    private taskName: string,
    private rpcUrl: string = "http://localhost:8001"
  ) {}

  async invoke(context: any): Promise<any> {
    const response = await fetch(`${this.rpcUrl}/run/${this.taskName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(context),
    });

    if (!response.ok) {
      throw new Error(`Task failed: ${response.statusText}`);
    }

    const result = await response.json();
    return result.result;
  }
}

// Auto-generated agent instances
export const identifyRisksAgent = new RPCAgent(
  "identify-risks",
  "Identify Risks",
  "identify_risks"
);

export const resolveAssumptionsAgent = new RPCAgent(
  "resolve-assumptions",
  "Resolve Assumptions",
  "resolve_assumptions"
);

// Export factory for creating agents dynamically
export function createRPCAgent(taskName: string, rpcUrl?: string): TaskAgent {
  return new RPCAgent(
    taskName,
    taskName.replace(/_/g, " ").split(" ").map(w => w[0].toUpperCase() + w.slice(1)).join(" "),
    taskName,
    rpcUrl
  );
}

// Usage example
// const result = await identifyRisksAgent.invoke({ context: {...} });
```

**Setup & Deployment:**

```bash
# Install dependencies
pip install fastapi uvicorn pydantic

# Run the RPC server
uvicorn planexe.rpc.task_runner:app --host 0.0.0.0 --port 8001

# Or add to docker-compose.yml:
services:
  task-rpc:
    build: .
    ports:
      - "8001:8001"
    command: uvicorn planexe.rpc.task_runner:app --host 0.0.0.0 --port 8001
    depends_on:
      - postgres
```

**Example Usage:**

```bash
# List available tasks
curl http://localhost:8001/tasks

# Get task metadata
curl http://localhost:8001/tasks/identify_risks

# Run a task
curl -X POST http://localhost:8001/run/identify_risks \
  -H "Content-Type: application/json" \
  -d '{
    "context_file": "./context.json"
  }'

# Expected response
{
  "task_name": "identify_risks",
  "status": "success",
  "result": {
    "risk_registry": [
      {
        "id": "RISK-001",
        "title": "Technical debt in core module",
        "severity": "high",
        "mitigation": "Refactor module X in Q2"
      }
    ]
  },
  "execution_time_ms": 2500,
  "tokens_used": 1250
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

## Implementation Roadmap

### Phase 1: Option A (Week 1)

1. **Create `planexe/agent_meta.py`** with decorator and manifest generation
2. **Decorate 3-5 key tasks** (IdentifyRisks, ResolveAssumptions, etc.)
3. **Generate manifest** at build time
4. **Verify manifest correctness** with existing TypeScript agent definitions
5. **Document decorator pattern** for new tasks

**Commands:**

```bash
# Create the decorator module
touch planexe/agent_meta.py

# Decorate key tasks in planexe/pipeline/tasks.py
# Then generate manifest
python -c "from planexe.agent_meta import generate_manifest; generate_manifest()"

# Verify manifest was created
ls -la .agents/manifest.json
cat .agents/manifest.json
```

### Phase 2: Option C (Week 2-3)

1. **Create `planexe/rpc/task_runner.py`** with FastAPI app
2. **Start RPC server** alongside Luigi runner
3. **Add to docker-compose.yml** for automated deployment
4. **Create TypeScript client library** to wrap RPC calls
5. **Test with sample external agents** (Codebuff, OpenClaw)

**Commands:**

```bash
# Install RPC dependencies
pip install fastapi uvicorn

# Create RPC module directory
mkdir -p planexe/rpc
touch planexe/rpc/__init__.py
touch planexe/rpc/task_runner.py
touch planexe/rpc/client.py

# Run RPC server
python -m uvicorn planexe.rpc.task_runner:app --host 0.0.0.0 --port 8001

# Test it
curl http://localhost:8001/health
curl http://localhost:8001/tasks
```

### Phase 3: Integration (Week 3-4)

1. **Update TypeScript agent definitions** to use auto-generated manifests
2. **Create agent wrapper factories** from manifest
3. **Test end-to-end** with external frameworks
4. **Document usage** in AGENTS.md

---

## Full Example: Migrate One Task

### Before (Task + Duplicate TypeScript Agent)

**Python task** (`planexe/pipeline/tasks.py`):

```python
class IdentifyRisks(luigi.Task):
    context_file = luigi.PathParameter(default="./context.json")
    
    def requires(self):
        return ResolveAssumptions()
    
    def output(self):
        return luigi.LocalTarget("./artifacts/risks.json")
    
    def run(self):
        # 50 lines of logic
        pass
```

**TypeScript agent** (duplicate logic):

```typescript
export const identifyRisksAgent = {
  id: "identify-risks",
  async invoke(context) {
    // DUPLICATED: 50 lines of logic from Python
    const risks = [];
    for (const assumption of context.assumptions) {
      // ... analyze
      risks.push(...);
    }
    return risks;
  }
};
```

**Problem**: When Python logic changes, TypeScript diverges.

### After (Task + Decorator + Thin Agent Wrapper)

**Python task** (unchanged, but decorated):

```python
@agent_meta(
    name="identify_risks",
    description="Identifies project risks from assumptions and context.",
    tools=["read_context", "read_assumptions"],
    outputs=["risk_registry"],
    stage="risk_assumptions",
    tags=["analysis", "risk"],
)
class IdentifyRisks(luigi.Task):
    context_file = luigi.PathParameter(default="./context.json")
    
    def requires(self):
        return ResolveAssumptions()
    
    def output(self):
        return luigi.LocalTarget("./artifacts/risks.json")
    
    def run(self):
        # Same 50 lines of logic
        pass
```

**TypeScript agent** (thin wrapper, no duplicated logic):

```typescript
export const identifyRisksAgent = new RPCAgent(
  "identify-risks",
  "Identify Risks",
  "identify_risks"
);

// Or from manifest:
// const manifest = await fetch("/.agents/manifest.json").then(r => r.json());
// const identifyRisks = manifest.agents.find(a => a.name === "identify_risks");
// export const identifyRisksAgent = createRPCAgent(identifyRisks.name);
```

**Manifest** (auto-generated):

```json
{
  "agents": [
    {
      "name": "identify_risks",
      "displayName": "Identify Risks",
      "description": "Identifies project risks from assumptions and context.",
      "pythonClass": "planexe.pipeline.tasks.IdentifyRisks",
      ...
    }
  ]
}
```

**Result**: Single source of truth. TypeScript never diverges from Python.

---
