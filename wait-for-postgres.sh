#!/bin/sh
set -e

if [ -z "$1" ]; then
  echo "[wait-for-postgres] ERROR: PostgreSQL host not provided"
  echo "Usage: wait-for-postgres.sh <host> -- <command>"
  exit 1
fi

HOST="$1"
shift

PORT="${PG_PORT:-5432}"
TIMEOUT="${PG_WAIT_TIMEOUT:-60}"

echo "[wait-for-postgres] Waiting for PostgreSQL at ${HOST}:${PORT} (timeout: ${TIMEOUT}s)..."

start_time=$(date +%s)

while true; do
  if pg_isready -h "$HOST" -p "$PORT" >/dev/null 2>&1; then
    echo "[wait-for-postgres] PostgreSQL is ready"
    break
  fi

  now=$(date +%s)
  elapsed=$((now - start_time))

  if [ "$elapsed" -ge "$TIMEOUT" ]; then
    echo "[wait-for-postgres] ERROR: Timeout waiting for PostgreSQL"
    exit 1
  fi

  sleep 2
done

# Optional: validate connection if credentials exist
if [ -n "$PGUSER" ] && [ -n "$PGDATABASE" ]; then
  echo "[wait-for-postgres] Verifying database access..."
  psql -h "$HOST" -p "$PORT" -U "$PGUSER" -d "$PGDATABASE" -c '\q' >/dev/null 2>&1 || {
    echo "[wait-for-postgres] ERROR: PostgreSQL reachable but authentication failed"
    exit 1
  }
fi

echo "[wait-for-postgres] Starting application: $*"
exec "$@"

