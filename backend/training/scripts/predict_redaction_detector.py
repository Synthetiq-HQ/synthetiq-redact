"""
Standalone CLI for the trained image redaction detector.

Runs the detector on a single image and writes an overlay PNG (boxes drawn) plus a
JSON file of boxes/confidences. Useful for testing the model outside the app.

Example (Windows PowerShell):
    cd "C:\\Users\\INTERPOL\\OneDrive\\Documents\\REDACT\\synthetiq-redact"
    python backend/training/scripts/predict_redaction_detector.py \
        --image "C:\\Users\\INTERPOL\\Downloads\\DOC-001_02.png" \
        --out "C:\\Users\\INTERPOL\\Downloads\\synthetiq_detector_cli_test"

The model path defaults to the same env vars / local best.pt fallback used by the
backend service, so it stays in sync with what the app uses.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Make the backend package importable so we reuse the shared detector service.
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Synthetiq redaction detector on an image.")
    parser.add_argument("--image", required=True, help="Path to the input page image.")
    parser.add_argument("--model", default=None, help="Optional model path override (defaults to configured model).")
    parser.add_argument("--out", required=True, help="Output directory for overlay + JSON.")
    parser.add_argument("--conf", type=float, default=None, help="Confidence threshold (default from config).")
    args = parser.parse_args()

    if args.model:
        # Honour an explicit override via the env var the service reads.
        os.environ["SYNTHETIQ_REDACT_DETECTOR_MODEL"] = args.model
    if args.conf is not None:
        os.environ["REDACTION_DETECTOR_CONF"] = str(args.conf)

    if not os.path.exists(args.image):
        print(f"Input image not found: {args.image}")
        return 2

    from image_redaction_detector import get_detector, DetectorUnavailableError

    detector = get_detector()
    if not detector.available:
        print(f"Detector unavailable: {detector.unavailable_reason}")
        return 3

    try:
        predictions = detector.predict(args.image, page_number=1)
    except DetectorUnavailableError as exc:
        print(f"Detector unavailable: {exc}")
        return 3

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.image).stem

    # Draw overlay.
    from PIL import Image, ImageDraw

    with Image.open(args.image) as src:
        overlay = src.convert("RGB")
        draw = ImageDraw.Draw(overlay)
        for pred in predictions:
            x, y, w, h = pred["x"], pred["y"], pred["w"], pred["h"]
            draw.rectangle((x, y, x + w, y + h), outline=(220, 38, 38), width=3)
            draw.text((x + 2, max(0, y - 12)), f"{pred['confidence']:.2f}", fill=(220, 38, 38))

    overlay_path = out_dir / f"{stem}_overlay.png"
    overlay.save(overlay_path, "PNG")

    json_path = out_dir / f"{stem}_predictions.json"
    payload = {
        "image": os.path.basename(args.image),
        "count": len(predictions),
        "conf_threshold": detector.conf_threshold,
        "boxes": [
            {
                "x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"],
                "confidence": p["confidence"],
                "redaction_type": p["redaction_type"],
            }
            for p in predictions
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Detected {len(predictions)} candidate box(es).")
    print(f"Overlay: {overlay_path}")
    print(f"JSON:    {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
