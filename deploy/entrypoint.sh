#!/bin/sh
set -e

# Apply DB migrations before starting (no-op if already at head).
echo "running alembic migrations..."
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
