---
title: Anthropic - AI provider
---

# Using PlanExe with Anthropic

[Anthropic](https://www.anthropic.com/) makes the Claude family of models. PlanExe can use Anthropic models directly via the Anthropic API.

There are two ways to authenticate:

| Method | Who it's for | Token format |
|---|---|---|
| **API key** | Anthropic API billing account | `sk-ant-api*` |
| **Claude Code OAuth token** | Claude Pro/Max subscribers | `sk-ant-oat*` |

The Claude Code OAuth path lets you use PlanExe without a separate API billing account — if you already pay for Claude Pro or Max, you can generate a token and use it directly.

## Authentication setup

### Option A — Standard API key

1. Sign up at [console.anthropic.com](https://console.anthropic.com/) and add API credits.
2. Generate an API key from the Console.
3. Add to your `.env`:
```
ANTHROPIC_API_KEY=sk-ant-api...
```

### Option B — Claude Code OAuth token (Claude Pro/Max subscribers)

If you have a Claude Pro or Max subscription, you can generate an OAuth token that works in place of an API key.

**Requirements:**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/getting-started) installed (`npm install -g @anthropic-ai/claude-code`)
- Active Claude Pro or Max subscription

**Steps:**

1. Run:
```
claude setup-token
```
This outputs a token starting with `sk-ant-oat`.

2. Add to your `.env`:
```
ANTHROPIC_API_KEY=sk-ant-oat01--...
```

PlanExe auto-detects the `sk-ant-oat` prefix and switches to the correct Bearer auth scheme automatically. No other changes needed.

> **Note:** OAuth tokens may expire. If you get 401 errors, run `claude setup-token` again to refresh.

---

## Choosing a model

PlanExe makes 60–100+ LLM calls per plan. Choose based on your priority:

| Config ID | Model | Speed | Cost (est. per plan) | Notes |
|---|---|---|---|---|
| `anthropic-claude-haiku-4-5` | Haiku 4.5 | Fastest | < $0.50 | Best default for most users |
| `anthropic-claude-sonnet-4-6` | Sonnet 4.6 | Medium | ~$2–5 | Better quality than Haiku |
| `anthropic-claude-sonnet-4-6-thinking` | Sonnet 4.6 + thinking | Slow | ~$5–15 | Extended reasoning per call |
| `anthropic-claude-opus-4-6` | Opus 4.6 | Slow | ~$15–40 | Highest quality, highest cost |
| `anthropic-claude-opus-4-6-thinking` | Opus 4.6 + thinking | Very slow | ~$30–80+ | Maximum quality, use sparingly |

For pinned versions (reproducible results), use:
- `anthropic-claude-haiku-4-5-pinned` — locked to `claude-haiku-4-5-20251001`
- `anthropic-claude-sonnet-4-5` — locked to `claude-sonnet-4-5`

---

## Quickstart (Docker)

1. Install Docker (with Docker Compose).
2. Clone the repo:
```
git clone https://github.com/PlanExeOrg/PlanExe.git
cd PlanExe
```
3. Copy `.env.docker-example` to `.env` and configure:
```
ANTHROPIC_API_KEY=sk-ant-...
DEFAULT_LLM=anthropic-claude-haiku-4-5
PLANEXE_MODEL_PROFILE=custom
PLANEXE_LLM_CONFIG_CUSTOM_FILENAME=anthropic_claude.json
```
4. Start PlanExe:
```
docker compose up worker_plan frontend_multi_user
```
5. Open http://localhost:5001 and submit a prompt.

To switch models, change `DEFAULT_LLM` in `.env` to any config ID from the table above, then restart:
```
docker compose restart worker_plan frontend_multi_user
```

---

## Extended thinking

Some entries in `anthropic_claude.json` enable [extended thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking). These use a `thinking_dict` in the config:

```json
"thinking_dict": {"type": "enabled", "budget_tokens": 10000}
```

`budget_tokens` controls how many tokens Claude can use for internal reasoning before writing its answer. Higher = slower + more expensive, but better structured output on complex tasks.

**Trade-offs for PlanExe:**
- PlanExe runs 60–100+ calls per plan — thinking multiplies both cost and latency significantly
- For most plans, Haiku or Sonnet without thinking produces good results
- Use thinking variants only when plan quality is the top priority

---

## Troubleshooting

**401 Unauthorized**
- API key: check that `ANTHROPIC_API_KEY` is set correctly in `.env`.
- OAuth token: run `claude setup-token` again — tokens expire.

**400 credit balance too low**
- API key path: add credits at [console.anthropic.com](https://console.anthropic.com/).
- OAuth token path: OAuth tokens authenticate you, but API calls still consume credits from your Anthropic account. Top up at the Console if needed.

**Check worker logs:**
```
docker compose logs -f worker_plan
```

Report issues on [Discord](https://planexe.org/discord). Include your OS, hardware, and the error from `log.txt` in the output directory.

---

## Next steps

- Learn prompt quality: [Prompt writing guide](../prompt_writing_guide.md)
- Understand output sections: [Plan output anatomy](../plan_output_anatomy.md)
