FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLANEXE_CONFIG_PATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_PREFER_BINARY=1 \
    PYTHONPATH=/app:/app/frontend_multi_user:/app/frontend_multi_user/src

RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid 1000 -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy application code and supporting files
COPY worker_plan/worker_plan_api /app/worker_plan_api
COPY database_api /app/database_api
COPY frontend_multi_user /app/frontend_multi_user
COPY llm_config /app/llm_config
COPY public/llms.txt /app/public/llms.txt

# Install dependencies from frontend_multi_user pyproject
RUN set -eux; \
    pip install --no-cache-dir "pip==24.3.1"; \
    pip install --no-cache-dir --prefer-binary /app/frontend_multi_user

# Default location for generated plans
RUN mkdir -p /app/run && chown -R appuser:appuser /app/run

# Gunicorn 25.x writes control-server state into <cwd>/.gunicorn at startup,
# resolved before --chdir is applied, so it lands in /app. Pre-create with
# correct ownership to avoid PermissionError from the master process.
RUN mkdir -p /app/.gunicorn && chown appuser:appuser /app/.gunicorn

USER appuser

WORKDIR /app/frontend_multi_user

EXPOSE 5000

ENV PLANEXE_FRONTEND_MULTIUSER_WORKERS=4

# --keep-alive 0 — workaround for sync-worker timeouts after large responses.
#
# Symptom: gunicorn master kills a worker with "WORKER TIMEOUT (pid:N)" exactly
# 120s after a successful big response (e.g. /plan/download/zip returning ~4MB,
# /viewplan returning ~600KB). Traceback always points at recv() / "no URI
# read" — misleading, that's just where SIGABRT interrupts the worker. The
# actual cause is the worker sitting idle in recv() on a kept-alive TCP
# connection that the upstream peer (Cloudflare edge in our deploy) holds open
# without sending another request. The sync worker counts that idle wait
# against --timeout, so the master eventually kills it.
#
# Worked in the past: this only became a regular issue recently. Likely cause
# is gunicorn 25.x sync-worker keep-alive handling combined with our move
# behind Cloudflare; previous gunicorn versions / direct connections did not
# trigger it.
#
# Fix: --keep-alive 0 forces gunicorn to close the connection right after each
# response. The worker returns to accept() instead of waiting in recv(), so it
# can never sit idle past --timeout. Tiny perf cost (one TCP handshake per
# request) — irrelevant for our traffic volume.
#
# Alternatives considered, not taken:
#  1. --worker-class gthread --threads N — threaded workers tolerate idle
#     connections without blocking. Bigger change; revisit if we ever want
#     real keep-alive for performance.
#  2. Pin gunicorn <25 — would also work if this is a 25.x regression, but
#     locks us out of upstream fixes and the 25.x control-server feature.
#  3. Lower --timeout — masks symptom at the cost of killing legitimately
#     slow handlers. Rejected.
#
# Revisit if we switch worker class, drop Cloudflare in front of this service,
# or upgrade gunicorn past a release that fixes sync keep-alive idle handling.
CMD gunicorn wsgi:app \
    --bind 0.0.0.0:${PLANEXE_FRONTEND_MULTIUSER_PORT:-5000} \
    --workers ${PLANEXE_FRONTEND_MULTIUSER_WORKERS} \
    --timeout 120 \
    --keep-alive 0 \
    --access-logfile - \
    --chdir /app/frontend_multi_user/src
