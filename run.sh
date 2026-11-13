#!/usr/bin/env bash
# Kept for compatibility: ./run.sh <pdf> <work_dir>  (UPLOAD=1 to upload, CONFIG=path for another config).
args=(run "$1" "$2"); [ -n "${CONFIG:-}" ] && args+=(-c "$CONFIG"); [ "${UPLOAD:-0}" = 1 ] && args+=(--upload)
exec python3 "$(dirname "$0")/pipeline.py" "${args[@]}"
