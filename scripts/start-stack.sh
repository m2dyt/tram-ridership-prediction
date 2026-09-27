#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

if ! docker info >/dev/null 2>&1; then
  printf '%s\n' "Docker Engine is unavailable. Start Docker Desktop and retry." >&2
  exit 1
fi

if [ ! -f .env ]; then
  python3 - <<'PY'
import secrets
from pathlib import Path

path = Path(".env")
values = {
    "TRAM_POSTGRES_PASSWORD": secrets.token_hex(24),
    "TRAM_POSTGRES_PORT": "15433",
    "TRAM_VIEWER_TOKEN": secrets.token_urlsafe(32),
    "TRAM_OPERATOR_TOKEN": secrets.token_urlsafe(32),
    "TRAM_CURSOR_SECRET": secrets.token_urlsafe(32),
    "TRAM_AUTH_TOKEN_SECRET": secrets.token_urlsafe(32),
}
path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
path.chmod(0o600)
print("Created .env with private local credentials.")
PY
fi

for path in \
  dataset/labels/labels_day_train.csv \
  dataset/labels/labels_day_test.csv \
  dataset/test_submission.csv
do
  if [ ! -f "$path" ]; then
    printf 'Required dataset file is missing: %s\n' "$path" >&2
    exit 1
  fi
done

docker compose config --quiet
docker compose build
docker compose up -d --wait db
docker compose run --rm migrate
docker compose run --rm bootstrap-operator
docker compose run --rm dataset-import
docker compose run --rm train-model
docker compose up -d --wait api
docker compose up -d worker

printf '\n%s\n' "Docker services:"
docker compose ps
printf '\n%s\n' "PostgreSQL row counts:"
docker compose exec -T db psql -U tram -d tram -P pager=off -c \
  "SELECT 'dataset_revisions' AS table_name, count(*) AS rows FROM dataset_revisions UNION ALL SELECT 'network_revisions', count(*) FROM network_revisions UNION ALL SELECT 'series', count(*) FROM series UNION ALL SELECT 'observations', count(*) FROM observations UNION ALL SELECT 'users', count(*) FROM users ORDER BY table_name;"
printf '\n%s\n' "Frontend and API: http://localhost:8000"
printf '%s\n' "Health endpoint: http://localhost:8000/api/v1/health"
printf '%s\n' "Shared operator login: operator; the password is in docs/DOCKER_STACK.md."
