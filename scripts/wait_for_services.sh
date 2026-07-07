#!/usr/bin/env bash
set -euo pipefail

host="${1:-localhost}"
port="${2:-8000}"
timeout="${3:-60}"

echo "Waiting for backend at http://${host}:${port}/health ..."
elapsed=0
until curl -sf "http://${host}:${port}/health" > /dev/null; do
  if [ "$elapsed" -ge "$timeout" ]; then
    echo "Timed out waiting for backend after ${timeout}s" >&2
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
echo "Backend is up."
