---
title: Cursor - MCP integration
---

# Cursor

According to [Cursor's wikipedia page](https://en.wikipedia.org/wiki/Cursor_(code_editor)):

> Several media outlets have described Cursor as a vibe coding app.

And

> Cursor allows developers produce code from natural language instructions.

## Video

**Video (1m29s)** - PlanExe inside Cursor

Here I'm chatting with Cursor. Behind the scenes Cursor talks with PlanExe via MCP.

In total it takes 18 minutes to create the plan. The boring parts have been cropped out.

<iframe width="560" height="315" src="https://www.youtube.com/embed/rVsH_iUZayA?si=VJz4uYnxyob4zYp_" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

## Interaction

My interaction with Cursor for creating a plan is like this:

1. tell me about the planexe mcp tool you have access to
2. I want you to come up with a good prompt
3. I want something ala winter olympics in Italy 2026
4. Slightly different idea. I want Denmark to switch from DKK to EUR. Use the persona of a person representing Denmark's ministers.
5. go ahead create the plan
6. *wait for 18 minutes until the plan has been created*
7. download the plan

Here is the created plan: [DKK to EUR](https://planexe.org/20260129_euro_adoption_report.html)

## Configuring Cursor

See [MCP client config snippets](mcp_client_config.md) for prerequisites and the cloud / local-Docker JSON blocks.

Go to `Cursor Settings` → `Tools & MCP`, click `New MCP Server` to open `.cursor/mcp.json`, and paste the `planexe` entry from the snippet page inside your `mcpServers` dictionary.

Now Cursor is connected with PlanExe, and it looks like this.
If it doesn't then ask on the [PlanExe Discord](https://planexe.org/discord) for help.

![image](cursor_settings.jpg)
