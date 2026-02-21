# Post-Plan Orchestration Layer: Design Proposal

**Status**: Proposal  
**Author**: VoynichLabs  
**Created**: 2026-02-21  
**Target**: PlanExe's post-plan enrichment swarm

---

## The Problem

Writing files + git commits is not orchestration. It's just persistence.

Currently, PlanExe's post-plan agent swarm lacks a central orchestration layer. What we have is:
- **Isolated agent invocations** with no visibility into sequencing or parallelization
- **File-based state passing** (reading/writing to disk) — inefficient and error-prone
- **No cross-agent context** beyond what's in committed files
- **No failure recovery** or retry logic
- **No credit metering per agent** — just batch processing
- **No visibility** into what's running, what failed, or what's blocking

The result: agents run in a loose, uncoordinated fashion. A plan gets processed, agents touch it, files get written, commits happen — but there's no orchestrator deciding who runs next, in what order, or with what input.

## The Opportunity

**Codebuff solved this problem.** They built a central orchestrator that:
1. **Coordinates multiple specialized agents** (File Picker, Planner, Editor, Reviewer)
2. **Maintains agent state** across runs (not just files)
3. **Streams tool calls and results** to clients in real-time
4. **Handles failures gracefully** with retry logic
5. **Meters credits per agent invocation** for cost tracking
6. **Supports programmatic agents** that generate steps rather than just prompting

This proposal adapts Codebuff's orchestration patterns for PlanExe's enrichment swarm.

---

## Codebuff's Orchestration Architecture

### The Core Loop: `loopAgentSteps`

Codebuff's orchestrator is a **synchronous step loop** that:

1. **Instantiates an agent** with a template (model, tools, instructions)
2. **Streams LLM output** to clients in real-time
3. **Parses tool calls** from the stream (not waiting for completion)
4. **Executes tools** in order (respecting dependencies)
5. **Collects results** into messages
6. **Loops** if the agent hasn't called `end_turn`
7. **Spawns subagents** if needed via the `spawn_agents` tool

```
loopAgentSteps({
  agentTemplate: AgentTemplate,
  agentState: AgentState,
  prompt: string,
  fileContext: ProjectFileContext,
  ...
}) → {
  while (!stepsComplete && stepNumber < maxSteps):
    - Call runAgentStep() to invoke the LLM
    - Parse tool calls from stream
    - Execute tools (including spawn_agents)
    - Update agent state
    - Return to loop
}
```

### Agent Templates: Declarative Agent Definitions

Each agent is defined via an **`AgentTemplate`** that specifies:

```typescript
{
  id: string                          // Unique identifier
  displayName: string
  model: string                       // "openai/gpt-4", "anthropic/claude-3-opus", etc.
  toolNames: string[]                 // Available tools
  instructionsPrompt: string          // System instructions
  spawnableAgents: AgentTemplateType[] // Which agents this agent can spawn
  handleSteps?: StepGenerator        // Programmatic step generator (for custom workflows)
}
```

**Key insight**: Agents are **composable**. A parent agent can spawn child agents by specifying which ones are allowed in `spawnableAgents`.

### Tool Execution: Streaming + On-Demand

Tools are executed as soon as they're parsed from the LLM stream:

1. **`processStream()`** parses XML/tool-call blocks in real-time
2. **`executeToolCall()`** runs the tool handler
3. **Results are added back to the message history**
4. **The agent continues** with the result in context

This is **streaming-aware** — clients see partial output before the tool even runs.

### State Management: Beyond Files

Codebuff maintains several layers of state:

- **`AgentState`**: Current step number, message history, subgoals, results
- **`FileContext`**: Project structure, file contents, knowledge files, agent templates
- **`ProjectFileContext`**: Aggregated context (code map, file tree, git state, etc.)
- **Message History**: Full conversation (assistant + tool results), used for context windows

State is **serializable** for database storage but **immutable during a step** (new state on each iteration).

### Failure Handling & Retries

- **Tool call parsing errors** → Logged, error message sent back to agent
- **Tool execution errors** → Caught, error message added to context
- **LLM failures** → Retried up to 3 times (configurable)
- **Abort signals** → Graceful cancellation via `AbortSignal`

### Spawning Subagents

When an agent calls `spawn_agents(agentIds, prompt, ...)`:

1. **Validate** the child agent is in `spawnableAgents`
2. **Look up** the child's template (local → database cache → database)
3. **Call `loopAgentSteps()` recursively** with the child's template
4. **Collect child results** and return them to parent

This creates a **tree of agent runs**, all tracked in the database.

### Credit Metering

Each agent invocation is tracked with:
- **Start time** (`startAgentRun`)
- **Step count** (`addAgentStep` for each iteration)
- **Credit consumption** (calculated per LLM call, per tool execution)
- **Finish status** (`finishAgentRun` with total credits)

This enables **per-agent billing** and **quota enforcement**.

---

## Proposed PlanExe Orchestration Layer

### 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ PlanExe Central Orchestrator (Coordinator)              │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Plan Artifact Ingestion                            │ │
│  │ (receives enrichment request + plan)               │ │
│  └────────────┬───────────────────────────────────────┘ │
│               │                                          │
│  ┌────────────▼───────────────────────────────────────┐ │
│  │ Agent Registry & Scheduling                        │ │
│  │ (knows which enrichment agents are available)      │ │
│  └────────────┬───────────────────────────────────────┘ │
│               │                                          │
│  ┌────────────▼───────────────────────────────────────┐ │
│  │ Orchestration Loop (adaptive scheduling)           │ │
│  │ - Check agent availability                         │ │
│  │ - Execute enrichment agents in sequence/parallel   │ │
│  │ - Wait for results                                 │ │
│  │ - Update plan artifact                             │ │
│  │ - Handle failures & retries                        │ │
│  └────────────┬───────────────────────────────────────┘ │
│               │                                          │
│  ┌────────────▼───────────────────────────────────────┐ │
│  │ State Management & Persistence                     │ │
│  │ (plan artifact, step results, agent context)       │ │
│  └────────────┬───────────────────────────────────────┘ │
│               │                                          │
│  ┌────────────▼───────────────────────────────────────┐ │
│  │ Credit Metering & Billing                          │ │
│  │ (track cost per agent, per enrichment)             │ │
│  └───────────────────────────────────────────────────── │
└─────────────────────────────────────────────────────────┘
```

### 2. The Orchestration Loop

Adapt Codebuff's `loopAgentSteps` pattern for post-plan enrichment:

```typescript
async function orchestrateEnrichmentSwarm(params: {
  planArtifact: PlanArtifact
  enrichmentRequest: EnrichmentRequest
  registry: AgentRegistry
  metering: CreditMeter
  state: OrchestrationState
}) {
  let stepNumber = 0
  const maxSteps = 20  // Prevent infinite loops

  while (!state.isComplete && stepNumber < maxSteps) {
    stepNumber++

    // 1. Select next agent(s) to run
    const nextAgents = registry.selectAgents({
      current: state.currentAgents,
      completed: state.completedAgents,
      planState: planArtifact.currentState,
    })

    if (!nextAgents.length) break  // No more agents to run

    // 2. Prepare context (plan + previous results)
    const context = buildContext({
      plan: planArtifact,
      stepResults: state.results,
      agentOutputs: state.agentOutputs,
    })

    // 3. Invoke agents (sequence or parallel)
    const results = await Promise.all(
      nextAgents.map(agent =>
        invokeAgent({
          agent,
          context,
          onProgress: (chunk) => state.emit('progress', chunk),
        })
      )
    )

    // 4. Meter credits
    for (const { agent, result } of zip(nextAgents, results)) {
      await metering.consumeCredits({
        agentId: agent.id,
        credits: result.creditsUsed,
        userId: enrichmentRequest.userId,
      })
    }

    // 5. Update state
    state.completedAgents.push(...nextAgents.map(a => a.id))
    state.results.push(...results)

    // 6. Update plan artifact with enrichments
    planArtifact = applyEnrichments(planArtifact, results)

    // 7. Check for completion or failure
    if (state.shouldAbort || results.some(r => r.status === 'failed')) {
      state.isComplete = true
    }
  }

  // 8. Final state persistence
  await persistFinalState({
    orchestrationId: state.id,
    planArtifact,
    state,
  })

  return { planArtifact, state }
}
```

### 3. Agent Registration & Discovery

Enrichment agents register themselves with the orchestrator:

```typescript
interface EnrichmentAgentDefinition {
  id: string                      // e.g., "security-review", "performance-analysis"
  displayName: string
  description: string
  
  // What this agent needs
  inputSchema: {
    fields: string[]              // Required fields from plan
    context: string[]             // Required context sections
  }
  
  // What this agent produces
  outputSchema: {
    enrichmentType: string        // e.g., "security-findings"
    fields: Record<string, any>
  }
  
  // Scheduling
  dependencies: string[]          // Agents that must complete first
  runCondition?: (plan, state) => boolean  // Optional gate function
  parallel: boolean               // Can run in parallel with others?
  timeout: number                 // Max execution time (ms)
  maxRetries: number
  
  // Resource info
  model: string                   // LLM model
  estimatedTokens: number
  costPerRun: number              // Fallback if token-based fails
}
```

### 4. Plan Artifact Versioning & Flow

The plan artifact flows through agents with incremental enrichment:

```typescript
interface PlanArtifact {
  id: string
  version: number                 // Incremented per orchestration step
  
  // Original plan
  plan: Plan
  
  // Enrichments (accumulated from agents)
  enrichments: {
    [agentId: string]: AgentEnrichment
  }
  
  // Metadata
  createdAt: number
  lastUpdatedAt: number
  orchestrationId: string         // Link back to orchestration run
  
  // Status tracking
  status: 'pending' | 'enriching' | 'complete' | 'failed'
  failureReason?: string
}

interface AgentEnrichment {
  agentId: string
  timestamp: number
  status: 'success' | 'failed' | 'partial'
  
  data: {
    [key: string]: any            // Agent-specific output
  }
  
  metadata: {
    inputHash: string             // For deduplication
    tokensUsed: number
    creditsCharged: number
    executionTimeMs: number
  }
}
```

### 5. Context Passing (Not Just Files)

Instead of file reads/writes, use a **shared context object**:

```typescript
interface OrchestrationContext {
  // Plan reference
  planId: string
  planVersion: number
  
  // Accumulated state
  priorEnrichments: Record<string, AgentEnrichment>
  agentOutputs: Record<string, any>
  
  // Resource context
  fileContextSnapshot: {
    fileTree: string
    changedFiles: string[]
    gitDiff: string
  }
  
  // User/billing context
  userId: string
  costBudget: number
  creditsRemaining: number
  
  // Execution context
  orchestrationId: string
  runId: string
  stepNumber: number
}
```

### 6. Failure Handling & Retries

```typescript
async function invokeAgentWithRetry(params: {
  agent: EnrichmentAgentDefinition
  context: OrchestrationContext
  maxRetries: number
}) {
  let attempt = 0
  let lastError

  while (attempt < maxRetries) {
    try {
      const result = await invokeAgent({ agent, context })
      return { status: 'success', result }
    } catch (error) {
      lastError = error
      attempt++

      // Backoff before retry
      if (attempt < maxRetries) {
        await sleep(1000 * Math.pow(2, attempt))
      }
    }
  }

  return {
    status: 'failed',
    error: lastError,
    attempts: maxRetries,
  }
}
```

### 7. Credit Metering (Per-Agent Billing)

```typescript
interface CreditTransaction {
  orchestrationId: string
  agentId: string
  stepNumber: number
  
  costs: {
    llmTokens: number             // # tokens × model rate
    toolExecutions: number        // # tool calls × rate
    baseCharge: number            // Fixed cost per invocation
  }
  
  totalCredits: number
  timestamp: number
}

async function meterCredits(params: {
  agent: EnrichmentAgentDefinition
  result: AgentResult
  userId: string
  costMode?: string              // "token-based" | "fixed" | "hybrid"
}) {
  const credits = calculateCredits({
    tokensUsed: result.metrics.tokensUsed,
    baseCharge: agent.costPerRun,
    costMode,
  })

  await consumeCreditsWithFallback({
    userId,
    credits,
    fallback: agent.costPerRun,  // If token count unavailable
  })

  return { creditsCharged: credits }
}
```

### 8. Integration with Railway Replicas

For horizontal scaling, partition enrichment work across replicas:

```typescript
interface ReplicaPartitionStrategy {
  // Option 1: By agent type
  agentAssignment: {
    [replicaId: string]: string[]  // Agent IDs assigned to this replica
  }
  
  // Option 2: By plan partition
  planPartitions: {
    [replicaId: string]: {
      planIds: string[]            // Which plans this replica handles
    }
  }
  
  // Option 3: By load (dynamic)
  dynamic: {
    maxAgentsPerReplica: number
    loadBalancerUrl: string
  }
}

// Replica receives work item and processes it
async function replicaOrchestrationWorker(params: {
  orchestrationId: string
  replicaId: string
  gatewayUrl: string             // PlanExe central coordination
}) {
  // 1. Check in with coordinator
  const work = await fetch(
    `${gatewayUrl}/api/orchestrations/${orchestrationId}/next-work`,
    { replicaId }
  )

  if (!work) return  // No work for this replica

  // 2. Execute locally
  const result = await orchestrateEnrichmentSwarm(work)

  // 3. Report back to coordinator
  await fetch(
    `${gatewayUrl}/api/orchestrations/${orchestrationId}/report`,
    {
      method: 'POST',
      body: JSON.stringify({ result, replicaId }),
    }
  )
}
```

### 9. Visibility & Monitoring

Expose orchestration state to clients in real-time:

```typescript
interface OrchestrationObservability {
  // WebSocket stream for real-time updates
  subscribe(orchestrationId: string): AsyncIterable<Event> {
    // Emits:
    // - step_started
    // - agent_invoked
    // - tool_called
    // - agent_completed
    // - enrichment_applied
    // - step_completed
    // - orchestration_failed
  }

  // REST API for status snapshots
  getStatus(orchestrationId: string): {
    orchestrationId: string
    status: 'pending' | 'running' | 'complete' | 'failed'
    stepNumber: number
    currentAgents: string[]
    completedAgents: string[]
    results: {
      [agentId: string]: AgentEnrichment
    }
    creditsUsed: number
    creditsRemaining: number
    estimatedTimeRemaining: number
  }

  // Audit log
  getLog(orchestrationId: string, filters?: {
    agentId?: string
    status?: string
  }): Promise<Event[]>
}
```

---

## Implementation Roadmap

### Phase 1: Core Loop (Week 1-2)
- [ ] Implement `orchestrateEnrichmentSwarm()` function
- [ ] Define `EnrichmentAgentDefinition` schema
- [ ] Build agent registry and lookup
- [ ] Simple sequential execution

### Phase 2: State Management (Week 2-3)
- [ ] Implement `OrchestrationContext` and state persistence
- [ ] Plan artifact versioning and enrichment stacking
- [ ] Message history for cross-agent context

### Phase 3: Execution & Metering (Week 3-4)
- [ ] Tool-based agent invocation (like Codebuff)
- [ ] Credit metering per agent
- [ ] Failure handling and retries

### Phase 4: Scaling (Week 4-5)
- [ ] Railway Replica integration
- [ ] Load balancing across replicas
- [ ] Distributed work queue

### Phase 5: Observability (Week 5-6)
- [ ] WebSocket events for real-time progress
- [ ] Dashboard for monitoring orchestration runs
- [ ] Audit logging and debugging tools

---

## Key Differences from Codebuff

| Aspect | Codebuff | PlanExe Proposed |
|--------|----------|-----------------|
| **Input** | User prompt | Plan artifact (pre-structured) |
| **Output** | Modified codebase | Enriched plan metadata |
| **Agents** | File Picker, Planner, Editor, Reviewer | Modular enrichment agents |
| **Scaling** | Single instance (cloud) | Railway Replicas (distributed) |
| **State** | Message history | Plan artifact + enrichments |
| **Sequencing** | LLM-driven (agent decides tools) | Registry-driven (orchestrator decides agents) |

The key insight: **Codebuff's orchestrator is LLM-centric** (agents request tools via prompting), while **PlanExe's should be registry-centric** (the orchestrator explicitly decides which agents run when).

---

## Benefits

1. **Coordination**: Central visibility into which agents run, in what order, with what inputs
2. **Efficiency**: Context passed via message objects, not file I/O
3. **Reliability**: Retry logic, failure handling, graceful degradation
4. **Cost Control**: Per-agent credit metering, quota enforcement
5. **Scalability**: Replica-based horizontal scaling, work distribution
6. **Observability**: Real-time event streams, audit logs, status dashboards
7. **Composability**: Agents register themselves; orchestrator discovers and schedules

---

## References

- Codebuff Repository: https://github.com/VoynichLabs/codebuff
- Codebuff Agent Runtime: `packages/agent-runtime/src/`
- Codebuff Main Loop: `run-agent-step.ts` → `loopAgentSteps()`
- Codebuff Templates: `templates/` (agent definitions)
- Codebuff Tool Execution: `tools/tool-executor.ts`, `tools/stream-parser.ts`

---

## Questions for Discussion

1. Should the orchestrator be **event-driven** (pull-based registry polling) or **queue-based** (agents enqueue work)?
2. How should we **handle partial enrichments** if an agent times out or fails partway through?
3. Should agents be **sequential by default** or **parallel-first** with explicit dependency ordering?
4. Do we want **agent composition** (agents can spawn subagents) like Codebuff, or just flat scheduling?
5. How should we integrate with existing **PlanExe plugins/extensions** if they exist?

---

## Complete Implementation Guide

### Setup & Installation

```bash
# Clone the repo and install dependencies
git clone https://github.com/VoynichLabs/PlanExe2026.git
cd PlanExe2026

# Install Node dependencies
npm install

# Create the orchestration module directory
mkdir -p src/orchestration

# Install TypeScript types
npm install --save-dev @types/node @types/express typescript
npm install express axios uuid dotenv
```

### File: `src/orchestration/types.ts`

Complete type definitions for the orchestration layer:

```typescript
// Core types for orchestration
export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed' | 'timeout';

export interface EnrichmentAgentDefinition {
  id: string;
  displayName: string;
  description: string;
  
  inputSchema: {
    fields: string[];
    context: string[];
  };
  
  outputSchema: {
    enrichmentType: string;
    fields: Record<string, any>;
  };
  
  dependencies: string[];
  runCondition?: (plan: PlanArtifact, state: OrchestrationState) => boolean;
  parallel: boolean;
  timeout: number;
  maxRetries: number;
  
  model: string;
  estimatedTokens: number;
  costPerRun: number;
}

export interface PlanArtifact {
  id: string;
  version: number;
  plan: any;
  
  enrichments: {
    [agentId: string]: AgentEnrichment;
  };
  
  createdAt: number;
  lastUpdatedAt: number;
  orchestrationId: string;
  
  status: 'pending' | 'enriching' | 'complete' | 'failed';
  failureReason?: string;
}

export interface AgentEnrichment {
  agentId: string;
  timestamp: number;
  status: AgentStatus;
  
  data: Record<string, any>;
  
  metadata: {
    inputHash: string;
    tokensUsed: number;
    creditsCharged: number;
    executionTimeMs: number;
  };
}

export interface OrchestrationContext {
  planId: string;
  planVersion: number;
  priorEnrichments: Record<string, AgentEnrichment>;
  agentOutputs: Record<string, any>;
  
  fileContextSnapshot: {
    fileTree: string;
    changedFiles: string[];
    gitDiff: string;
  };
  
  userId: string;
  costBudget: number;
  creditsRemaining: number;
  
  orchestrationId: string;
  runId: string;
  stepNumber: number;
}

export interface OrchestrationState {
  id: string;
  planId: string;
  status: 'pending' | 'running' | 'complete' | 'failed';
  stepNumber: number;
  
  currentAgents: string[];
  completedAgents: string[];
  failedAgents: string[];
  results: AgentEnrichment[];
  agentOutputs: Record<string, any>;
  
  creditsUsed: number;
  createdAt: number;
  updatedAt: number;
}

export interface CreditTransaction {
  orchestrationId: string;
  agentId: string;
  stepNumber: number;
  
  costs: {
    llmTokens: number;
    toolExecutions: number;
    baseCharge: number;
  };
  
  totalCredits: number;
  timestamp: number;
}
```

### File: `src/orchestration/orchestrator.ts`

Main orchestration loop:

```typescript
import { v4 as uuidv4 } from 'uuid';
import {
  EnrichmentAgentDefinition,
  PlanArtifact,
  OrchestrationContext,
  OrchestrationState,
  AgentEnrichment,
  AgentStatus,
} from './types';

export class EnrichmentOrchestrator {
  private agents: Map<string, EnrichmentAgentDefinition> = new Map();
  private state: OrchestrationState;
  private context: OrchestrationContext;

  constructor(
    private planArtifact: PlanArtifact,
    agents: EnrichmentAgentDefinition[],
    private metering: CreditMeter
  ) {
    agents.forEach(agent => this.agents.set(agent.id, agent));
    
    this.state = {
      id: uuidv4(),
      planId: planArtifact.id,
      status: 'pending',
      stepNumber: 0,
      currentAgents: [],
      completedAgents: [],
      failedAgents: [],
      results: [],
      agentOutputs: {},
      creditsUsed: 0,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    
    this.context = this.buildContext();
  }

  private buildContext(): OrchestrationContext {
    return {
      planId: this.planArtifact.id,
      planVersion: this.planArtifact.version,
      priorEnrichments: this.planArtifact.enrichments,
      agentOutputs: this.state.agentOutputs,
      fileContextSnapshot: {
        fileTree: '',
        changedFiles: [],
        gitDiff: '',
      },
      userId: 'system',
      costBudget: 1000,
      creditsRemaining: 1000,
      orchestrationId: this.state.id,
      runId: uuidv4(),
      stepNumber: 0,
    };
  }

  async orchestrateEnrichmentSwarm(maxSteps: number = 20): Promise<OrchestrationState> {
    let stepNumber = 0;

    while (!this.isComplete() && stepNumber < maxSteps) {
      stepNumber++;
      this.state.stepNumber = stepNumber;

      console.log(`=== Orchestration Step ${stepNumber} ===`);

      // Select next agents to run
      const nextAgents = this.selectAgents();
      if (nextAgents.length === 0) {
        console.log('No more agents ready to run');
        break;
      }

      console.log(`Running agents: ${nextAgents.map(a => a.id).join(', ')}`);

      // Invoke agents sequentially (or parallel if configured)
      const results = await Promise.all(
        nextAgents.map(agent => this.invokeAgent(agent))
      );

      // Process results
      for (const result of results) {
        if (result.status === 'completed') {
          this.state.completedAgents.push(result.agentId);
        } else if (result.status === 'failed') {
          this.state.failedAgents.push(result.agentId);
        }

        // Meter credits
        const credits = await this.metering.calculateCredits({
          agentId: result.agentId,
          tokensUsed: result.metadata.tokensUsed,
          baseCharge: this.agents.get(result.agentId)?.costPerRun || 0,
        });

        this.state.creditsUsed += credits;
        this.context.creditsRemaining -= credits;

        // Store enrichment
        this.planArtifact.enrichments[result.agentId] = result;
        this.state.results.push(result);
      }

      this.state.updatedAt = Date.now();
    }

    // Mark orchestration complete
    this.state.status = this.state.failedAgents.length === 0 ? 'complete' : 'failed';
    this.planArtifact.status = this.state.status === 'complete' ? 'complete' : 'failed';
    this.planArtifact.lastUpdatedAt = Date.now();

    return this.state;
  }

  private selectAgents(): EnrichmentAgentDefinition[] {
    const ready: EnrichmentAgentDefinition[] = [];

    for (const agent of this.agents.values()) {
      // Skip if already completed or failed
      if (
        this.state.completedAgents.includes(agent.id) ||
        this.state.failedAgents.includes(agent.id)
      ) {
        continue;
      }

      // Check if all dependencies are met
      const depsMetched = agent.dependencies.every(dep =>
        this.state.completedAgents.includes(dep)
      );

      if (!depsMetched) {
        continue;
      }

      // Check run condition if provided
      if (agent.runCondition && !agent.runCondition(this.planArtifact, this.state)) {
        continue;
      }

      ready.push(agent);
    }

    return ready;
  }

  private async invokeAgent(agent: EnrichmentAgentDefinition): Promise<AgentEnrichment> {
    const startTime = Date.now();

    try {
      console.log(`Invoking agent: ${agent.id}`);

      // Call the agent via HTTP or RPC
      const response = await invokeAgentRPC(agent.id, this.context);

      const executionTimeMs = Date.now() - startTime;

      return {
        agentId: agent.id,
        timestamp: Date.now(),
        status: 'completed',
        data: response,
        metadata: {
          inputHash: hashContext(this.context),
          tokensUsed: response.tokensUsed || 0,
          creditsCharged: 0, // Will be calculated
          executionTimeMs,
        },
      };
    } catch (error) {
      console.error(`Agent ${agent.id} failed:`, error);

      return {
        agentId: agent.id,
        timestamp: Date.now(),
        status: 'failed',
        data: { error: String(error) },
        metadata: {
          inputHash: hashContext(this.context),
          tokensUsed: 0,
          creditsCharged: 0,
          executionTimeMs: Date.now() - startTime,
        },
      };
    }
  }

  private isComplete(): boolean {
    const totalAgents = this.agents.size;
    const completedOrFailed =
      this.state.completedAgents.length + this.state.failedAgents.length;
    return completedOrFailed === totalAgents;
  }

  getState(): OrchestrationState {
    return this.state;
  }

  getPlanArtifact(): PlanArtifact {
    return this.planArtifact;
  }
}

// Helper: invoke agent via RPC
async function invokeAgentRPC(agentId: string, context: OrchestrationContext): Promise<any> {
  const response = await fetch(`http://localhost:8080/api/agents/${agentId}/invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(context),
  });

  if (!response.ok) {
    throw new Error(`Agent invocation failed: ${response.statusText}`);
  }

  return response.json();
}

// Helper: hash context for deduplication
function hashContext(context: OrchestrationContext): string {
  // Implement a hash of the context
  return `hash-${Date.now()}`;
}

// Credit meter
export class CreditMeter {
  async calculateCredits(params: {
    agentId: string;
    tokensUsed: number;
    baseCharge: number;
  }): Promise<number> {
    // Token-based pricing: e.g., 0.01 credits per token
    const tokenCost = params.tokensUsed * 0.01;
    return tokenCost + params.baseCharge;
  }
}
```

### File: `src/orchestration/api.ts`

Express API for orchestration:

```typescript
import express, { Request, Response } from 'express';
import { EnrichmentOrchestrator, CreditMeter } from './orchestrator';
import { PlanArtifact, EnrichmentAgentDefinition, OrchestrationState } from './types';

export const createOrchestrationAPI = (
  agentRegistry: Map<string, EnrichmentAgentDefinition>
) => {
  const router = express.Router();

  // POST /orchestrate - Start a new orchestration run
  router.post('/orchestrate', async (req: Request, res: Response) => {
    try {
      const { planArtifact } = req.body;

      if (!planArtifact || !planArtifact.id) {
        return res.status(400).json({ error: 'Missing planArtifact' });
      }

      const agents = Array.from(agentRegistry.values());
      const metering = new CreditMeter();
      const orchestrator = new EnrichmentOrchestrator(planArtifact, agents, metering);

      const state = await orchestrator.orchestrateEnrichmentSwarm();

      res.json({
        orchestrationId: state.id,
        status: state.status,
        completedAgents: state.completedAgents,
        failedAgents: state.failedAgents,
        creditsUsed: state.creditsUsed,
        planArtifact: orchestrator.getPlanArtifact(),
      });
    } catch (error) {
      console.error('Orchestration error:', error);
      res.status(500).json({ error: String(error) });
    }
  });

  // GET /orchestrate/:orchestrationId - Get orchestration status
  router.get('/orchestrate/:orchestrationId', async (req: Request, res: Response) => {
    // Implementation: fetch from database
    res.json({ message: 'Get orchestration status' });
  });

  // GET /agents - List all registered agents
  router.get('/agents', (req: Request, res: Response) => {
    const agents = Array.from(agentRegistry.values()).map(a => ({
      id: a.id,
      displayName: a.displayName,
      description: a.description,
      timeout: a.timeout,
      costPerRun: a.costPerRun,
    }));

    res.json({ agents });
  });

  // POST /agents - Register a new agent
  router.post('/agents', (req: Request, res: Response) => {
    const { agent } = req.body;

    if (!agent.id || !agent.displayName) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    agentRegistry.set(agent.id, agent);
    res.status(201).json({ agent });
  });

  return router;
};
```

### File: `src/index.ts`

Main application setup:

```typescript
import express, { Express } from 'express';
import { createOrchestrationAPI } from './orchestration/api';
import { EnrichmentAgentDefinition } from './orchestration/types';

const app: Express = express();
const PORT = process.env.PORT || 8080;

// Middleware
app.use(express.json());

// Agent registry (in-memory for now, can be backed by database)
const agentRegistry: Map<string, EnrichmentAgentDefinition> = new Map([
  [
    'security-review',
    {
      id: 'security-review',
      displayName: 'Security Review Agent',
      description: 'Reviews plan for security implications and risk mitigation strategies',
      inputSchema: { fields: ['plan'], context: ['architecture', 'requirements'] },
      outputSchema: { enrichmentType: 'security-findings', fields: { issues: [], recommendations: [] } },
      dependencies: [],
      parallel: false,
      timeout: 120000,
      maxRetries: 2,
      model: 'gpt-4',
      estimatedTokens: 2000,
      costPerRun: 0.50,
    },
  ],
  [
    'performance-analysis',
    {
      id: 'performance-analysis',
      displayName: 'Performance Analysis Agent',
      description: 'Analyzes plan for performance bottlenecks and optimization opportunities',
      inputSchema: { fields: ['plan'], context: ['architecture', 'metrics'] },
      outputSchema: { enrichmentType: 'performance-findings', fields: { bottlenecks: [], recommendations: [] } },
      dependencies: ['security-review'],
      parallel: false,
      timeout: 120000,
      maxRetries: 2,
      model: 'gpt-4',
      estimatedTokens: 1500,
      costPerRun: 0.40,
    },
  ],
]);

// Mount orchestration API
app.use('/api', createOrchestrationAPI(agentRegistry));

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', uptime: process.uptime() });
});

// Error handling middleware
app.use((err: any, req: any, res: any, next: any) => {
  console.error('Error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(PORT, () => {
  console.log(`Orchestration server running on port ${PORT}`);
});
```

### File: `docker-compose.yml`

Docker setup for orchestration:

```yaml
version: '3.8'

services:
  orchestration:
    build:
      context: .
      dockerfile: Dockerfile.orchestration
    ports:
      - "8080:8080"
    environment:
      NODE_ENV: production
      DATABASE_URL: postgres://planexe:planexe@postgres:5432/orchestration
      REDIS_URL: redis://redis:6379
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      - postgres
      - redis
    volumes:
      - ./src:/app/src
    command: npm run dev

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: planexe
      POSTGRES_PASSWORD: planexe
      POSTGRES_DB: orchestration
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### Setup Commands

```bash
# Install dependencies
npm install

# Compile TypeScript
npx tsc

# Run locally
npm run dev

# Run with Docker
docker-compose up -d

# Create database schema
npx prisma migrate dev

# Seed with initial agents
node scripts/seed-agents.js
```

### Environment Configuration

Create `.env`:

```
NODE_ENV=development
PORT=8080
DATABASE_URL=postgres://planexe:planexe@localhost:5432/orchestration
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Running an Orchestration

```bash
# Start the server
npm run dev

# In another terminal, trigger an orchestration
curl -X POST http://localhost:8080/api/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "planArtifact": {
      "id": "plan-123",
      "version": 1,
      "plan": { "title": "My Plan", "description": "..." },
      "enrichments": {},
      "createdAt": '$(date +%s)'000',
      "lastUpdatedAt": '$(date +%s)'000',
      "orchestrationId": null,
      "status": "pending"
    }
  }'
```

### Expected Output

```json
{
  "orchestrationId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "complete",
  "completedAgents": ["security-review", "performance-analysis"],
  "failedAgents": [],
  "creditsUsed": 0.90,
  "planArtifact": {
    "id": "plan-123",
    "version": 2,
    "enrichments": {
      "security-review": {
        "agentId": "security-review",
        "timestamp": 1708462300000,
        "status": "completed",
        "data": { "issues": [...], "recommendations": [...] },
        "metadata": { "tokensUsed": 2100, "creditsCharged": 0.50, "executionTimeMs": 3500 }
      }
    },
    "status": "complete"
  }
}
```
