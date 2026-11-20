#!/usr/bin/env bash
# Lightweight bootstrap for a 2 vCPU / 2 GB RAM / 20 GB Disk Linux server.
# No Docker, no Conda, no Node.js required (uses prebuilt store_lite/ & frontend/out/).
set -euo pipefail
APP_DIR=$(cd "${1:-$(pwd)}" && pwd)
cd "$APP_DIR"

echo "== [1/5] Check Python >=3.10"
PY_SYS=$(command -v python3)
"$PY_SYS" -c "import sys; assert sys.version_info >= (3, 10), sys.version"

echo "== [2/5] Create isolated venv & install requirements-lite.txt"
if [ ! -x "$APP_DIR/.venv-lite/bin/python" ]; then
  "$PY_SYS" -m venv "$APP_DIR/.venv-lite"
fi
PY="$APP_DIR/.venv-lite/bin/python"
"$PY" -m pip install --no-cache-dir --upgrade pip
"$PY" -m pip install --no-cache-dir -r backend/requirements-lite.txt

echo "== [3/5] Check store_lite/ and frontend/out/"
if [ ! -f "$APP_DIR/store_lite/lite_manifest.json" ] || [ ! -f "$APP_DIR/store_lite/nephroperturb.db" ]; then
  echo "ERROR: store_lite/ missing. Rsync store_lite/ first (see deploy/DEPLOY_LITE.md)." >&2
  exit 1
fi
if [ ! -f "$APP_DIR/frontend/out/index.html" ]; then
  echo "ERROR: frontend/out/ missing. Rsync prebuilt frontend/out/ first." >&2
  exit 1
fi
mkdir -p "$APP_DIR/logs"
[ -f "$APP_DIR/.env" ] || { cp "$APP_DIR/.env.example" "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"; }

echo "== [4/5] Start single-process Lite server (:8091)"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1
ROOT="$APP_DIR" PY="$PY" setsid nohup "$APP_DIR/deploy/run_lite.sh" > "$APP_DIR/logs/lite.log" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$APP_DIR/.lite.pid"
sleep 5

echo "== [5/5] Health & RSS check"
curl -fsS "http://127.0.0.1:${PORT:-8091}/health" && echo
curl -fsS -o /dev/null -w "UI HTTP %{http_code}\n" "http://127.0.0.1:${PORT:-8091}/"
grep -E "VmRSS|VmHWM|Threads" "/proc/$PID/status" || true
echo "Done. Logs: $APP_DIR/logs/lite.log"
