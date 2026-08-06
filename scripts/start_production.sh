#!/usr/bin/env sh
set -eu

echo "Starting SmartReco production initialization..."

python scripts/check_config.py

if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
    echo "Applying Alembic migrations..."
    python -m alembic upgrade head
fi

if [ "${SEED_ON_START:-false}" = "true" ]; then
    echo "Running idempotent SmartReco seed..."
    python scripts/seed_data.py
fi

echo "Starting SmartReco web server..."

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
