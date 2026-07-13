#!/usr/bin/env bash
set -euo pipefail

host="${1:-localhost}"
port="${2:-8000}"
timeout="${3:-60}"

url="http://${host}:${port}/health"

# /health returns HTTP 200 even when a dependency is still booting (it reports
# {"status":"degraded"}), so a bare curl -sf would pass before Neo4j/Qdrant are
# ready and let `make seed` race ahead. Wait until every dependency is up, i.e.
# the body reports "status":"ok".
echo "Waiting for all dependencies to be healthy at ${url} ..."
elapsed=0
until body="$(curl -sf "$url" 2>/dev/null)" \
    && printf '%s' "$body" | grep -qE '"status"[[:space:]]*:[[:space:]]*"ok"'; do
  if [ "$elapsed" -ge "$timeout" ]; then
    echo "Timed out after ${timeout}s. Last /health response:" >&2
    curl -s "$url" >&2 || true
    echo >&2
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
echo "All dependencies healthy."
