from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from training_utils import (
    CRITICAL_PII_TYPES,
    bbox_iou,
    character_error_rate,
    ensure_parent,
    mean,
    normalize_text,
    read_jsonl,
    token_recall,
    word_error_rate,
)


def load_predictions(path: str | Path) -> list[dict[str, Any]]:
    if not path:
        return []
    return read_jsonl(path)


def pii_values(row: dict[str, Any]) -> list[str]:
    values = []
    for item in row.get("pii_items") or []:
        if isinstance(item, dict) and item.get("value"):
            values.append(str(item["value"]))
    return values


def critical_pii_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in row.get("pii_items") or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type in CRITICAL_PII_TYPES:
            items.append(item)
    return items


def prediction_boxes(prediction: dict[str, Any]) -> list[list[float]]:
    boxes = []
    for word in prediction.get("words") or []:
        bbox = word.get("bbox") if isinstance(word, dict) else None
        if isinstance(bbox, list) and len(bbox) == 4 and isinstance(bbox[0], list):
            xs = [float(point[0]) for point in bbox]
            ys = [float(point[1]) for point in bbox]
            boxes.append([min(xs), min(ys), max(xs), max(ys)])
        elif isinstance(bbox, list) and len(bbox) == 4:
            boxes.append([float(value) for value in bbox])
    return boxes


def score_redaction_mapping(expected_items: list[dict[str, Any]], predicted_boxes: list[list[float]], iou_threshold: float) -> dict[str, Any]:
    if not expected_items:
        return {"expected": 0, "mapped": 0, "success": 1.0, "missed": []}

    mapped = 0
    missed = []
    for item in expected_items:
        expected_box = item.get("bbox")
        best = max((bbox_iou(expected_box, box) for box in predicted_boxes), default=0.0)
        if best >= iou_threshold:
            mapped += 1
        else:
            missed.append({"type": item.get("type"), "value": item.get("value"), "best_iou": round(best, 4)})
    return {
        "expected": len(expected_items),
        "mapped": mapped,
        "success": mapped / len(expected_items),
        "missed": missed,
    }


def low_confidence_review_accuracy(predictions: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    if not predictions:
        return {"rows": 0, "accuracy": None}
    correct = 0
    for prediction in predictions:
        confidence = float(prediction.get("confidence") or 0.0)
        cer = float(prediction.get("cer") if prediction.get("cer") is not None else 1.0)
        should_review = cer > 0.12 or any(item.get("expected_redaction_action") == "review" for item in prediction.get("pii_items") or [])
        triggered = confidence < threshold
        if triggered == should_review:
            correct += 1
    return {"rows": len(predictions), "accuracy": correct / len(predictions)}


def evaluate_backend(name: str, predictions: list[dict[str, Any]], iou_threshold: float, review_threshold: float) -> dict[str, Any]:
    if not predictions:
        return {
            "status": "no_predictions",
            "rows": 0,
        }

    cers = []
    wers = []
    line_hits = 0
    field_expected = 0
    field_found = 0
    pii_expected = 0
    pii_found = 0
    critical_expected = 0
    critical_missed: list[dict[str, Any]] = []
    mapping_scores = []
    mapping_missed: list[dict[str, Any]] = []

    for prediction in predictions:
        truth = str(prediction.get("truth") or "")
        text = str(prediction.get("prediction") or "")
        cer = character_error_rate(text, truth)
        wer = word_error_rate(text, truth)
        cers.append(cer)
        wers.append(wer)
        if normalize_text(text) == normalize_text(truth):
            line_hits += 1

        pii = prediction.get("pii_items") or []
        pii_recall = token_recall(text, [item.get("value") for item in pii if isinstance(item, dict)])
        pii_expected += pii_recall["expected"]
        pii_found += pii_recall["found"]

        field_recall = token_recall(text, pii_values(prediction))
        field_expected += field_recall["expected"]
        field_found += field_recall["found"]

        critical = critical_pii_items(prediction)
        critical_expected += len(critical)
        pred_norm = normalize_text(text)
        for item in critical:
            if normalize_text(item.get("value", "")) not in pred_norm:
                critical_missed.append({"type": item.get("type"), "value": item.get("value")})

        mapping = score_redaction_mapping(pii, prediction_boxes(prediction), iou_threshold)
        mapping_scores.append(mapping["success"])
        mapping_missed.extend(mapping["missed"])

    return {
        "status": "complete",
        "rows": len(predictions),
        "cer": round(mean(cers), 4),
        "wer": round(mean(wers), 4),
        "line_recognition_accuracy": round(line_hits / len(predictions), 4),
        "field_level_recall": round(field_found / field_expected, 4) if field_expected else 1.0,
        "pii_recall": round(pii_found / pii_expected, 4) if pii_expected else 1.0,
        "critical_pii_false_negative_count": len(critical_missed),
        "critical_pii_missed": critical_missed[:25],
        "redaction_box_mapping_success": round(mean(mapping_scores), 4),
        "redaction_mapping_missed": mapping_missed[:25],
        "low_confidence_review_trigger_accuracy": low_confidence_review_accuracy(predictions, review_threshold),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate handwriting OCR and redaction mapping predictions.")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output-report", default="backend/training/reports/handwriting_ocr_eval_report.json")
    parser.add_argument("--iou-threshold", type=float, default=0.35)
    parser.add_argument("--review-confidence-threshold", type=float, default=0.70)
    args = parser.parse_args()

    predictions = load_predictions(args.predictions)
    by_backend: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        by_backend[str(prediction.get("backend") or "unknown")].append(prediction)

    report = {
        "predictions": str(Path(args.predictions).resolve()),
        "metrics": {
            "cer": "character error rate, lower is better",
            "wer": "word error rate, lower is better",
            "field_level_recall": "share of expected answer-key field values found in OCR text",
            "pii_recall": "share of expected PII values found in OCR text",
            "critical_pii_false_negative_count": "critical PII values missing from OCR output",
            "redaction_box_mapping_success": "expected PII boxes matched by OCR word boxes at IoU threshold",
            "low_confidence_review_trigger_accuracy": "whether low confidence would send risky rows to review",
        },
        "targets": {
            "first_fake_council_cer_goal": 0.12,
            "critical_pii_recall_before_real_pilot": 0.99,
            "handwriting_auto_release_during_pilot": False,
        },
        "backends": {},
    }

    for backend_name, backend_predictions in sorted(by_backend.items()):
        report["backends"][backend_name] = evaluate_backend(
            backend_name,
            backend_predictions,
            args.iou_threshold,
            args.review_confidence_threshold,
        )

    if not by_backend:
        report["backends"]["none"] = {"status": "no_predictions", "rows": 0}

    out = ensure_parent(args.output_report)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
