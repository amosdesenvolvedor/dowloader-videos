#!/usr/bin/env bash
set -euo pipefail

URL="http://localhost:3000"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user start downloaderytube-local.service >/dev/null 2>&1 || true
fi

for _ in $(seq 1 20); do
  if curl --silent --head --fail "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

exec /usr/bin/xdg-open "$URL"
