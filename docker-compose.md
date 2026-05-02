Docker Compose for PlanExe
==========================

TL;DR
-----
- Services: `database_postgres` (internal DB), `worker_plan` (internal pipeline API), `frontend_multi_user` (UI on `${PLANEXE_FRONTEND_MULTIUSER_PORT:-5001}`), plus DB workers (`worker_plan_database_1/2/3` by default; `worker_plan_database` in `manual` profile), and `mcp_cloud` (MCP interface on `${PLANEXE_MCP_HTTP_PORT:-8001}`); `frontend_multi_user` waits for Postgres and worker health.
- Shared host files: `.env` and `./llm_config/` mounted read-only; `.env` is also loaded via `env_file`.
- Postgres defaults to user/db/password `planexe`; override via env or `.env`; data lives in the `database_postgres_data` volume.
- Env defaults live in `docker-compose.yml` but can be overridden in `.env` or your shell (URLs, timeouts, run dirs, optional auth).
- Only `frontend_multi_user` and `mcp_cloud` publish ports to the host (bound to `127.0.0.1` by default, override via `PLANEXE_BIND_HOST`). `database_postgres` and `worker_plan` are docker-network-only — see [Published ports / bind host](#published-ports--bind-host).
- `develop.watch` syncs code/config for `worker_plan`; rebuild with `--no-cache` after big moves or dependency changes; restart policy is `unless-stopped`.

Quickstart (run from repo root)
-------------------------------
- Up (everything): `docker compose up frontend_multi_user database_postgres worker_plan worker_plan_database_1 worker_plan_database_2 worker_plan_database_3`.
- Up (MCP server): `docker compose up mcp_cloud` (requires `database_postgres` to be running).
- Down: `docker compose down` (add `--remove-orphans` if stray containers linger).
- Rebuild clean: `docker compose build --no-cache database_postgres worker_plan frontend_multi_user worker_plan_database worker_plan_database_1 worker_plan_database_2 worker_plan_database_3 mcp_cloud`.
- UI: http://localhost:5001 after the stack is up.
- MCP: configure your MCP client to connect to the `mcp_cloud` container via stdio.
- Logs: `docker compose logs -f worker_plan` or `... frontend_multi_user` or `... mcp_cloud`.
- One-off inside a container: `docker compose run --rm worker_plan python -m worker_plan_internal.fiction.fiction_writer` (use `exec` if already running).
- Ensure `.env` and `llm_config/` exist; copy `.env.docker-example` to `.env` if you need a starter.

Why compose (escaping dependency hell)
--------------------------------------
- Dependency hell: when one Python package requires version A of a dependency while another requires version B (or a different Python), so `pip` cannot satisfy everything in one environment; the resolver loops, pins conflict, or installs a set that breaks another part of the app. System-level deps (libssl) can also clash, and "fixes" often mean uninstalling or downgrading unrelated packages.
- I want to experiment with the `uv` package manager; to try it, install `uv` during the image build and replace the `pip install ...` lines with `uv pip install ...`. Compose keeps that change isolated per service so it doesn’t spill onto the other containers or host Python.
- Compose solves this by isolating environments per service: each image pins its own base Python, OS libs, and `requirements.txt`, so the frontend and worker no longer fight over versions.
- Builds are reproducible: the `Dockerfile` installs a clean env from scratch, so you avoid ghosts from previous virtualenvs or globally-installed wheels.
- If a dependency change fails, you can rebuild from zero or switch base images without nuking your host Python setup.

What compose sets up
--------------------
- Reusable local stack with consistent env/paths under `/app` in each container.
- Postgres data volume: `database_postgres_data` keeps the database files outside the repo tree.

Service: `database_postgres` (Postgres DB)
------------------------------------------
- Purpose: Storage in a Postgres database for future queue + event logging work. **Not published to the host.** Other containers reach it via the docker network at `database_postgres:5432`. To poke at it from your machine use `docker compose exec database_postgres psql -U planexe` or a one-off override (see [Published ports / bind host](#published-ports--bind-host)).
- Build: `database_postgres/Dockerfile` (uses the official Postgres image).
- Env defaults: `PLANEXE_POSTGRES_USER=planexe`, `PLANEXE_POSTGRES_PASSWORD=planexe`, `PLANEXE_POSTGRES_DB=planexe`, `PLANEXE_POSTGRES_PORT=5432` (override with env/.env).
- Data/health: data in the named volume `database_postgres_data`; healthcheck uses `pg_isready`.

Published ports / bind host
---------------------------

Several services have permissive defaults that are fine for localhost-only development but would be a foot-gun on a shared network:

- `frontend_multi_user` defaults to `admin` / `admin`.
- `mcp_cloud` defaults to `PLANEXE_MCP_REQUIRE_AUTH=false` with empty `PLANEXE_MCP_API_KEY`.
- `database_postgres` defaults to user/password `planexe` / `planexe`.
- `worker_plan` has no auth at all.

Ports policy:

- `database_postgres` and `worker_plan` are **not** published to the host. Other containers reach them via the docker network as `database_postgres:5432` and `worker_plan:8000`. This also sidesteps the common "port 5432 already in use" conflict with a local Postgres on dev machines.
- `frontend_multi_user` (5001) and `mcp_cloud` (8001) are published, bound to `PLANEXE_BIND_HOST` (default `127.0.0.1`).

To opt back into LAN access for the published services (e.g., testing from your phone, Claude Desktop on another machine):

```bash
export PLANEXE_BIND_HOST=0.0.0.0
docker compose up
```

Before doing this, set strong values for at least:

- `PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD`
- `PLANEXE_MCP_REQUIRE_AUTH=true` and `PLANEXE_MCP_API_KEY`

### Reaching the internal services from the host

When you actually want a `psql` shell or `curl` to one of the unpublished services:

```bash
# Postgres shell inside the DB container:
docker compose exec database_postgres psql -U planexe

# Hit worker_plan from inside the frontend container:
docker compose exec frontend_multi_user curl -fsS http://worker_plan:8000/healthcheck
```

Or, drop a tiny override file (gitignored) that adds host port mappings for a debugging session:

```yaml
# docker-compose.override.yml
services:
  database_postgres:
    ports:
      - "127.0.0.1:5433:5432"   # avoid colliding with a local Postgres on 5432
  worker_plan:
    ports:
      - "127.0.0.1:8000:8000"
```

`docker compose up` automatically merges `docker-compose.override.yml` if present.

Service: `frontend_multi_user` (multi user UI)
------------------------------------------
- Purpose: Multi-user Flask UI with admin views (tasks/events/nonce/workers) backed by Postgres.
- Build: `frontend_multi_user/Dockerfile`.
- Env defaults: DB host `database_postgres`, port `5432`, db/user/password `planexe` (follows `PLANEXE_POSTGRES_*`); admin credentials must be provided via `PLANEXE_FRONTEND_MULTIUSER_ADMIN_USERNAME`/`PLANEXE_FRONTEND_MULTIUSER_ADMIN_PASSWORD` (compose will fail if missing); container listens on fixed port `5000`, host maps `${PLANEXE_BIND_HOST:-127.0.0.1}:${PLANEXE_FRONTEND_MULTIUSER_PORT:-5001}`.
- Health: depends on `database_postgres` health; its own healthcheck hits `/healthcheck` on port 5000.

Service: `worker_plan` (pipeline API)
-------------------------------------
- Purpose: runs the PlanExe pipeline. Listens on port 8000 inside the container; **not published to the host** — `frontend_multi_user` reaches it via the docker network at `worker_plan:8000`. The frontend depends on its health.
- Build: `worker_plan/Dockerfile`.
- Env: `PLANEXE_CONFIG_PATH=/app`, `PLANEXE_WORKER_RELAY_PROCESS_OUTPUT=true`.
- Health: `http://localhost:8000/healthcheck` checked via the compose healthcheck.
- Volumes: `.env` (ro), `llm_config/` (ro).
- Watch: sync `worker_plan/` into `/app/worker_plan`, rebuild on `worker_plan/pyproject.toml`, restart on compose edits.

Service: `worker_plan_database` (DB-backed worker)
--------------------------------------------------
- Purpose: polls `PlanItem` rows in Postgres, marks them processing, runs the PlanExe pipeline, and writes progress/events back to the DB; no HTTP port exposed.
- Build: `worker_plan_database/Dockerfile` (ships `worker_plan` code, shared `database_api` models, and this worker subclass).
- Depends on: `database_postgres` health.
- Env defaults: derives `SQLALCHEMY_DATABASE_URI` from `PLANEXE_POSTGRES_HOST|PORT|DB|USER|PASSWORD` (fallbacks to `database_postgres` + `planexe/planexe` on 5432); `PLANEXE_CONFIG_PATH=/app`; MachAI confirmation URLs default to `https://example.com/iframe_generator_confirmation` for both `PLANEXE_IFRAME_GENERATOR_CONFIRMATION_PRODUCTION_URL` and `PLANEXE_IFRAME_GENERATOR_CONFIRMATION_DEVELOPMENT_URL` (override with real endpoints).
- Volumes: `.env` (ro), `llm_config/` (ro). Pipeline output stays inside the container; the worker persists final artifacts via the DB.
- Entrypoint: `python -m worker_plan_database.app` (runs the long-lived poller loop).
- Multiple workers: compose defines `worker_plan_database_1/2/3` with `PLANEXE_WORKER_ID` set to `1/2/3`. Start the trio with:
  - `docker compose up -d worker_plan_database_1 worker_plan_database_2 worker_plan_database_3`
  - (Use `worker_plan_database` alone only via profile: `docker compose --profile manual up worker_plan_database`.)

Service: `mcp_cloud` (MCP interface)
--------------------------------------
- Purpose: Model Context Protocol (MCP) server that provides a standardized interface for AI agents and developer tools to interact with PlanExe. Communicates with `worker_plan_database` via the shared Postgres database.
- Build: `mcp_cloud/Dockerfile` (ships shared `database_api` models and the MCP server implementation).
- Depends on: `database_postgres` and `worker_plan` health.
- Env defaults: derives `SQLALCHEMY_DATABASE_URI` from `PLANEXE_POSTGRES_HOST|PORT|DB|USER|PASSWORD` (fallbacks to `database_postgres` + `planexe/planexe` on 5432); `PLANEXE_CONFIG_PATH=/app`; `PLANEXE_MCP_HTTP_HOST=0.0.0.0`, `PLANEXE_MCP_HTTP_PORT=8001`; `PLANEXE_MCP_PUBLIC_BASE_URL=http://localhost:8001` for report download URLs; `PLANEXE_MCP_REQUIRE_AUTH=false` by default.
- Ports: host `${PLANEXE_BIND_HOST:-127.0.0.1}:${PLANEXE_MCP_HTTP_PORT:-8001}` -> container `8001`.
- Volumes: `llm_config/` (ro for provider configs).
- Health: `http://localhost:8001/healthcheck` checked via the compose healthcheck.
- Communication: Streamable HTTP (`/mcp`) plus helper endpoints (`/download/...`, `/sse/...`). Point your MCP client at `http://localhost:${PLANEXE_MCP_HTTP_PORT:-8001}/mcp`.
- MCP tools: implements the specification in `docs/mcp/planexe_mcp_interface.md` including session management, artifact operations, and event streaming.

Usage notes
-----------
- Published ports (host-reachable, both default to `127.0.0.1`): `${PLANEXE_FRONTEND_MULTIUSER_PORT:-5001}->frontend_multi_user`, `${PLANEXE_MCP_HTTP_PORT:-8001}->mcp_cloud`. Set `PLANEXE_BIND_HOST=0.0.0.0` for LAN access (read [Published ports / bind host](#published-ports--bind-host) first).
- Internal-only services (no host port): `database_postgres` (`:5432`) and `worker_plan` (`:8000`). Reach them via the docker network from another container, or use `docker compose exec` / a `docker-compose.override.yml` for ad-hoc host access.
- `.env` must exist before `docker compose up`; it is both loaded and mounted read-only. Same for `llm_config/`. If missing, start from `.env.docker-example`.
- Database: connect from inside any container as `database_postgres:5432` with `planexe/planexe` by default; data persists via the `database_postgres_data` volume. Direct host access is opt-in via override file or `docker compose exec`.

Example: running stack
----------------------

Snapshot from `docker compose ps` on a live stack with two numbered DB workers; your timestamps, ports, and container names may differ:

```
PROMPT> docker compose ps                                                 
NAME                     IMAGE                            COMMAND                  SERVICE                  CREATED          STATUS                   PORTS
database_postgres        planexe-database_postgres        "docker-entrypoint.s…"   database_postgres        8 hours ago      Up 8 hours (healthy)
frontend_multi_user      planexe-frontend_multi_user      "python /app/fronten…"   frontend_multi_user      8 hours ago      Up 2 minutes (healthy)   127.0.0.1:5001->5000/tcp
worker_plan              planexe-worker_plan              "uvicorn worker_plan…"   worker_plan              2 minutes ago    Up 2 minutes (healthy)
worker_plan_database_1   planexe-worker_plan_database_1   "python -m worker_pl…"   worker_plan_database_1   15 seconds ago   Up 13 seconds            
worker_plan_database_2   planexe-worker_plan_database_2   "python -m worker_pl…"   worker_plan_database_2   15 seconds ago   Up 13 seconds  
```
