#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${MANIFEST:-backend/training/exports/hybrid_redaction_pilot/hybrid_manifest.jsonl}"
PREDICTIONS="${PREDICTIONS:-backend/training/reports/runpod_ocr_baseline_predictions.jsonl}"
REPORT_DIR="${REPORT_DIR:-backend/training/reports}"
LOG_DIR="${LOG_DIR:-backend/training/reports/runpod_logs}"
STAMP_DIR="$LOG_DIR/stamps"
RUNPOD_GPU_RATE_USD="${RUNPOD_GPU_RATE_USD:-1.396}"

mkdir -p "$REPORT_DIR" "$LOG_DIR" "$STAMP_DIR"

if [ ! -f "$LOG_DIR/run_started_at.txt" ]; then
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$LOG_DIR/run_started_at.txt"
fi

run_stage() {
  local name="$1"
  shift
  local done="$STAMP_DIR/$name.done"
  local failed="$STAMP_DIR/$name.failed"
  local log="$LOG_DIR/$name.log"

  if [ -f "$done" ]; then
    echo "[skip] $name already complete"
    return 0
  fi

  rm -f "$failed"
  echo "$name" > "$LOG_DIR/current_stage.txt"
  echo "[start] $name at $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  set +e
  {
    echo "[stage] $name"
    echo "[command] $*"
    "$@"
  } 2>&1 | tee "$log"
  local exit_code=${PIPESTATUS[0]}
  set -e

  if [ "$exit_code" -ne 0 ]; then
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$failed"
    echo "[failed] $name exit_code=$exit_code"
    python backend/training/scripts/runpod_status.py --rate "$RUNPOD_GPU_RATE_USD" || true
    return "$exit_code"
  fi

  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$done"
  echo "[done] $name"
  python backend/training/scripts/runpod_status.py --rate "$RUNPOD_GPU_RATE_USD" || true

  if [ "${STOP_AFTER_STAGE:-}" = "$name" ]; then
    echo "[stop] STOP_AFTER_STAGE=$name"
    exit 0
  fi
}

run_stage validate \
  python backend/training/scripts/prepare_hybrid_redaction_pilot.py --validate-only

run_stage ocr_baseline \
  python backend/training/scripts/compare_ocr_backends.py \
    --manifest "$MANIFEST" \
    --backends "${OCR_BACKENDS:-easyocr,paddleocr}" \
    --gpu \
    --limit "${LIMIT:-300}" \
    --output-report "$REPORT_DIR/runpod_ocr_baseline_report.json" \
    --predictions "$PREDICTIONS"

run_stage ocr_eval \
  python backend/training/scripts/eval_handwriting_ocr.py \
    --predictions "$PREDICTIONS" \
    --output-report "$REPORT_DIR/runpod_ocr_eval_report.json"

run_stage autolabel \
  python backend/training/scripts/autolabel_redaction_boxes.py \
    --manifest "$MANIFEST" \
    --predictions "$PREDICTIONS" \
    --backend "${AUTOLABEL_BACKEND:-auto}" \
    --output-dir backend/training/exports/hybrid_redaction_pilot/detector_dataset

run_stage detector_train \
  python backend/training/scripts/train_redaction_detector.py \
    --data backend/training/exports/hybrid_redaction_pilot/detector_dataset/data.yaml \
    --model "${MODEL:-yolo11n.pt}" \
    --epochs "${EPOCHS:-80}" \
    --imgsz "${IMGSZ:-1280}" \
    --batch "${BATCH:--1}" \
    --device "${DEVICE:-0}"

rm -f "$LOG_DIR/current_stage.txt"
echo "[complete] hybrid pilot finished at $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
python backend/training/scripts/runpod_status.py --rate "$RUNPOD_GPU_RATE_USD" || true
