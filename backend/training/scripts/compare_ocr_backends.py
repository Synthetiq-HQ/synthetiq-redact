from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from training_utils import character_error_rate, ensure_parent, read_manifest, word_error_rate, write_jsonl


class BackendResult(dict):
    pass


def crop_image(row: dict[str, Any], temp_dir: Path) -> Path:
    image_path = Path(row["image_path"])
    bbox = row.get("line_bbox")
    if not bbox:
        return image_path
    with Image.open(image_path) as image:
        x0, y0, x1, y1 = [int(float(value)) for value in bbox]
        crop = image.crop((max(0, x0 - 8), max(0, y0 - 6), min(image.width, x1 + 8), min(image.height, y1 + 6)))
        out = temp_dir / f"{image_path.stem}_{abs(hash(str(bbox)))}.png"
        crop.save(out)
        return out


def easyocr_backend(gpu: bool) -> Callable[[Path], BackendResult]:
    try:
        import easyocr
    except Exception as exc:
        raise RuntimeError(f"EasyOCR not installed: {exc}") from exc

    reader = easyocr.Reader(["en"], gpu=gpu)

    def run(image_path: Path) -> BackendResult:
        results = reader.readtext(str(image_path), detail=1)
        words = []
        confidences = []
        text_parts = []
        for bbox, text, confidence in results:
            clean_bbox = [[int(point[0]), int(point[1])] for point in bbox]
            words.append({"text": text, "bbox": clean_bbox, "confidence": float(confidence)})
            text_parts.append(text)
            confidences.append(float(confidence))
        return BackendResult(
            text=" ".join(text_parts),
            confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            words=words,
        )

    return run


def paddleocr_backend(use_gpu: bool) -> Callable[[Path], BackendResult]:
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR not installed: {exc}") from exc

    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=use_gpu, show_log=False)

    def run(image_path: Path) -> BackendResult:
        result = ocr.ocr(str(image_path), cls=True)
        words = []
        confidences = []
        text_parts = []
        for page in result or []:
            for line in page or []:
                bbox, payload = line
                text, confidence = payload
                words.append({"text": text, "bbox": bbox, "confidence": float(confidence)})
                text_parts.append(text)
                confidences.append(float(confidence))
        return BackendResult(
            text=" ".join(text_parts),
            confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            words=words,
        )

    return run


def trocr_backend(model_path: str, processor_path: str | None, device: str) -> Callable[[Path], BackendResult]:
    if not model_path:
        raise RuntimeError("TrOCR skipped because --trocr-model was not supplied.")
    try:
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except Exception as exc:
        raise RuntimeError(f"TrOCR dependencies not installed: {exc}") from exc

    processor = TrOCRProcessor.from_pretrained(processor_path or model_path)
    model = VisionEncoderDecoderModel.from_pretrained(model_path)
    actual_device = "cuda" if device == "cuda" and torch.cuda.is_available() else "cpu"
    model.to(actual_device)
    model.eval()

    def run(image_path: Path) -> BackendResult:
        image = Image.open(image_path).convert("RGB")
        pixel_values = processor(images=image, return_tensors="pt").pixel_values.to(actual_device)
        with torch.inference_mode():
            generated_ids = model.generate(pixel_values, max_new_tokens=128)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return BackendResult(text=text, confidence=0.0, words=[])

    return run


def surya_backend() -> Callable[[Path], BackendResult]:
    try:
        import surya  # noqa: F401
    except Exception as exc:
        raise RuntimeError(f"Surya not installed: {exc}") from exc
    raise RuntimeError("Surya API varies by release; install it and wire a local adapter before scoring.")


def build_backend(name: str, args: argparse.Namespace) -> Callable[[Path], BackendResult]:
    if name == "easyocr":
        return easyocr_backend(gpu=args.gpu)
    if name == "paddleocr":
        return paddleocr_backend(use_gpu=args.gpu)
    if name == "trocr":
        return trocr_backend(args.trocr_model, args.trocr_processor, args.device)
    if name == "surya":
        return surya_backend()
    raise ValueError(f"Unknown backend: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare OCR backends on a Synthetiq JSONL manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-report", default="backend/training/reports/baseline_ocr_report.json")
    parser.add_argument("--predictions", default="backend/training/reports/baseline_ocr_predictions.jsonl")
    parser.add_argument("--backends", default="easyocr,paddleocr,surya,trocr")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--trocr-model", default="")
    parser.add_argument("--trocr-processor", default="")
    args = parser.parse_args()

    rows = read_manifest(args.manifest)
    if args.limit:
        rows = rows[: args.limit]

    selected = [name.strip().lower() for name in args.backends.split(",") if name.strip()]
    predictions: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "manifest": str(Path(args.manifest).resolve()),
        "rows_requested": len(rows),
        "backends": {},
    }

    with tempfile.TemporaryDirectory(prefix="synthetiq_ocr_") as tmp:
        temp_dir = Path(tmp)
        for backend_name in selected:
            try:
                runner = build_backend(backend_name, args)
            except Exception as exc:
                report["backends"][backend_name] = {"status": "skipped", "reason": str(exc)}
                continue

            timings = []
            cers = []
            wers = []
            usable = 0
            backend_errors: list[str] = []

            for index, row in enumerate(rows):
                try:
                    input_path = crop_image(row, temp_dir)
                    start = time.perf_counter()
                    result = runner(input_path)
                    elapsed = time.perf_counter() - start
                    text = str(result.get("text") or "")
                    truth = str(row.get("text") or "")
                    cer = character_error_rate(text, truth)
                    wer = word_error_rate(text, truth)
                    timings.append(elapsed)
                    cers.append(cer)
                    wers.append(wer)
                    usable += 1
                    predictions.append(
                        {
                            "backend": backend_name,
                            "image_path": row.get("image_path"),
                            "page_number": row.get("page_number", 1),
                            "line_bbox": row.get("line_bbox"),
                            "truth": truth,
                            "prediction": text,
                            "confidence": result.get("confidence", 0.0),
                            "words": result.get("words", []),
                            "cer": cer,
                            "wer": wer,
                            "elapsed_seconds": round(elapsed, 4),
                            "pii_items": row.get("pii_items", []),
                        }
                    )
                except Exception as exc:
                    backend_errors.append(f"row {index}: {exc}")

            report["backends"][backend_name] = {
                "status": "complete" if usable else "failed",
                "rows": usable,
                "avg_cer": round(sum(cers) / len(cers), 4) if cers else None,
                "avg_wer": round(sum(wers) / len(wers), 4) if wers else None,
                "avg_seconds_per_row": round(sum(timings) / len(timings), 4) if timings else None,
                "errors": backend_errors[:10],
            }

    predictions_path = write_jsonl(ensure_parent(args.predictions), predictions)
    report["predictions"] = str(predictions_path.resolve())
    report_path = ensure_parent(args.output_report)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
