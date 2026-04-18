---
title: LM Studio - MCP integration
---

# LM Studio

[LM Studio](https://lmstudio.ai/) is available for Linux/macOS/Windows.

You need a hefty computer for running models locally.

## Interaction

My interaction with LM Studio for creating a plan is like this:

1. tell me about the planexe mcp tool
2. fetch the example prompts
3. based on the example prompts. I want you to create a plan prompt for a social media website inspired by Reddit, but instead of the target audience being humans, I want the target audience to be AI agents talking with other AI agents. And hanging out in different channels.
4. go ahead create a plan
5. check status
6. what is progress now
7. status
8. how about now
9. download the report
10. also download the zip

LM Studio cannot autonomously check status, so it's up to the user to ask for it to invoke the `plan_status` tool.

The created plan is here: [AI AgentNet](https://planexe.org/20260131_ai_agentnet_report.html)

## Configuring LM Studio

Check that LM Studio works with a model that supports tools such as [glm-4.7-flash](https://lmstudio.ai/models/zai-org/glm-4.7-flash).

See [MCP client config snippets](mcp_client_config.md) for prerequisites and the cloud / local-Docker JSON blocks.

Open LM Studio's MCP settings to edit `mcp.json` and paste the `planexe` entry from the snippet page inside your `mcpServers` dictionary.

![image](lm_studio_settings.jpg)

If it doesn't work then ask on the [PlanExe Discord](https://planexe.org/discord) for help.
