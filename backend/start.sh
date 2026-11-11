#!/usr/bin/env bash
# Local / non-Fly start script. On Fly, fly.toml's release_command runs the
# migrations and the Docker CMD starts uvicorn, so this file is not used there.
#
# Any failure stops the script: the server never starts on a schema that did
# not migrate.
set -euo pipefail
cd "$(dirname "$0")"

echo "Running database migrations..."
alembic upgrade head

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
