# Railway Configuration for `frontend_multi_user`

See [PlanExe on Railway](https://docs.planexe.org/railway/) documentation for more details.

## Env vars

```
PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL="https://home.planexe.org"
PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD="${{shared.PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD}}"
PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME="${{shared.PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME}}"
PLANEXE_FRONTEND_MULTIUSER_PORT="5000"
PLANEXE_FRONTEND_MULTIUSER_DB_HOST="${{shared.PLANEXE_POSTGRES_HOST}}"
PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY="${{shared.PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY}}"
PLANEXE_WORKER_PLAN_URL="http://${{worker_plan.RAILWAY_PRIVATE_DOMAIN}}:8000"
PLANEXE_AUTH_REQUIRED="true"
PLANEXE_OAUTH_GOOGLE_CLIENT_ID="${{shared.PLANEXE_OAUTH_GOOGLE_CLIENT_ID}}"
PLANEXE_OAUTH_GOOGLE_CLIENT_SECRET="${{shared.PLANEXE_OAUTH_GOOGLE_CLIENT_SECRET}}"
PLANEXE_POSTGRES_PASSWORD="${{shared.PLANEXE_POSTGRES_PASSWORD}}"
PLANEXE_STRIPE_SECRET_KEY="${{shared.PLANEXE_STRIPE_SECRET_KEY}}"
PLANEXE_GOOGLE_ANALYTICS="${{shared.PLANEXE_GOOGLE_ANALYTICS}}"
PLANEXE_OAUTH_DISCORD_CLIENT_ID="${{shared.PLANEXE_OAUTH_DISCORD_CLIENT_ID}}"
PLANEXE_OAUTH_DISCORD_CLIENT_SECRET="${{shared.PLANEXE_OAUTH_DISCORD_CLIENT_SECRET}}"
PLANEXE_OAUTH_GITHUB_CLIENT_ID="${{shared.PLANEXE_OAUTH_GITHUB_CLIENT_ID}}"
PLANEXE_OAUTH_GITHUB_CLIENT_SECRET="${{shared.PLANEXE_OAUTH_GITHUB_CLIENT_SECRET}}"
PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES="${{shared.PLANEXE_LLM_CONFIG_WHITELISTED_CLASSES}}"
PLANEXE_API_KEY_SECRET="${{shared.PLANEXE_API_KEY_SECRET}}"
```

## Session / admin login (production)

Set **PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY** to a long, random secret (e.g. `openssl rand -hex 32`). Flask uses it to sign the session cookie. If it is missing or changes between deploys, login (including admin) will not persist and you will see "Please log in to access this page" after signing in. When `PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL` is HTTPS, the app sets the session cookie as Secure and SameSite=Lax so the browser sends it on redirects.

## OAuth

OAuth provider setup details are in `/docs/oauth.md`:

- Google (production + localhost)
- GitHub (production + localhost)
- Discord (production + localhost)


## Volume - None

The `frontend_multi_user` gets initialized via env vars, and doesn't write to disk, so it needs no volume.

## Domain

Configure a `Custom Domain` named `home.planexe.org`, that points to railway.
Incoming traffic on port 80 gets redirect to target port 5000.
