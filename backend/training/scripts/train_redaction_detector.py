from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a YOLO redaction-region detector for Synthetiq Redact.")
    parser.add_argument("--data", default="backend/training/exports/hybrid_redaction_pilot/detector_dataset/data.yaml")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=-1)
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default="backend/training/models")
    parser.add_argument("--name", default="synthetiq-redaction-detector")
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "data": str(Path(args.data).resolve()),
                    "model": args.model,
                    "epochs": args.epochs,
                    "imgsz": args.imgsz,
                    "batch": args.batch,
                    "device": args.device,
                    "project": str(Path(args.project).resolve()),
                    "name": args.name,
                },
                indent=2,
            )
        )
        return 0

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError("Install ultralytics before detector training.") from exc

    model = YOLO(args.model)
    result = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        patience=args.patience,
        plots=True,
        exist_ok=True,
    )
    run_dir = Path(result.save_dir)
    best = run_dir / "weights" / "best.pt"
    print(json.dumps({"status": "complete", "run_dir": str(run_dir.resolve()), "best_model": str(best.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
