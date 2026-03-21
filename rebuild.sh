#!/usr/bin/env bash
set -e
docker compose down --remove-orphans
docker compose build --no-cache
docker compose up
