#!/usr/bin/env bash
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
for f in .api.pid .mcp.pid .web.pid; do
  if [ -f "$ROOT/$f" ]; then kill "$(cat "$ROOT/$f")" 2>/dev/null || true; rm -f "$ROOT/$f"; fi
done
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "app.mcp_server" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true
echo stopped
