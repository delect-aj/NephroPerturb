#!/usr/bin/env bash
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
PY=${PY:-/public/home/dongb/miniforge3/envs/nephroperturb/bin/python}
cd "$ROOT/backend"
exec "$PY" -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8091}" --workers 1
