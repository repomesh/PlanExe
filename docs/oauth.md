---
title: OAuth setup
---

# OAuth setup for frontend_multi_user

This guide covers OAuth login for `frontend_multi_user` with:

- Google
- GitHub
- Discord

It includes both production and localhost setups.

## How PlanExe builds callback URLs

PlanExe uses this pattern for all providers:

`{PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL}/auth/{provider}/callback`

Examples:

- `https://home.planexe.org/auth/google/callback`
- `https://home.planexe.org/auth/github/callback`
- `https://home.planexe.org/auth/discord/callback`
- `http://localhost:5001/auth/google/callback`
- `http://localhost:5001/auth/github/callback`
- `http://localhost:5001/auth/discord/callback`

Important:

- `PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL` must have no trailing slash.
- If this env var is missing, PlanExe defaults to `http://localhost:5001`.

## Required environment variables

Set these on `frontend_multi_user`:

```bash
PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL="https://home.planexe.org"
PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY="insert-a-long-random-secret-for-sessions"
PLANEXE_AUTH_REQUIRED="true"

PLANEXE_OAUTH_GOOGLE_CLIENT_ID="insert-your-clientid"
PLANEXE_OAUTH_GOOGLE_CLIENT_SECRET="insert-your-secret"

PLANEXE_OAUTH_GITHUB_CLIENT_ID="insert-your-clientid"
PLANEXE_OAUTH_GITHUB_CLIENT_SECRET="insert-your-secret"

PLANEXE_OAUTH_DISCORD_CLIENT_ID="insert-your-clientid"
PLANEXE_OAUTH_DISCORD_CLIENT_SECRET="insert-your-secret"
```

Notes:

- Keep `PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY` stable across deploys, otherwise login sessions break.
- If `PLANEXE_AUTH_REQUIRED=true` and no OAuth provider is configured, startup fails by design.

## Production setup

Use your real public domain, for example `https://home.planexe.org`.

### Google (production)

1. In Google Cloud Console, create OAuth client type `Web application`.
2. Add authorized redirect URI:
   `https://home.planexe.org/auth/google/callback`
3. Set client ID/secret in:
   `PLANEXE_OAUTH_GOOGLE_CLIENT_ID` and `PLANEXE_OAUTH_GOOGLE_CLIENT_SECRET`.

Verify what the app is using:

- Open `https://home.planexe.org/api/oauth-redirect-uri`
- Confirm `redirect_uri=` matches the URI in Google exactly.

### GitHub (production)

Create OAuth App at [github.com/settings/developers](https://github.com/settings/developers):

- Application name: `PlanExe`
- Homepage URL: `https://planexe.org/`
- Authorization callback URL: `https://home.planexe.org/auth/github/callback`
- Device Flow: off

Set credentials in:

- `PLANEXE_OAUTH_GITHUB_CLIENT_ID`
- `PLANEXE_OAUTH_GITHUB_CLIENT_SECRET`

### Discord (production)

Create an application in the Discord developer portal:
[discord.com/developers/applications](https://discord.com/developers/applications)

Under OAuth2 settings, add redirect URI:

- `https://home.planexe.org/auth/discord/callback`

Set credentials in:

- `PLANEXE_OAUTH_DISCORD_CLIENT_ID`
- `PLANEXE_OAUTH_DISCORD_CLIENT_SECRET`

## Localhost setup (development)

Use `http://localhost:5001` as public URL.

### Google (localhost)

In Google OAuth client (`Web application`), add:

- `http://localhost:5001/auth/google/callback`

Set:

- `PLANEXE_FRONTEND_MULTIUSER_PUBLIC_URL=http://localhost:5001`
- Google client ID/secret env vars.

### GitHub (localhost)

In [github.com/settings/developers](https://github.com/settings/developers), create a local OAuth app:

- Application name: `PlanExe Localhost`
- Homepage URL: `http://localhost:5001/`
- Authorization callback URL: `http://localhost:5001/auth/github/callback`
- Device Flow: off

Set GitHub client ID/secret env vars.

### Discord (localhost)

In Discord application OAuth2 settings, add:

- `http://localhost:5001/auth/discord/callback`

Set Discord client ID/secret env vars.

## Troubleshooting

- `404` on `/login/<provider>`: provider env vars are missing (client ID/secret).
- Redirect mismatch errors: callback URI in provider console does not exactly match PlanExe callback.
- Login does not persist after redirect: `PLANEXE_FRONTEND_MULTIUSER_SECRET_KEY` is missing or changed.
- Browser says insecure cookie on localhost over HTTP: expected in local dev; production should use HTTPS.
