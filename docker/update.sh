#!/bin/bash

# Exit on any error
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting Update Process..."
cd "$ROOT_DIR"

ENV_ARG=""
if [ -f ".env" ]; then
    ENV_ARG="--env-file .env"
fi

echo "Pulling from git repository..."
git pull origin "$(git rev-parse --abbrev-ref HEAD)"

git describe --tags --always > VERSION 2>/dev/null || git rev-parse --short HEAD > VERSION 2>/dev/null || true
git log -1 --format="%cs" > VERSION_DATE 2>/dev/null || true

echo "Ensuring project-wide permissions..."
chmod -R a+rwX .
chmod +x manage.py

echo "Preparing data directories..."
mkdir -p "$ROOT_DIR/data/backups"
chmod -R 777 "$ROOT_DIR/data"

echo "Building the docker image..."
docker compose $ENV_ARG build

echo "Starting the container..."
docker compose $ENV_ARG up -d

echo "Syncing requirements..."
docker compose $ENV_ARG exec -u root web pip install -q --no-cache-dir --root-user-action=ignore -r requirements.txt

echo "Database migrations..."
docker compose $ENV_ARG exec web python3 manage.py migrate --noinput

echo "Processing assets..."
docker compose $ENV_ARG exec web python3 manage.py collectstatic --noinput

echo "-----------------------------------"
echo "Update complete! Application is running."
