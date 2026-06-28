from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = [
    ("validate", "Dataset validation"),
    ("ocr_baseline", "OCR baseline"),
    ("ocr_eval", "PII recall evaluation"),
    ("autolabel", "Detector auto-labels"),
    ("detector_train", "Detector training"),
]


def read_text(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "unreadable", "error": str(exc)}


def file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    return max(0.0, datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)


def summarize_reports(base: Path) -> dict[str, Any]:
    report_dir = base / "backend/training/reports"
    export_dir = base / "backend/training/exports/hybrid_redaction_pilot"
    model_dir = base / "backend/training/models/synthetiq-redaction-detector"
    ocr = read_json(report_dir / "runpod_ocr_baseline_report.json")
    eval_report = read_json(report_dir / "runpod_ocr_eval_report.json")
    autolabel = read_json(export_dir / "detector_dataset/autolabel_report.json")
    best_model = model_dir / "weights/best.pt"
    return {
        "ocr_backends": ocr.get("backends", {}),
        "pii_eval": eval_report.get("backends", {}),
        "autolabel": autolabel,
        "best_model_exists": best_model.exists(),
        "best_model": str(best_model) if best_model.exists() else None,
    }


def build_status(base: Path, rate: float) -> dict[str, Any]:
    log_dir = base / "backend/training/reports/runpod_logs"
    stamp_dir = log_dir / "stamps"
    current_stage_path = log_dir / "current_stage.txt"
    started_path = log_dir / "run_started_at.txt"
    started = read_text(started_path, 200).strip()
    current_stage = read_text(current_stage_path, 200).strip()

    if started_path.exists():
        elapsed_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - started_path.stat().st_mtime) / 3600.0)
    else:
        elapsed_hours = 0.0

    stages = []
    for key, label in STAGES:
        done = (stamp_dir / f"{key}.done").exists()
        failed = (stamp_dir / f"{key}.failed").exists()
        log_path = log_dir / f"{key}.log"
        stages.append(
            {
                "stage": key,
                "label": label,
                "status": "failed" if failed else "complete" if done else "running" if current_stage == key else "pending",
                "log": str(log_path),
                "log_age_seconds": file_age_seconds(log_path),
            }
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started,
        "current_stage": current_stage,
        "elapsed_hours_estimate": round(elapsed_hours, 3),
        "estimated_gpu_cost_usd": round(elapsed_hours * rate, 2),
        "gpu_rate_usd_per_hour": rate,
        "stages": stages,
        "reports": summarize_reports(base),
        "last_log_tail": read_text(log_dir / f"{current_stage}.log") if current_stage else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize RunPod hybrid pilot progress.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--rate", type=float, default=1.396)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    status = build_status(Path(args.root), args.rate)
    if args.json:
        print(json.dumps(status, indent=2))
        return 0

    print("Synthetiq Redact RunPod status")
    print(f"Checked: {status['checked_at']}")
    print(f"Current stage: {status['current_stage'] or 'not started'}")
    print(f"Estimated cost so far: ${status['estimated_gpu_cost_usd']} at ${status['gpu_rate_usd_per_hour']}/hr")
    print("")
    for stage in status["stages"]:
        print(f"- {stage['stage']}: {stage['status']}")
    print("")
    reports = status["reports"]
    if reports["ocr_backends"]:
        print("OCR report found.")
    if reports["pii_eval"]:
        print("PII evaluation report found.")
    if reports["autolabel"]:
        print("Auto-label report found.")
    if reports["best_model_exists"]:
        print(f"Best detector model: {reports['best_model']}")
    if status["last_log_tail"]:
        print("")
        print("Latest log tail:")
        print(status["last_log_tail"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
