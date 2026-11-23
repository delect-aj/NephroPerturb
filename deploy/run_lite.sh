#!/usr/bin/env bash
# Single-process, 1-core, <=1 GB RAM launcher serving REST API + MCP (/mcp) + Static Web UI (/).
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
if [ -n "${PY:-}" ]; then
  PYTHON="$PY"
elif [ -x "$ROOT/.venv-lite/bin/python" ]; then
  PYTHON="$ROOT/.venv-lite/bin/python"
elif [ -x "/public/home/dongb/miniforge3/envs/nephroperturb/bin/python" ]; then
  PYTHON="/public/home/dongb/miniforge3/envs/nephroperturb/bin/python"
else
  PYTHON="$(command -v python3)"
fi

[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

export NEPHRO_STORE="${NEPHRO_STORE:-$ROOT/store_lite}"
export NEPHRO_CONFIG="${NEPHRO_CONFIG:-$ROOT/config}"
export NEPHRO_MOUNT_MCP="${NEPHRO_MOUNT_MCP:-1}"
export NEPHRO_STATIC_DIR="${NEPHRO_STATIC_DIR:-$ROOT/frontend/out}"

# Strictly pin all BLAS / Arrow / OMP threads to 1 core
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export ARROW_NUM_THREADS=1

# Compute endpoints are serialized by _COMPUTE_LOCK in main.py; keep HTTP concurrency >=64
# so browsers can load static CSS/JS/SVG assets in parallel without HTTP 503.
# Legacy LIMIT_CONCURRENCY (e.g. 4 in older systemd units) is intentionally ignored.
HTTP_CONCURRENCY="${HTTP_CONCURRENCY:-128}"

cd "$ROOT/backend"
CMD=(
  "$PYTHON" -m uvicorn app.main:app
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8091}"
  --workers 1
  --limit-concurrency "$HTTP_CONCURRENCY"
)

if [ "${PIN_CPU0:-1}" = "1" ] && command -v taskset >/dev/null 2>&1; then
  exec taskset -c "${CPU_LIST:-0}" "${CMD[@]}"
else
  exec "${CMD[@]}"
fi
