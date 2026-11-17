#!/bin/bash

# Exit on any error
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting TURBO Update (Design/Logic only, No Restart)..."
cd "$ROOT_DIR"

ENV_ARG=""
if [ -f ".env" ]; then
    ENV_ARG="--env-file .env"
fi

echo "Pulling from git..."
git pull origin "$(git rev-parse --abbrev-ref HEAD)"

git describe --tags --always > VERSION 2>/dev/null || git rev-parse --short HEAD > VERSION 2>/dev/null || true
git log -1 --format="%cs" > VERSION_DATE 2>/dev/null || true

echo "Setting permissions..."
chmod -R a+rwX .
chmod +x manage.py

echo "Collecting static files..."
docker compose $ENV_ARG exec web python3 manage.py collectstatic --noinput

echo "-----------------------------------"
echo "TURBO Update complete! Changes should be live instantly."
