#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_DIR/.env.mac-ssd"

if [[ ! -d /Volumes/ZX20 ]]; then
  echo "SSD not found at /Volumes/ZX20. Plug in the SSD before starting Synthetiq Redact." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Run scripts/setup_mac_ssd.sh first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

mkdir -p "$UPLOAD_DIR" "$PROCESSED_DIR"

echo "Starting Synthetiq Redact with SSD storage:"
echo "  Data: $SYNTHETIQ_REDACT_DATA_DIR"
echo "  DB:   $DB_PATH"
echo ""

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

(cd "$REPO_DIR/backend" && venv/bin/python -m uvicorn main_v2:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

(cd "$REPO_DIR/frontend" && npm run dev -- --host 127.0.0.1 --port 5173) &
FRONTEND_PID=$!

echo "Backend:  http://127.0.0.1:8000"
echo "Frontend: http://127.0.0.1:5173"
echo "Press Ctrl+C to stop both services."

wait
