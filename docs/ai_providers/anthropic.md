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

## Option A — Standard API key

1. Sign up at [console.anthropic.com](https://console.anthropic.com/) and add API credits.
2. Generate an API key from the Console.
3. Copy `.env.docker-example` to `.env` and add:
```
ANTHROPIC_API_KEY=sk-ant-api...
```

## Option B — Claude Code OAuth token (Claude Pro/Max subscribers)

If you have a Claude Pro or Max subscription, you can use `claude setup-token` to generate an OAuth token that works in place of an API key.

**Requirements:**
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/getting-started) installed (`npm install -g @anthropic-ai/claude-code`)
- Active Claude Pro or Max subscription

**Steps:**

1. Run:
```
claude setup-token
```
This outputs a token starting with `sk-ant-oat`.

2. Copy `.env.docker-example` to `.env` and add:
```
ANTHROPIC_API_KEY=sk-ant-oat01--...
```

PlanExe auto-detects the `sk-ant-oat` prefix and switches to the correct `Authorization: Bearer` auth scheme with the required `anthropic-beta: oauth-2025-04-20` header. No other changes needed.

> **Note:** OAuth tokens may expire. If you get 401 errors, run `claude setup-token` again to refresh.

## Quickstart (Docker)

1. Install Docker (with Docker Compose).
2. Clone the repo:
```
git clone https://github.com/PlanExeOrg/PlanExe.git
cd PlanExe
```
3. Copy `.env.docker-example` to `.env` and set your key (API key or OAuth token — either format works):
```
ANTHROPIC_API_KEY=sk-ant-...
DEFAULT_LLM=anthropic-claude-haiku-4-5
PLANEXE_MODEL_PROFILE=custom
PLANEXE_LLM_CONFIG_CUSTOM_FILENAME=anthropic_claude.json
```
4. Start PlanExe:
```
docker compose up worker_plan frontend_single_user
```
5. Open http://localhost:7860 and submit a prompt.

## Configuration

PlanExe includes `llm_config/anthropic_claude.json` with two ready-to-use entries:

| Config ID | Model | Speed | Cost |
|---|---|---|---|
| `anthropic-claude-sonnet-4-5` | claude-sonnet-4-5 | Medium | ~$3/$15 per M tokens |
| `anthropic-claude-haiku-4-5` | claude-haiku-4-5 | Fast | ~$0.25/$1.25 per M tokens |

For most PlanExe runs, **haiku** is the right choice — it's fast, cheap, and handles PlanExe's structured output requirements well.

To use this config:
```
PLANEXE_MODEL_PROFILE=custom
PLANEXE_LLM_CONFIG_CUSTOM_FILENAME=anthropic_claude.json
DEFAULT_LLM=anthropic-claude-haiku-4-5
```

## Choosing a model

PlanExe makes 60–100+ LLM calls per plan. Claude Haiku is recommended for cost-effective runs. Claude Sonnet produces higher-quality output but costs roughly 10× more per run.

## Troubleshooting

**401 Unauthorized**
- API key: check that `ANTHROPIC_API_KEY` is set correctly in `.env`.
- OAuth token: run `claude setup-token` again — tokens expire.

**400 credit balance too low**
- API key path: add credits at [console.anthropic.com](https://console.anthropic.com/).
- OAuth token path: OAuth tokens authenticate you but API calls still consume credits from your Anthropic account. If your account has no credits, top up at the Console.

**Check worker logs:**
```
docker compose logs -f worker_plan
```

Report issues on [Discord](https://planexe.org/discord). Include your OS, hardware, and the error from `log.txt` in the output directory.

---

## Next steps

- Learn prompt quality: [Prompt writing guide](../prompt_writing_guide.md)
- Understand output sections: [Plan output anatomy](../plan_output_anatomy.md)
