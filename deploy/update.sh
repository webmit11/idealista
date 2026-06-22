#!/bin/sh
# Update the production deployment from git and rebuild the stack.
# Run on the server:  sh /opt/idealista/deploy/update.sh
# Pulls latest code, rebuilds images, restarts. Keeps .env and the DB volume.
set -e
cd "$(dirname "$0")/.."
echo "· git pull…"
git pull --ff-only
echo "· rebuild + restart…"
docker compose -f docker-compose.prod.yml up -d --build
echo "· status:"
docker compose -f docker-compose.prod.yml ps --format 'table {{.Service}}\t{{.Status}}'
