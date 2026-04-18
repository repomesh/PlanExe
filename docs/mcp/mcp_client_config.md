---
title: MCP client config snippets
---

# MCP client config snippets

Canonical JSON snippets for MCP clients that configure servers via an `mcpServers` dictionary (Cursor, LM Studio, Windsurf, Antigravity, Claude Desktop, etc.). For clients that use a CLI instead (Claude Code, Codex), see the per-client guide.

---

## Cloud server (`mcp.planexe.org`)

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

Get your `pex_...` key at [home.planexe.org](https://home.planexe.org/).

---

## Local Docker (`http://localhost:8001/mcp`)

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

Start PlanExe first with `docker compose up` and wait for `mcp_cloud` to be healthy. Adjust the URL if PlanExe is running on another host or port.

---

## Prerequisites

A working installation of PlanExe, reachable at the URL you plan to use. Follow [Getting Started](../getting_started.md) to bring up the stack locally, then double-check that you can create a plan via the web UI before configuring the MCP client.
