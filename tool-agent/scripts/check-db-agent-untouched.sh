#!/usr/bin/env sh
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [ -d "$ROOT/db-agent" ]; then
  if ! git -C "$ROOT" diff --quiet -- db-agent 2>/dev/null; then
    echo "ERROR: db-agent/ has uncommitted changes — tool-agent must not modify db-agent"
    git -C "$ROOT" diff --stat -- db-agent || true
    exit 1
  fi
fi
echo "OK: db-agent untouched"
