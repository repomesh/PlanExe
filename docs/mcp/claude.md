---
title: Claude - MCP integration
---

# Claude

[Claude](https://claude.ai/) is available as a desktop app and as [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's CLI tool. Both support MCP and are configured the same way.

## Prerequisites

- Claude desktop app or Claude Code installed.
- PlanExe MCP server reachable by Claude.

## Quick setup

1. Configure MCP in Claude (see options below).
2. Ask for prompt examples.
3. Create a plan and download the report.

## Sample prompt

> Get example prompts for creating a plan.

## Success criteria

- You can fetch prompt examples.
- You can create a plan.
- You can download the report.

---

## Option A: Connect to the cloud server (mcp.planexe.org)

This is the fastest way to get started. No Docker or local installation required.

### 1. Get an API key

Create an account and obtain an API key at [home.planexe.org](https://home.planexe.org/).
Your key will be prefixed with `pex_`.

### 2. Add the MCP server

Run this command in your terminal:

```bash
claude mcp add --transport http \
  planexe \
  https://mcp.planexe.org/mcp \
  --header "X-API-Key: pex_YOUR_API_KEY"
```

Replace `pex_YOUR_API_KEY` with your actual API key.

### 3. Verify

Start Claude and check that the server is connected.

In Claude Code, type `/mcp` to see the server status. In the Claude desktop app, go to Settings and check the MCP section. You should see `planexe` listed with its tools.

---

## Option B: Run Docker locally + connect directly via HTTP

This connects Claude directly to the local MCP server over HTTP. No `mcp_local` proxy needed.

### 1. Start PlanExe locally

Follow the [Getting Started](../getting_started.md) instructions to set up PlanExe, then start the services:

```bash
docker compose up
```

Wait until the `mcp_cloud` service is healthy (listening on port 8001).

### 2. Add the MCP server

```bash
claude mcp add --transport http \
  planexe \
  http://localhost:8001/mcp
```

Authentication is disabled by default for local Docker (`PLANEXE_MCP_REQUIRE_AUTH=false`), so no API key is needed.

### 3. Verify

In Claude Code, type `/mcp` to see the server status. In the Claude desktop app, check Settings > MCP.

> **Note:** With this option, `plan_file_info` returns a download URL. Claude can fetch the URL content for you, or you can open the URL in your browser.

---

## Option C: Run Docker locally + use the mcp_local proxy

The `mcp_local` proxy runs as a stdio process and forwards calls to the Docker MCP server. It adds the `plan_download` tool which saves artifacts directly to disk.

### 1. Start PlanExe locally

Follow the [Getting Started](../getting_started.md) instructions, then:

```bash
docker compose up
```

### 2. Add the MCP server

```bash
claude mcp add --transport stdio \
  --env PLANEXE_URL="http://localhost:8001/mcp" \
  --env PLANEXE_PATH="/Users/your-name/Desktop" \
  planexe \
  -- uv run --with mcp /path/to/PlanExe/mcp_local/planexe_mcp_local.py
```

Make these adjustments:

- Replace `/path/to/PlanExe` with the actual path to your PlanExe clone.
- Replace `/Users/your-name/Desktop` with the directory where downloaded plans should be saved.
- Optional: Adjust `http://localhost:8001/mcp` if PlanExe is running on a different port.

### 3. Verify

In Claude Code, type `/mcp` to see the server status. In the Claude desktop app, check Settings > MCP.

---

## Using mcp_local with the cloud server

You can also use the `mcp_local` proxy to connect to the cloud server. This gives you the `plan_download` tool while using the hosted service:

```bash
claude mcp add --transport stdio \
  --env PLANEXE_URL="https://mcp.planexe.org/mcp" \
  --env PLANEXE_MCP_API_KEY="pex_YOUR_API_KEY" \
  --env PLANEXE_PATH="/Users/your-name/Desktop" \
  planexe \
  -- uv run --with mcp /path/to/PlanExe/mcp_local/planexe_mcp_local.py
```

---

## Alternative: manual JSON configuration

Instead of using `claude mcp add`, you can create a `.mcp.json` file in your project root.

**Cloud server (HTTP):**

```json
{
  "mcpServers": {
    "planexe": {
      "type": "http",
      "url": "https://mcp.planexe.org/mcp",
      "headers": {
        "X-API-Key": "pex_YOUR_API_KEY"
      }
    }
  }
}
```

**Local Docker (HTTP):**

```json
{
  "mcpServers": {
    "planexe": {
      "type": "http",
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

**Local proxy (stdio):**

```json
{
  "mcpServers": {
    "planexe": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp",
        "/path/to/PlanExe/mcp_local/planexe_mcp_local.py"
      ],
      "env": {
        "PLANEXE_URL": "http://localhost:8001/mcp",
        "PLANEXE_PATH": "/Users/your-name/Desktop"
      }
    }
  }
}
```

---

## Managing the MCP server

```bash
# List configured servers
claude mcp list

# Get details for the planexe server
claude mcp get planexe

# Remove the server
claude mcp remove planexe
```

---

## Interaction

My interaction with Claude for creating a plan is like this:

1. tell me about the planexe mcp tool you have access to
2. get the prompt examples
3. I want a prompt about building a community solar farm in rural Denmark
4. go ahead create this plan
5. *wait for 10-20 minutes, Claude polls status automatically*
6. download the report

---

## Troubleshooting

- If `/mcp` shows the server as disconnected, check that Docker is running (`docker compose ps`) or that `mcp.planexe.org` is reachable.
- If you get authentication errors with the cloud server, verify your API key at [home.planexe.org](https://home.planexe.org/).
- For stdio transport issues, make sure `uv` is installed and on your PATH.
- For more help, see the [Troubleshooting guide](mcp_troubleshooting.md) or ask on the [PlanExe Discord](https://planexe.org/discord).
