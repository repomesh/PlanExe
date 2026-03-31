#!/usr/bin/env bash
#
# Rebuild and restart all Docker services from scratch.
#
# What it does:
#   1. Stops all running containers for this project
#   2. Removes stale containers that may conflict (from other PlanExe repos)
#   3. Rebuilds all images without cache (picks up code changes)
#   4. Cleans up old images and build cache to prevent disk bloat
#   5. Starts everything back up
#
# Your database is safe — data lives in the Docker volume
# "planexe_database_postgres_data", which is never removed by this script.
#
# Usage:
#   ./rebuild.sh
#
set -e
docker compose down --remove-orphans
# Remove stopped containers whose names conflict with this project.
# Data is safe — it lives in Docker volumes, not containers.
docker rm \
    database_postgres \
    database_worker \
    worker_plan \
    worker_plan_database \
    worker_plan_database_1 \
    worker_plan_database_2 \
    worker_plan_database_3 \
    frontend_single_user \
    frontend_multi_user \
    mcp_cloud \
    2>&1 | grep -v "No such container" || true
docker compose build --no-cache
# Clean up dangling images and build cache left by --no-cache rebuilds.
# This prevents disk usage from growing with every rebuild.
# Volumes are NOT touched — data is safe.
docker image prune -f
docker builder prune -f
docker compose up
