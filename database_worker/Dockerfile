FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client zstd && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid 1000 -d /app -s /sbin/nologin appuser

COPY database_worker/server.py /app/server.py

WORKDIR /app

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8002

CMD ["python", "server.py"]
