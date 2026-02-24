---
title: Publish to MCP Registry
---

# Publish PlanExe to MCP Registry

This page documents how to publish the hosted PlanExe MCP server ([https://mcp.planexe.org/mcp](https://mcp.planexe.org/mcp)) to the official MCP Registry so it appears in the GitHub MCP registry UI.

## 1) Metadata file

PlanExe uses the committed registry metadata file in the MCP cloud component:

- `mcp_cloud/server.json`

The current registry name is:

- `io.github.PlanExeOrg/planexe`

This uses GitHub namespace ownership verification (`io.github.<org>/<server>`).

## 2) Install `mcp-publisher`

On macOS, prefer Homebrew:

```bash
brew update
brew install mcp-publisher
mcp-publisher --help
```

Fallback (direct binary download):

```bash
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" \
| tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/
```

## 3) Authenticate and publish

From the `mcp_cloud` directory, run:

```bash
cd mcp_cloud
mcp-publisher login github
mcp-publisher publish
```

Notes:

- Publish from the directory containing `server.json` (`mcp_cloud/`).
- Bump `version` in `mcp_cloud/server.json` for each new release before publishing.

## 4) Verify registry entry

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.PlanExeOrg/planexe"
```

If found in registry search, it should become discoverable in the GitHub MCP Registry UI at [https://github.com/mcp](https://github.com/mcp).

## 5) Claim on Glama

Glama connector claim verification expects a public well-known file:

- `https://mcp.planexe.org/.well-known/glama.json`

PlanExe serves this from `mcp_cloud/http_server.py` with the schema:

```json
{
  "$schema": "https://glama.ai/mcp/schemas/connector.json",
  "maintainers": [
    {
      "email": "neoneye@gmail.com"
    }
  ]
}
```

If needed, override the email via environment variable:

```bash
PLANEXE_MCP_GLAMA_MAINTAINER_EMAIL=neoneye@gmail.com
```
