---
title: Deploy PlanExe on Railway
---

# PlanExe on Railway

This is what PlanExe looks like when it's deployed on Railway:
- Website: [home.planexe.org](https://home.planexe.org/)
- MCP interface: [mcp.planexe.org](https://mcp.planexe.org/)

You can deploy PlanExe yourself on Railway. It's not straightforward to get working. I recommend first getting docker working on localhost, when that works, then move on to Railway. There are many files related to railway, these are named `railway.md` or `railway.toml`, and describes how things are configured in my Railway setup.

## Project Settings

### Environments

Create these environments:
- `production`
- `staging`

### Shared variables - production

```
OPENROUTER_API_KEY="secret"
PLANEXE_API_KEY_SECRET="secret"
PLANEXE_DATABASE_WORKER_API_KEY="secret"
PLANEXE_DATABASE_WORKER_URL="http://databaseworker.railway.internal:8080"
PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD="secret"
PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME="secret"
PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY="secret"
PLANEXE_GOOGLE_ANALYTICS="secret"
PLANEXE_IFRAME_GENERATOR_CONFIRMATION_DEVELOPMENT_URL="https://example.com/iframe_confirm_development"
PLANEXE_IFRAME_GENERATOR_CONFIRMATION_PRODUCTION_URL="https://example.com/iframe_confirm_production"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES="OpenRouter"
PLANEXE_OAUTH_DISCORD_CLIENT_ID="secret"
PLANEXE_OAUTH_DISCORD_CLIENT_SECRET="secret"
PLANEXE_OAUTH_GITHUB_CLIENT_ID="secret"
PLANEXE_OAUTH_GITHUB_CLIENT_SECRET="secret"
PLANEXE_OAUTH_GOOGLE_CLIENT_ID="secret"
PLANEXE_OAUTH_GOOGLE_CLIENT_SECRET="secret"
PLANEXE_POSTGRES_HOST="databasepostgres.railway.internal"
PLANEXE_POSTGRES_PASSWORD="secret"
PLANEXE_STRIPE_SECRET_KEY="secret"
POSTGRES_DATABASE_HOST="secret"
POSTGRES_DATABASE_PUBLIC_PORT="secret"
```

Generate `<a-strong-random-string>` with `openssl rand -hex 32`.


### Shared variables - staging

```
PLANEXE_POSTGRES_PASSWORD=unique random text, different than production
OPENROUTER_API_KEY="SECRET-KEY-HERE"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES=OpenRouter
```

## Using Shared Variables in Services

Each service that connects to the database must reference the shared password variable in its own environment variables.

In Railway, go to each service → **Variables** and add:

```
PLANEXE_POSTGRES_PASSWORD="${{shared.PLANEXE_POSTGRES_PASSWORD}}"
OPENROUTER_API_KEY="${{shared.OPENROUTER_API_KEY}}"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES="${{shared.PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES}}"
```

Services that need this variable:
- `database_postgres`
- `frontend_multi_user`
- `worker_plan_database`

This ensures all services use the same password, and you only need to update it in one place (the shared variables) when rotating credentials.
