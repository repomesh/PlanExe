---
title: MCP troubleshooting
---

# MCP troubleshooting

Common MCP integration issues and fixes.

---

## Cannot create a plan

- Ensure your prompt is detailed (typically ~300-800 words) and includes objective, scope, constraints, timeline, stakeholders, budget/resources, and success criteria.
- Some topics may be refused by the model (harmful, unethical, or dangerous requests).
- Try a smaller model or a more reliable paid model.
- Confirm the MCP server is reachable from your client.

---

## Status never changes

- Long‑running plans are normal; retry after a few minutes.
- If it stalls, create a new task and compare behavior.

---

## Download fails

- Confirm the download URL is reachable from your network.
- If you run locally, make sure any proxy or base URL is correct.
- Ensure `PLANEXE_PATH` is a valid directory and that you have write permissions.

---

## Low‑quality output

- Increase prompt detail and constraints.
- Use a stronger model.
- Avoid “vague” or conflicting requirements.

---

## Quota or billing errors

If you see errors like:

> You exceeded your current quota, please check your plan and billing details

Then:

- Verify your provider has active billing.
- Check usage limits or rate limits.
- Try a different model or provider.

---

## `Invalid API key` (403)

If your MCP client can reach `https://mcp.planexe.org/mcp` but receives `{"detail":"Invalid API key"}`:

- Send **only the raw key value** (e.g. `pex_…`), not `X-API-Key: pex_…`.
- The header should be `X-API-Key: <key>` or `Authorization: Bearer <key>`.
- Verify with curl:

```bash
curl -i -H "X-API-Key: pex_your_key_here" https://mcp.planexe.org/mcp/tools
```

- For self-hosted deployments: ensure `PLANEXE_API_KEY_SECRET` matches in both `frontend_multi_user` (key issuer) and `mcp_cloud` (key validator). A mismatch causes all `pex_…` keys to be rejected.
