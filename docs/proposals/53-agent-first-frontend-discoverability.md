# Proposal 53: Agent-First Frontend Discoverability for PlanExe

## Goal

Make PlanExe discoverable and usable by AI agents (OpenClaw, OpenAI Agents, Codebuff, Claude Code, etc.) via standard protocols and metadata. Enable AI agents to autonomously discover, understand, and integrate with PlanExe as a planning and orchestration tool.

## Problem Statement

PlanExe is a powerful planning orchestrator, but AI agents cannot easily:
1. **Discover** PlanExe's capabilities (what it does, what endpoints exist)
2. **Understand** how to use it (API schemas, tool signatures, authentication)
3. **Integrate** with it (function calling, MCP servers, or direct API calls)
4. **Trust** it (pricing, credit models, rate limits)

This limits PlanExe's reach to agents and orchestrators that require manual integration or discovery via documentation.

## Recommendations

### 1. `llms.txt` – LLM Agent Discovery

**What:** Add `/llms.txt` to both `home.planexe.org` and `mcp.planexe.org` (cloud) and locally for Docker deployments.

**Why:** The `llms.txt` standard (emerging from orchestrator patterns) tells AI agents:
- What PlanExe does (elevator pitch)
- How to generate a plan (API endpoint, MCP endpoint, or local Docker)
- Authentication (API key, MCP auth, or open local)
- Available tools/capabilities (plan generation, status polling, artifact retrieval)
- Credit model and pricing
- Rate limits and quotas

**Content (sample):**

```
# PlanExe - Multi-Step Plan Orchestration & Execution

## What is PlanExe?

PlanExe is an AI-native planning orchestrator that transforms vague goals into detailed, executable multi-step plans. It breaks down complex tasks into subtasks, assigns resource requirements, estimates timelines, and tracks execution state—all via API or MCP.

Designed for:
- AI agents needing structured planning
- Codebuff and Claude Code for code generation planning
- OpenClaw orchestrators for multi-step task decomposition
- LLM-powered automation systems

## API Endpoints

### Cloud (home.planexe.org)

- **POST /api/v1/plans** – Create a new plan (requires API key)
- **GET /api/v1/plans/{planId}** – Fetch plan state and execution trace
- **GET /api/v1/plans/{planId}/artifacts** – Download generated artifacts
- **POST /api/v1/plans/{planId}/run** – Execute the plan
- **GET /api/v1/plans/{planId}/status** – Poll execution status

Base URL: https://home.planexe.org/api/v1
Auth: Bearer <API_KEY> (obtain at https://home.planexe.org/account/api-keys)

### Local Docker

```bash
docker run -p 3000:3000 planexeorg/planexe:latest
Base URL: http://localhost:3000/api/v1
Auth: None (trusted local environment)
```

## MCP Server

PlanExe exposes a Model Context Protocol server for direct integration with OpenAI's Responses API and other MCP-aware agents.

**Cloud MCP endpoint:** https://mcp.planexe.org/sse
**Local Docker MCP:** http://localhost:3001/sse (after enabling MCP mode)

## Tools Available

### plan.generate
Generates a multi-step plan from a goal description.
- Input: goal (string), context (optional), constraints (optional)
- Output: planId, steps, artifacts, estimate

### plan.poll
Polls the execution status of a running plan.
- Input: planId
- Output: status, completedSteps, failedSteps, trace

### plan.artifacts
Lists and downloads generated artifacts from a completed plan.
- Input: planId, artifactId (optional)
- Output: artifacts array with download URLs

## Credit Model

- Plan generation: 10 credits
- Execution per minute: 5 credits
- Artifact download: 1 credit per 100MB
- Free tier: 100 credits/month
- See https://home.planexe.org/pricing for details

## Rate Limits

- 100 plans/hour (cloud)
- 1000 artifact downloads/day
- No rate limits on local Docker

## Support

- Docs: https://docs.planexe.org
- GitHub: https://github.com/PlanExeOrg/PlanExe
- Issues: https://github.com/PlanExeOrg/PlanExe/issues
```

**Implementation:**
- Add `public/llms.txt` to repo (example above)
- Serve from `home.planexe.org/llms.txt` (HTTP static)
- Serve from `mcp.planexe.org/llms.txt`
- Update Docker entrypoint to serve `/llms.txt` locally on port 3000

**Reference:** Orchestrator patterns gist notes that `llms.txt` is how agents discover available skills and MCP servers without manual integration.

---

### 2. OpenAPI / LLM-Optimized Tool Schema

**What:** Expose `/openapi.json` describing PlanExe's API in OpenAPI 3.1 format, with LLM-optimized descriptions.

**Why:** OpenAI's function-calling guide and Responses API expect structured function schemas. LLMs perform better with:
- Clear, detailed descriptions (not just docstring summaries)
- Input/output examples
- Enum values for constrained choices
- Required vs optional fields explicitly marked
- Error codes documented

**Content (sample):**

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "PlanExe API",
    "description": "Multi-step plan generation, execution, and orchestration for AI agents",
    "version": "1.0.0",
    "contact": {
      "url": "https://github.com/PlanExeOrg/PlanExe"
    }
  },
  "servers": [
    {
      "url": "https://home.planexe.org/api/v1",
      "description": "Cloud production"
    },
    {
      "url": "http://localhost:3000/api/v1",
      "description": "Local Docker"
    }
  ],
  "paths": {
    "/plans": {
      "post": {
        "summary": "Generate a multi-step plan",
        "description": "Break down a goal into executable steps, estimate resources, and track dependencies. Use this when you need to decompose a complex task into subtasks with clear success criteria.",
        "operationId": "generatePlan",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "goal": {
                    "type": "string",
                    "description": "The high-level goal to plan for (e.g., 'Build a REST API for a social media platform')"
                  },
                  "context": {
                    "type": "string",
                    "description": "Optional context about constraints, existing systems, or success criteria"
                  },
                  "constraints": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of constraints (e.g., ['must use TypeScript', 'budget < $5000', 'timeline 2 weeks'])"
                  },
                  "model": {
                    "type": "string",
                    "enum": ["gpt-4o", "claude-3-opus", "o1"],
                    "description": "Which planning model to use (affects cost and reasoning depth)"
                  }
                },
                "required": ["goal"],
                "additionalProperties": false
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Plan successfully generated",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "planId": { "type": "string", "format": "uuid" },
                    "goal": { "type": "string" },
                    "steps": {
                      "type": "array",
                      "items": {
                        "type": "object",
                        "properties": {
                          "stepId": { "type": "string" },
                          "description": { "type": "string" },
                          "dependencies": { "type": "array", "items": { "type": "string" } },
                          "estimatedMinutes": { "type": "integer" }
                        }
                      }
                    },
                    "createdAt": { "type": "string", "format": "date-time" }
                  }
                }
              }
            }
          },
          "400": {
            "description": "Invalid goal or constraints"
          }
        }
      }
    },
    "/plans/{planId}": {
      "get": {
        "summary": "Get plan details and execution trace",
        "description": "Fetch the current state of a plan, including completed steps, failures, and execution trace for debugging",
        "operationId": "getPlan",
        "parameters": [
          {
            "name": "planId",
            "in": "path",
            "required": true,
            "schema": { "type": "string", "format": "uuid" }
          }
        ],
        "responses": {
          "200": {
            "description": "Plan details"
          }
        }
      }
    }
  }
}
```

**Implementation:**
- Generate from code (e.g., via `@nestjs/swagger` or OpenAPI decorator libraries)
- Serve at `home.planexe.org/openapi.json`
- Include examples for common use cases (code generation, workflow decomposition)
- Validate against OpenAPI 3.1 spec

**Reference:** OpenAI function-calling guide emphasizes that detailed descriptions help models understand when and how to use tools. The Responses API docs recommend OpenAPI 3.1 as the source of truth for function schemas.

---

### 3. MCP Well-Known Endpoint (`.well-known/mcp.json`)

**What:** Add `/.well-known/mcp.json` describing PlanExe as an MCP server, compatible with OpenAI's MCP connector and orchestrators.

**Why:** OpenAI's tools-connectors-mcp guide and orchestrator patterns show that MCP servers need a discoverable manifest listing available tools, auth requirements, and rate limits.

**Content (sample):**

```json
{
  "version": "1.0",
  "mcp_server": {
    "name": "PlanExe",
    "description": "Multi-step plan generation and execution orchestrator",
    "tools": [
      {
        "name": "plan.generate",
        "description": "Generate a multi-step plan from a goal. Use when decomposing complex tasks.",
        "input_schema": {
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "type": "object",
          "properties": {
            "goal": {
              "type": "string",
              "description": "The goal to plan for"
            },
            "context": {
              "type": "string",
              "description": "Optional context and constraints"
            }
          },
          "required": ["goal"],
          "additionalProperties": false
        },
        "output_schema": {
          "type": "object",
          "properties": {
            "planId": { "type": "string" },
            "steps": { "type": "array" },
            "estimatedDuration": { "type": "string" }
          }
        }
      },
      {
        "name": "plan.poll",
        "description": "Poll the execution status of a running plan",
        "input_schema": {
          "type": "object",
          "properties": {
            "planId": { "type": "string" }
          },
          "required": ["planId"],
          "additionalProperties": false
        }
      },
      {
        "name": "plan.artifacts",
        "description": "Retrieve generated artifacts from a completed plan",
        "input_schema": {
          "type": "object",
          "properties": {
            "planId": { "type": "string" }
          },
          "required": ["planId"],
          "additionalProperties": false
        }
      }
    ]
  },
  "auth": {
    "cloud": {
      "type": "bearer_token",
      "description": "API key from https://home.planexe.org/account/api-keys",
      "header": "Authorization"
    },
    "local_docker": {
      "type": "none",
      "description": "No auth required for localhost Docker"
    }
  },
  "rate_limits": {
    "plans_per_hour": 100,
    "artifact_downloads_per_day": 1000,
    "cost_per_plan_generation": 10,
    "cost_unit": "credits"
  },
  "endpoints": {
    "cloud": "https://mcp.planexe.org/sse",
    "local": "http://localhost:3001/sse"
  }
}
```

**Implementation:**
- Serve at `home.planexe.org/.well-known/mcp.json`
- Keep in sync with OpenAPI schema
- Document in contributing guide for maintainers

**Reference:** OpenClaw architecture shows how Gateway/MCP servers expose their capabilities via manifest endpoints. The MCP spec defines `/.well-known/mcp.json` as the discovery entry point.

---

### 4. `robots.txt` for AI Crawlers

**What:** Update `robots.txt` to allow major AI crawlers and LLM training pipelines, while protecting sensitive routes.

**Why:** Agents like Claude Web, GPTBot, and PerplexityBot use `robots.txt` to understand which content they can index and integrate. This makes PlanExe findable in AI-augmented search and agent training pipelines.

**Content (sample):**

```
# Allow AI crawlers to discover and understand PlanExe
User-agent: GPTBot
Disallow: /admin/
Disallow: /user/*/private/
Allow: /api/
Allow: /docs/
Allow: /llms.txt
Allow: /openapi.json
Allow: /.well-known/mcp.json

User-agent: Claude-Web
Disallow: /admin/
Disallow: /user/*/private/
Allow: /api/
Allow: /docs/
Allow: /llms.txt

User-agent: PerplexityBot
Disallow: /admin/
Allow: /docs/
Allow: /llms.txt

# Standard crawlers
User-agent: *
Disallow: /admin/
Disallow: /user/*/private/
Allow: /api/
Allow: /docs/
```

**Implementation:**
- Update `public/robots.txt`
- Consider allowing `/api/` for schema crawling (safe since no auth-sensitive data)
- Test with Google Search Console and ChatGPT crawlers

**Reference:** Orchestrator patterns note that explicit allow rules in `robots.txt` help agents understand what's available.

---

### 5. Structured Data (JSON-LD) & SEO Meta Tags

**What:** Add schema.org SoftwareApplication markup to homepage and service pages.

**Why:** JSON-LD makes PlanExe discoverable via AI-augmented search engines and helps agents understand what it is without full page parsing.

**Content (sample):**

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "PlanExe",
  "description": "Multi-step plan generation and orchestration for AI agents. Decomposes complex goals into executable steps with resource tracking and dependency management.",
  "url": "https://home.planexe.org",
  "applicationCategory": "DeveloperApplication",
  "offers": {
    "@type": "Offer",
    "price": "10",
    "priceCurrency": "USD",
    "description": "Per plan generation (cloud). Free tier: 100 credits/month"
  },
  "featureList": [
    "Multi-step plan generation",
    "API and MCP integration",
    "Execution tracking",
    "Artifact generation",
    "OpenAI Agents compatible",
    "OpenClaw compatible"
  ],
  "operatingSystem": "Any",
  "softwareVersion": "1.0",
  "downloadUrl": "https://github.com/PlanExeOrg/PlanExe",
  "author": {
    "@type": "Organization",
    "name": "PlanExe"
  },
  "inLanguage": "en"
}
</script>

<!-- Meta tags for social/AI preview -->
<meta property="og:title" content="PlanExe - AI Plan Orchestrator" />
<meta property="og:description" content="Generate, execute, and track multi-step plans via API or MCP. Integrates with OpenAI Agents, Claude, and Codebuff." />
<meta property="og:url" content="https://home.planexe.org" />
<meta property="og:type" content="website" />
<meta name="description" content="PlanExe is an AI-native planning orchestrator that decomposes complex goals into executable multi-step plans with full execution tracking and resource management." />
<meta name="keywords" content="AI planning, orchestration, MCP, API, OpenAI agents, Codebuff, task decomposition" />
```

**Implementation:**
- Add to base layout/template in Next.js/React app
- Update homepage, docs, and API pages
- Use Yoast or similar to validate OpenGraph + structured data

**Reference:** OpenAI's new tools blog emphasizes that agents need clear metadata to understand service capabilities.

---

### 6. Agent-Readable GitHub README Section

**What:** Add a dedicated machine-readable section to the main README for agent integration.

**Why:** Agents often clone/read repos to understand integrations. A clear "For AI Agents" section with tool names, schemas, and auth instructions speeds up discovery.

**Content (sample):**

```markdown
## For AI Agents & Orchestrators

This section is optimized for AI agents (OpenAI Agents, Claude Code, Codebuff, OpenClaw, etc.) to quickly understand PlanExe's capabilities.

### Quick Integration

**Cloud (Hosted):**
```bash
curl -X POST https://home.planexe.org/api/v1/plans \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Build a REST API"}'
```

**Local Docker:**
```bash
docker run -p 3000:3000 planexeorg/planexe:latest
# No auth required. API at http://localhost:3000/api/v1
```

**MCP (OpenAI Responses API):**
```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="gpt-4o",
    tools=[{
        "type": "mcp",
        "server_label": "planexe",
        "server_url": "https://mcp.planexe.org/sse",
        "authorization": "Bearer YOUR_API_KEY",
    }],
    input="Generate a plan for deploying a microservices app"
)
print(response.output_text)
```

### Tools

| Tool | Input | Output | Use Case |
|------|-------|--------|----------|
| `plan.generate` | goal, context, constraints | planId, steps, estimate | Decompose complex tasks |
| `plan.poll` | planId | status, completedSteps, trace | Check execution progress |
| `plan.artifacts` | planId | artifacts array | Download generated outputs |

### OpenAPI & Schemas

- OpenAPI 3.1 schema: `GET /openapi.json`
- MCP manifest: `GET /.well-known/mcp.json`
- Agent discovery: `GET /llms.txt`

### Authentication

**Cloud:** Bearer token (get at https://home.planexe.org/account/api-keys)
**Local Docker:** None (trusted environment)

### Rate Limits

- 100 plans/hour (cloud)
- 1000 artifact downloads/day
- No limits on local Docker

### Pricing (Cloud)

- Plan generation: 10 credits
- Execution per minute: 5 credits
- Free tier: 100 credits/month

See https://home.planexe.org/pricing for details.
```

**Implementation:**
- Add to main README.md after "Features" section
- Include in CONTRIBUTING.md for agent/MCP developers
- Link from docs homepage

**Reference:** Orchestrator patterns gist notes that README agent sections help developers integrate without digging through docs.

---

## Implementation Priority

1. **llms.txt** (Phase 1 – Week 1)
   - Easiest to implement (static file)
   - Highest impact on agent discoverability
   - No code changes required

2. **robots.txt update** (Phase 1 – Week 1)
   - Quick addition
   - Enables AI crawler indexing

3. **OpenAPI schema** (Phase 2 – Week 2)
   - Requires API documentation review
   - High value for function-calling integration
   - Can be generated from code if using OpenAPI-native framework

4. **MCP Well-Known endpoint** (Phase 2 – Week 2)
   - Keep in sync with OpenAPI schema
   - Enables MCP orchestrators

5. **Structured data + meta tags** (Phase 3 – Week 3)
   - Low complexity
   - Improves AI-augmented search discoverability

6. **README agent section** (Phase 3 – Week 3)
   - Document existing capabilities
   - No code required

---

## How Agents Will Use This

1. **Discovery Phase:** Agent scans `llms.txt` or `/.well-known/mcp.json` → learns about PlanExe
2. **Schema Phase:** Agent fetches `/openapi.json` or MCP tool definitions → understands function signatures
3. **Integration Phase:**
   - Function calling: Agent calls `POST /api/v1/plans` with structured schema
   - MCP: Agent connects to `https://mcp.planexe.org/sse` via Responses API
   - Direct: Agent uses cURL or SDK to invoke REST endpoints
4. **Execution Phase:** Agent polls `/api/v1/plans/{planId}` for status → downloads artifacts

---

## Expected Outcomes

- **OpenAI Agents** can natively discover and call PlanExe tools via function calling
- **Claude Code** can integrate PlanExe for multi-step code generation planning
- **Codebuff** can use PlanExe for workflow decomposition
- **OpenClaw** can add PlanExe as an MCP capability
- **AI-augmented search** (Perplexity, Claude Web) can index PlanExe as a planning resource
- **Developers** can quickly integrate PlanExe without extensive documentation reading

---

## Risks & Mitigations

### Risk: Malicious agents calling expensive endpoints
**Mitigation:** Implement rate limiting per API key, credit-based billing, approval gates for MCP calls.

### Risk: Sensitive data exposure via schema
**Mitigation:** Don't expose user-specific fields in OpenAPI; only include public tool schemas.

### Risk: MCP server compromise
**Mitigation:** Require approval for MCP calls by default (OpenAI's default); document in security guide.

**Reference:** OpenAI's MCP connector docs emphasize: "By default, OpenAI will request your approval before any data is shared with a connector or remote MCP server."

---

## References

- **Orchestrator Patterns:** https://gist.github.com/championswimmer/bd0a45f0b1482cb7181d922fd94ab978
- **OpenAI New Tools for Building Agents:** https://openai.com/blog/new-tools-for-building-agents
- **OpenAI Function Calling Guide:** https://platform.openai.com/docs/guides/function-calling
- **OpenAI MCP Connectors Guide:** https://platform.openai.com/docs/guides/tools-connectors-mcp
- **OpenClaw Gateway Architecture:** https://docs.openclaw.ai/concepts/architecture
- **MCP Specification:** https://modelcontextprotocol.io/introduction
- **llms.txt Standard:** (emerging standard for agent discovery)
- **OpenAPI 3.1 Spec:** https://spec.openapis.org/oas/v3.1.0
- **schema.org SoftwareApplication:** https://schema.org/SoftwareApplication

---

## Success Metrics

- Agent discovery via web search / MCP crawler
- OpenAI Agents integration time (should be <30 min after this)
- MCP tool call volume from orchestrators
- Developer integration time reduction
