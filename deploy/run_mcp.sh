#!/usr/bin/env bash
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
PY=${PY:-/public/home/dongb/miniforge3/envs/nephroperturb/bin/python}
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
cd "$ROOT/backend"
export NEPHRO_MCP_TRANSPORT=${NEPHRO_MCP_TRANSPORT:-streamable-http}
exec "$PY" -m app.mcp_server
