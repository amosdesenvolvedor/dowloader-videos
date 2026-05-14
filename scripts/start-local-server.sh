#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/linuxlite/Documents/SiteOficiais/DownloaderYTube"
VERCEL_BIN="/usr/local/bin/vercel"

cd "$PROJECT_DIR"
exec "$VERCEL_BIN" dev --local --yes --listen 127.0.0.1:3000
