FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client zstd && \
    rm -rf /var/lib/apt/lists/*

COPY database_worker/server.py /app/server.py

WORKDIR /app
EXPOSE 8002

CMD ["python", "server.py"]
