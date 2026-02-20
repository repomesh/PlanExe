# OpenClaw MCP Integration

## Overview

PlanExe exposes a Model Context Protocol (MCP) interface that allows OpenClaw to connect and access PlanExe's powerful planning capabilities. OpenClaw users can interact with PlanExe tools through the dedicated `planexe-mcp` skill, which is available on ClawHub.

The integration supports three deployment scenarios:

1. **Cloud**: Connect to the hosted `mcp.planexe.org` service
2. **Remote Docker**: Connect to a Docker container running on a separate machine
3. **Local Docker**: Connect to a Docker container on the same machine as OpenClaw

## Setup Scenarios

### Scenario A: Cloud-Hosted MCP Service

Connect directly to the hosted PlanExe MCP service at `mcp.planexe.org`.

#### Prerequisites

- An active PlanExe account
- Credits purchased via Stripe at [home.planexe.org](https://home.planexe.org)

#### Configuration

Set the following environment variables in your OpenClaw configuration:

```bash
PLANEXE_MCP_URL=https://mcp.planexe.org
PLANEXE_API_KEY=your_api_key_here
```

The `PLANEXE_API_KEY` is available in your PlanExe account dashboard after purchasing credits.

#### Usage

Once configured, the `planexe-mcp` skill will automatically route all PlanExe tool calls to the cloud service. No additional setup is required.

---

### Scenario B: Remote Docker Deployment

Run PlanExe as a Docker container on a separate machine and connect OpenClaw remotely.

#### Prerequisites

- Docker installed on the remote machine
- Network connectivity between OpenClaw and the remote machine
- The remote machine's IP address or hostname

#### Setup on Remote Machine

Run the PlanExe Docker container with port 8001 exposed:

```bash
docker run -p 8001:8001 planexe/planexe:latest
```

The MCP interface will be available at `http://<remote-ip>:8001`.

#### Configuration in OpenClaw

Set the following environment variables in your OpenClaw configuration:

```bash
PLANEXE_MCP_URL=http://<remote-ip>:8001
PLANEXE_API_KEY=your_api_key_here
```

Replace `<remote-ip>` with the IP address or hostname of the remote machine running Docker.

#### Usage

The `planexe-mcp` skill will automatically route all PlanExe tool calls to the remote Docker instance.

---

### Scenario C: Local Docker Deployment

Run PlanExe as a Docker container on the same machine as OpenClaw.

#### Prerequisites

- Docker installed locally
- OpenClaw running on the same machine

#### Setup

Run the PlanExe Docker container locally:

```bash
docker run -p 8001:8001 planexe/planexe:latest
```

The MCP interface will be available at `http://127.0.0.1:8001`.

#### Configuration in OpenClaw

Set the following environment variables in your OpenClaw configuration:

```bash
PLANEXE_MCP_URL=http://127.0.0.1:8001
PLANEXE_API_KEY=your_api_key_here
```

#### Usage

The `planexe-mcp` skill will automatically route all PlanExe tool calls to the local Docker container.

---

## Key Notes

- **Single Skill**: The `planexe-mcp` skill handles all three scenarios seamlessly. Choose your deployment approach, set the appropriate environment variables, and the skill automatically routes requests correctly.

- **ClawHub**: The `planexe-mcp` skill is available on [ClawHub](https://clawhub.ai), OpenClaw's skill marketplace. Install it like any other OpenClaw skill.

- **API Key Management**: Regardless of deployment scenario, you'll need a valid `PLANEXE_API_KEY`. For cloud deployments, this is purchased via Stripe. For Docker deployments, consult the PlanExe documentation for local authentication setup.

## Invoking PlanExe Tools

Once the `planexe-mcp` skill is installed and configured:

1. Reference PlanExe tools in your OpenClaw workflows
2. The skill automatically connects to your configured MCP endpoint
3. Tool results are returned directly to your OpenClaw context

For specific tool documentation, refer to the [PlanExe documentation](https://planexe.org/docs).

## Troubleshooting

- **Connection Refused**: Verify that `PLANEXE_MCP_URL` is correct and the service is running
- **Authentication Failed**: Check that `PLANEXE_API_KEY` is valid
- **Timeout**: For Docker deployments, ensure the container is fully initialized before making requests
