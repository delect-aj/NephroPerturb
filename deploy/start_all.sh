#!/usr/bin/env bash
# Start API, MCP server and the Next.js frontend (no root required).
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
export PATH=/public/home/dongb/miniforge3/envs/nephroperturb/bin:$PATH
LOG=${LOG:-/public/home/dongb}
cd "$ROOT"
setsid nohup deploy/run_api.sh > "$LOG/api.log" 2>&1 < /dev/null &
echo $! > "$ROOT/.api.pid"
setsid nohup deploy/run_mcp.sh > "$LOG/mcp.log" 2>&1 < /dev/null &
echo $! > "$ROOT/.mcp.pid"
cd frontend
setsid nohup npm run start > "$LOG/web.log" 2>&1 < /dev/null &
echo $! > "$ROOT/.web.pid"
echo "started: api:8091 mcp:8092 web:3000"
