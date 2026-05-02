---
title: Antigravity - MCP integration
---

# Google Antigravity

[Antigravity](https://github.com/google-deepmind/antigravity) by Google.

[Antigravity MCP documentation](https://antigravity.google/docs/mcp)

## Interaction

My interaction history:

1. tell me about the planexe mcp tool
2. make 5 suggestions
3. crisis response plan for yellow stone outbreak, please refine that
4. I didn't meant outbreak, I meant vulcanic
5. your prompt is a bit shorter than the example prompts
6. go ahead create the plan
7. check status
8. status
9. status
10. status
11. download the report
12. summarize the report
13. does it correspond to your expectations?

I had to manually ask about `check status` to get details how the plan creation was going. It's not something that Antigravity can do.

The created plan is here: [Yellowstone Evacuation](https://planexe.org/20260201_yellowstone_evacuation_report.html)

## Configuring Antigravity

See [MCP client config snippets](mcp_client_config.md) for prerequisites and the cloud / local-Docker JSON blocks.

1. Open Antigravity
2. Click the "..." icon at the top of the Agent panel
3. Select "MCP Servers"
4. This opens the `mcp_config.json` file.

Paste the `planexe` entry from the snippet page inside your `mcpServers` dictionary. Save the file, then go to `Manage MCP Servers` and click the refresh icon.

If it doesn't work then ask on the [PlanExe Discord](https://planexe.org/discord) for help.

This is what it should look like:
![antigravity MCP settings](antigravity.jpg)
