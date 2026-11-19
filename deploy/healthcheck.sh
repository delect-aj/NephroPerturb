#!/usr/bin/env bash
set -euo pipefail
api=${API_URL:-http://127.0.0.1:8091}
web=${WEB_URL:-http://127.0.0.1:3000}
curl -fsS "$api/health" > /dev/null && echo "api ok" || { echo "api DOWN"; exit 1; }
curl -fsS -o /dev/null -w "web %{http_code}\n" "$web/" || { echo "web DOWN"; exit 1; }
