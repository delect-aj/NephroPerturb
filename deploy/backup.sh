#!/usr/bin/env bash
# Archive metadata DB + annotations + model artifacts (matrices excluded: rebuildable).
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
DEST=${DEST:-/public/home/dongb/backup}
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d_%H%M%S)
tar -czf "$DEST/nephroperturb_meta_$STAMP.tar.gz" \
  -C "$ROOT" store/nephroperturb.db store/annotations store/models \
  store/cp_index.parquet store/genetic_index.parquet config scripts backend
sha256sum "$DEST/nephroperturb_meta_$STAMP.tar.gz" > "$DEST/nephroperturb_meta_$STAMP.sha256"
echo "backup: $DEST/nephroperturb_meta_$STAMP.tar.gz"
