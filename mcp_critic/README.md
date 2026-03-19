# mcp_critic — PlanExe Critic MCP Server

Standalone MCP server that exposes PlanExe's critic pipeline as tools:

| Tool | What it does |
|------|-------------|
| `premise_attack` | 5-lens ensemble that attacks the WHY of a plan |
| `premortem` | Failure mode analysis: what will kill this project |
| `swot` | Strengths, weaknesses, opportunities, threats |
| `critique` | Runs all three tools in one call |

## Usage

### stdio mode (Claude Desktop, Cursor, etc.)

```bash
cd /path/to/PlanExe
python -m mcp_critic.server
```

### Configure in Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "planexe-critic": {
      "command": "python",
      "args": ["-m", "mcp_critic.server"],
      "cwd": "/path/to/PlanExe",
      "env": {
        "PLANEXE_MODEL_PROFILE": "baseline"
      }
    }
  }
}
```

> **Troubleshooting — `ModuleNotFoundError: No module named 'worker_plan_internal'`:** This means the editable install's `.pth` file is being skipped. On macOS this can happen if the venv's `site-packages` directory has the hidden flag set (Python 3.13 skips hidden `.pth` files). Fix: `chflags -R nohidden /path/to/PlanExe/.venv/lib/python3.13/site-packages/` then reinstall with `pip install -e worker_plan/`.

## Configuration

| Env var | Description |
|---------|-------------|
| `LLM_MODEL` | Use a specific named model (e.g. `openrouter-paid-gemini-2.0-flash-001`) |
| `PLANEXE_MODEL_PROFILE` | Model profile: `baseline` / `premium` / `frontier` / `custom` |
| `PLANEXE_LLM_CONFIG_CUSTOM_FILENAME` | Custom llm_config JSON filename |

If neither `LLM_MODEL` nor `PLANEXE_MODEL_PROFILE` is set, the server uses
all models in priority order from the active llm_config profile.

## Parameters

All tools accept these optional parameters in addition to `prompt`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | `"json"` \| `"markdown"` | `"json"` | Response format. Use `"json"` for structured output (machine-readable), `"markdown"` for human-readable prose. |
| `model_profile` | `"baseline"` \| `"premium"` \| `"frontier"` \| `"custom"` | env default | Override the model tier for this call. `baseline` is fastest/cheapest; `frontier` uses the most capable model. Overrides `PLANEXE_MODEL_PROFILE` env var for the duration of the call. |

The `critique` tool also accepts:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tools` | `string[]` | all three | Which tools to run. Any subset of `["premise_attack", "premortem", "swot"]`. Partial results are returned if any tool fails. |

## Example calls

### premise_attack

```json
{
  "prompt": "Build a social media platform for cats that monetizes via pet food subscriptions",
  "format": "json"
}
```

### premortem

```json
{
  "prompt": "Launch a rocket startup targeting Mars cargo delivery within 5 years, $200M seed",
  "format": "markdown"
}
```

### swot

```json
{
  "prompt": "Open a dental clinic in Copenhagen targeting families. Budget 2.5M DKK.",
  "model_profile": "premium"
}
```

### critique (all three tools)

```json
{
  "prompt": "Replace all government tax collection with a blockchain-based voluntary contribution system",
  "tools": ["premise_attack", "premortem"],
  "model_profile": "baseline",
  "format": "markdown"
}
```

## Test the server starts

```bash
python -c "
import asyncio
from mcp_critic.server import handle_list_tools
tools = asyncio.run(handle_list_tools())
for t in tools:
    print(t.name, '-', t.description[:60])
"
```

## Architecture

```
External Agent / MCP Client
    │
    ▼
mcp_critic/server.py     — MCP server, tool definitions, async handlers
    │
    ▼
mcp_critic/tools.py      — sync wrappers around diagnostic classes
    │
    ├── PremiseAttack.execute()     (worker_plan_internal/diagnostics/premise_attack.py)
    ├── Premortem.execute()         (worker_plan_internal/diagnostics/premortem.py)
    └── swot_phase2_conduct_analysis()  (worker_plan_internal/swot/swot_phase2_conduct_analysis.py)

mcp_critic/config.py     — LLMExecutor construction from env vars
```

No diagnostic code is copied — all logic is imported from `worker_plan_internal`.
