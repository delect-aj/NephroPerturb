#!/usr/bin/env bash
# Bootstrap NephroPerturb on a fresh Linux server (no root required).
# Usage: bash deploy/bootstrap.sh [/path/to/app-dir]
# Assumes: git clone already done; store/ artifacts transferred separately
#          (see deploy/DEPLOY.md); internet access for conda/pip/npm.
set -euo pipefail
APP_DIR=$(cd "${1:-$(pwd)}" && pwd)
ENV_NAME=${ENV_NAME:-nephroperturb}
CONDA_HOME=${CONDA_HOME:-$HOME/miniforge3}
PY="$CONDA_HOME/envs/$ENV_NAME/bin/python"
BIN="$CONDA_HOME/envs/$ENV_NAME/bin"
cd "$APP_DIR"

echo "== [1/6] Miniforge"
if [ ! -x "$CONDA_HOME/bin/conda" ]; then
  curl -fsSL -o /tmp/miniforge.sh \
    https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash /tmp/miniforge.sh -b -p "$CONDA_HOME"
fi

echo "== [2/6] Conda env ($ENV_NAME: python 3.11 + node 20)"
[ -x "$PY" ] || "$CONDA_HOME/bin/conda" create -y -n "$ENV_NAME" python=3.11 nodejs=20

echo "== [3/6] Python runtime deps"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r backend/requirements.txt

echo "== [4/6] Store artifacts check"
if [ ! -f store/nephroperturb.db ] || [ ! -f store/matrices/kprl_cp_zscore.npy ]; then
  echo "ERROR: store/ missing. Transfer it first (see deploy/DEPLOY.md step 2)." >&2
  exit 1
fi
mkdir -p store/annotations/raw logs

echo "== [5/6] Frontend build"
[ -f .env ] || { cp .env.example .env; echo "NOTE: edit .env and set DEEPSEEK_API_KEY"; }
if [ ! -d frontend/node_modules ]; then
  (cd frontend && PATH="$BIN:$PATH" npm ci)
fi
(cd frontend && PATH="$BIN:$PATH" npm run build)

echo "== [6/6] Start services"
export ROOT="$APP_DIR" PY="$PY"
setsid nohup deploy/run_api.sh > logs/api.log 2>&1 < /dev/null &
setsid nohup deploy/run_mcp.sh > logs/mcp.log 2>&1 < /dev/null &
(cd frontend && PATH="$BIN:$PATH" setsid nohup npm run start > ../logs/web.log 2>&1 < /dev/null &)
sleep 10
echo "-- health:"
curl -s --max-time 10 http://127.0.0.1:8091/health || true
echo
echo "-- web:"
curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 http://127.0.0.1:3000/ || true
echo "Done. Logs in $APP_DIR/logs/. API :8091  MCP :8092  Web :3000"
