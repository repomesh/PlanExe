# MCP roadmap for PlanExe

## OpenClaw 

Have openclaw again invoke mcp.planexe.org, and turn it into a skill.


# Code

- plan_file_info: ability to download files as they become ready. **No per-file inspection during processing.** `plan_status` lists intermediate files with timestamps, which is useful for detecting stalls, but there's no way to read individual files while the plan is still processing. Being able to peek at early outputs could help users decide whether to let the plan continue or stop and adjust.
- plan_create/plan_retry, better error messages when the credits are low.
- Submit here
    - publish on mcp discord
    - publish on mcp subreddits
    - https://mcp.so/
    - https://github.com/punkpeye/awesome-mcp-servers
    - https://www.pulsemcp.com/servers?q=planexe   processes weekly incoming web servers, so I should wait a few days
    - https://mcpservers.org/search?query=planexe   cost $40 to have it reviewed
    - https://www.mcp-trust.com/
- plan_status, respond with the credits spent, and the credits available.
- can I automate testing of MCP? Automated testing of the mcp.planexe.org endpoint, so it runs a harness of tests: create a plan, zero credits, invalid bearer token, purchase credits.
- Set a credit limit to individual named API keys on home.planexe.org, so they don’t exceed the budget.


## Docs

- Go through MCP docs and check if screenshots reflect the current api. When I took the screenshots I used task_ prefix. Now I use plan_ prefix.
- OpenClaw integration
- Glama.ai
- Smithery 
- AgentZero integration
- n8n integration
- Video tutorial explaning how to use PlanExe via mcp.
