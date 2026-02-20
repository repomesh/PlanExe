---
name: planexe-mcp
description: "OpenClaw skill for connecting to PlanExe via Model Context Protocol. Supports three deployment scenarios: cloud-hosted service, remote Docker, and local Docker."
version: "1.0.0"
author: "PlanExe Team"
---

# PlanExe MCP Skill

Access PlanExe's powerful planning capabilities directly from OpenClaw via the Model Context Protocol (MCP).

## Overview

The `planexe-mcp` skill provides a unified interface to interact with PlanExe across three deployment scenarios:

- **Cloud**: `mcp.planexe.org` (Stripe credits at home.planexe.org)
- **Remote Docker**: Container on a separate machine
- **Local Docker**: Container on the same machine as OpenClaw

## Setup by Deployment Scenario

### Scenario A: Cloud-Hosted Service

Connect to the hosted PlanExe MCP service.

**Configuration:**

Add to your OpenClaw config or environment:

```bash
PLANEXE_MCP_URL=https://mcp.planexe.org
PLANEXE_API_KEY=your_api_key_from_planexe_account
```

**How to Get Your API Key:**

1. Visit [home.planexe.org](https://home.planexe.org)
2. Purchase credits via Stripe
3. Generate an API key in your account dashboard
4. Copy the key to your OpenClaw configuration

---

### Scenario B: Remote Docker

Run PlanExe in Docker on a separate machine and connect remotely.

**On the Remote Machine:**

```bash
docker run -p 8001:8001 planexe/planexe:latest
```

**Configuration in OpenClaw:**

```bash
PLANEXE_MCP_URL=http://<remote-ip>:8001
PLANEXE_API_KEY=your_api_key
```

Replace `<remote-ip>` with your remote machine's IP address or hostname.

---

### Scenario C: Local Docker

Run PlanExe in Docker on the same machine as OpenClaw.

**Setup:**

```bash
docker run -p 8001:8001 planexe/planexe:latest
```

**Configuration in OpenClaw:**

```bash
PLANEXE_MCP_URL=http://127.0.0.1:8001
PLANEXE_API_KEY=your_api_key
```

---

## Invoking PlanExe Tools

Once configured, you can invoke PlanExe tools within your OpenClaw workflows:

### Example: Create a Plan

```openclaw
planexe.create_plan(
  title="Project Launch",
  description="Q2 product launch planning",
  deadline="2026-06-30"
)
```

### Example: Analyze an Existing Plan

```openclaw
planexe.analyze_plan(
  plan_id="plan_123abc"
)
```

### Example: Run Plan Simulation

```openclaw
planexe.simulate_plan(
  plan_id="plan_123abc",
  iterations=100
)
```

Refer to the complete [PlanExe API documentation](https://planexe.org/docs) for all available tools and parameters.

## Configuration Reference

| Variable | Example | Description |
|----------|---------|-------------|
| `PLANEXE_MCP_URL` | `https://mcp.planexe.org` | MCP endpoint URL |
| `PLANEXE_API_KEY` | `pk_live_abc123...` | API authentication key |

## Troubleshooting

**Connection Refused**
- Verify `PLANEXE_MCP_URL` is correct
- For Docker: Ensure the container is running (`docker ps`)
- Check network connectivity between OpenClaw and the service

**Authentication Failed**
- Verify `PLANEXE_API_KEY` is valid
- Check for typos or expired credentials
- For cloud: Log in to [home.planexe.org](https://home.planexe.org) to verify account status

**Timeout Errors**
- For Docker deployments, allow time for container initialization
- Check if the service is overloaded
- Consider increasing the request timeout in your OpenClaw config

**Docker Issues (Local/Remote)**
- Verify Docker is installed: `docker --version`
- Check container logs: `docker logs <container-id>`
- Ensure port 8001 is not in use: `lsof -i :8001` (macOS/Linux)

## Support

For issues or questions:
- Check the [PlanExe documentation](https://planexe.org/docs)
- Visit the [PlanExe community forum](https://community.planexe.org)
- Open an issue on [GitHub](https://github.com/PlanExeOrg/PlanExe)

## License

This skill is part of PlanExe and is available under the same license as the PlanExe project.
