#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$(pwd)}"
VENV="${VENV:-/workspace/sr-venv}"
REPORT_DIR="${REPORT_DIR:-backend/training/reports/runpod_logs}"

cd "$ROOT"
mkdir -p "$REPORT_DIR"

echo "[bootstrap] root=$ROOT"
echo "[bootstrap] venv=$VENV"

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    unzip \
    python3-venv \
    python3-pip \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    ffmpeg
fi

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install --upgrade pip wheel setuptools

if ! python - <<'PY'
try:
    import torch
    print(f"[bootstrap] torch already installed: {torch.__version__}, cuda={torch.cuda.is_available()}")
except Exception:
    raise SystemExit(1)
PY
then
  echo "[bootstrap] torch missing, installing CUDA 12.4 wheels"
  python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
fi

python -m pip install -r requirements-runpod-hybrid.txt

python backend/training/scripts/check_gpu.py | tee "$REPORT_DIR/gpu_check.txt" || true
python backend/training/scripts/prepare_hybrid_redaction_pilot.py --validate-only | tee "$REPORT_DIR/bootstrap_validate.txt"

cat > "$REPORT_DIR/bootstrap_complete.txt" <<EOF
Bootstrap completed at $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Activate with: source $VENV/bin/activate
Run with: bash backend/training/scripts/runpod_hybrid_pilot.sh
Check with: python backend/training/scripts/runpod_status.py
EOF

echo "[bootstrap] complete"
