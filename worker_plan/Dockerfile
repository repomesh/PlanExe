FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLANEXE_CONFIG_PATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_PREFER_BINARY=1

RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid 1000 -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy application code and supporting files
COPY worker_plan /app/worker_plan
COPY llm_config /app/llm_config

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefer-binary /app/worker_plan

# Default location for generated plans
RUN mkdir -p /app/run && chown -R appuser:appuser /app/run

USER appuser

EXPOSE 8000

CMD ["uvicorn", "worker_plan.app:app", "--host", "0.0.0.0", "--port", "8000"]
