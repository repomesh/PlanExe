FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLANEXE_CONFIG_PATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_PREFER_BINARY=1 \
    PYTHONPATH=/app:/app/worker_plan_database:/app/database_api

RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid 1000 -d /app -s /sbin/nologin appuser

WORKDIR /app

# Bring in the shared worker code, DB models, and this worker implementation.
COPY worker_plan /app/worker_plan
COPY worker_plan_database /app/worker_plan_database
COPY database_api /app/database_api
COPY llm_config /app/llm_config

# Install the core planexe package plus Flask support and database drivers.
RUN set -eux; \
    pip install --no-cache-dir --upgrade pip; \
    pip install --no-cache-dir --prefer-binary /app/worker_plan; \
    pip install --no-cache-dir --prefer-binary -r /app/worker_plan_database/requirements.txt

# Ensure output directory exists (mounted in docker-compose).
RUN mkdir -p /app/run && chown -R appuser:appuser /app/run

USER appuser

CMD ["python", "-m", "worker_plan_database.app"]
