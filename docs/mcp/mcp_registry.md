---
title: Publish to MCP Registry
---

# Publish PlanExe to MCP Registry

## Official MCP Registry

https://registry.modelcontextprotocol.io/?q=planexe

Updating this registry is by using CLI tools.

Steps to publish the hosted PlanExe MCP server ([https://mcp.planexe.org/mcp](https://mcp.planexe.org/mcp)) to the official MCP Registry so it appears in the GitHub MCP registry UI.

### Metadata file

PlanExe uses the committed registry metadata file in the MCP cloud component:

- `mcp_cloud/server.json`

The current registry name is:

- `io.github.PlanExeOrg/planexe`

This uses GitHub namespace ownership verification (`io.github.<org>/<server>`).

### Install `mcp-publisher`

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

### Authenticate and publish

From the `mcp_cloud` directory, run:

```bash
cd mcp_cloud
mcp-publisher login github
mcp-publisher publish
```

Notes:

- Publish from the directory containing `server.json` (`mcp_cloud/`).
- Bump `version` in `mcp_cloud/server.json` for each new release before publishing.

### Verify registry entry

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.PlanExeOrg/planexe"
```

If found in registry search, it should become discoverable in the GitHub MCP Registry UI at [https://github.com/mcp](https://github.com/mcp).


## Other MCP registries

### Glama

https://glama.ai/mcp/connectors/io.github.PlanExeOrg/planexe

Updating this is by updating these files:
https://planexe.org/.well-known/glama.json
https://mcp.planexe.org/.well-known/glama.json


### MCP.so

https://mcp.so/server/planexe/PlanExeOrg

The way to edit it, has to be through [mcp.so/my-servers](https://mcp.so/my-servers).


