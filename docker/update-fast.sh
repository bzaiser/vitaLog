#!/bin/bash

# Exit on any error
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting FAST Update Process (No Rebuild)..."
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

echo "Syncing requirements..."
docker compose $ENV_ARG exec -u root web pip install -q --no-cache-dir --root-user-action=ignore -r requirements.txt

DS_REPO="https://github.com/bzaiser/django-design-studio.git"
DS_COMMIT_FILE="$ROOT_DIR/data/.ds_commit"
DS_REMOTE=$(git ls-remote "$DS_REPO" refs/heads/main 2>/dev/null | awk '{print $1}')
DS_LOCAL=$(cat "$DS_COMMIT_FILE" 2>/dev/null || true)
if [ -n "$DS_REMOTE" ] && [ "$DS_REMOTE" != "$DS_LOCAL" ]; then
    echo "Updating django-design-studio ($DS_REMOTE)..."
    docker compose $ENV_ARG exec -u root web pip install -q --no-cache-dir --force-reinstall --no-deps --root-user-action=ignore "git+${DS_REPO}@${DS_REMOTE}"
    echo "$DS_REMOTE" > "$DS_COMMIT_FILE"
fi

echo "Running database migrations..."
docker compose $ENV_ARG exec web python3 manage.py migrate --noinput

echo "Collecting static files..."
docker compose $ENV_ARG exec web python3 manage.py collectstatic --noinput

echo "Updating containers..."
docker compose $ENV_ARG up -d
docker compose $ENV_ARG restart web

echo "-----------------------------------"
echo "FAST Update complete! The UI/Code is now live."
