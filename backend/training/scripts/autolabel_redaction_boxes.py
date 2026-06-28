from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def bbox_to_xyxy(raw: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, list):
        return None
    if len(raw) == 4 and all(isinstance(value, (int, float)) for value in raw):
        x0, y0, x1, y1 = [float(value) for value in raw]
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    if len(raw) >= 4 and all(isinstance(point, list) and len(point) >= 2 for point in raw):
        xs = [float(point[0]) for point in raw]
        ys = [float(point[1]) for point in raw]
        return min(xs), min(ys), max(xs), max(ys)
    return None


def union_box(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float] | None:
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def to_yolo(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    x0 = max(0.0, min(float(width), x0))
    x1 = max(0.0, min(float(width), x1))
    y0 = max(0.0, min(float(height), y0))
    y1 = max(0.0, min(float(height), y1))
    cx = ((x0 + x1) / 2.0) / width
    cy = ((y0 + y1) / 2.0) / height
    bw = max(1.0, x1 - x0) / width
    bh = max(1.0, y1 - y0) / height
    return cx, cy, bw, bh


def find_best_word_window(words: list[dict[str, Any]], target: str) -> tuple[int, int, float] | None:
    target_norm = compact(target)
    if len(target_norm) < 3:
        return None

    word_norms = [compact(str(word.get("text") or "")) for word in words]
    best: tuple[int, int, float] | None = None
    max_window = min(18, len(words))
    for start in range(len(words)):
        acc = ""
        for end in range(start, min(len(words), start + max_window)):
            acc += word_norms[end]
            if not acc:
                continue
            score = 0.0
            if target_norm in acc:
                score = min(1.0, len(target_norm) / max(len(acc), 1))
            elif acc in target_norm and len(acc) >= max(4, int(len(target_norm) * 0.45)):
                score = len(acc) / len(target_norm)
            else:
                overlap = longest_common_substring_len(acc, target_norm)
                score = overlap / max(len(target_norm), 1)
            if score >= 0.72 and (best is None or score > best[2]):
                best = (start, end + 1, score)
    return best


def longest_common_substring_len(a: str, b: str) -> int:
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        current = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                current[j] = previous[j - 1] + 1
                best = max(best, current[j])
        previous = current
    return best


def key_for_path(path_value: str) -> str:
    return Path(path_value).as_posix().lower()


def choose_backend(rows: list[dict[str, Any]], backend: str, preference: str) -> str:
    available = {
        str(row.get("backend") or "").lower()
        for row in rows
        if row.get("image_path")
    }
    if backend.lower() != "auto":
        return backend
    for candidate in [name.strip().lower() for name in preference.split(",") if name.strip()]:
        if candidate in available:
            return candidate
    return sorted(available)[0] if available else ""


def choose_predictions(rows: list[dict[str, Any]], backend: str) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        if backend and str(row.get("backend") or "").lower() != backend.lower():
            continue
        selected[key_for_path(str(row.get("image_path") or ""))] = row
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Create YOLO redaction labels from OCR word boxes and Synthetiq answer keys.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output-dir", default="backend/training/exports/hybrid_redaction_pilot/detector_dataset")
    parser.add_argument("--backend", default="paddleocr")
    parser.add_argument("--backend-preference", default="paddleocr,easyocr")
    parser.add_argument("--single-class", action="store_true", default=True)
    args = parser.parse_args()

    manifest_rows = read_jsonl(Path(args.manifest))
    prediction_rows = read_jsonl(Path(args.predictions))
    selected_backend = choose_backend(prediction_rows, args.backend, args.backend_preference)
    predictions = choose_predictions(prediction_rows, selected_backend)
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    metadata_rows: list[dict[str, Any]] = []
    summary = {
        "manifest_rows": len(manifest_rows),
        "prediction_rows": len(predictions),
        "images_with_labels": 0,
        "images_without_predictions": 0,
        "matched_items": 0,
        "missed_items": 0,
        "requested_backend": args.backend,
        "backend": selected_backend,
        "class_names": ["sensitive"],
    }

    for row in manifest_rows:
        image_path = Path(str(row["image_path"]))
        prediction = predictions.get(key_for_path(str(row["image_path"])))
        split = "val" if row.get("split") == "validation" else str(row.get("split") or "train")
        dst_image = output_dir / "images" / split / image_path.name
        dst_label = output_dir / "labels" / split / f"{image_path.stem}.txt"
        dst_image.parent.mkdir(parents=True, exist_ok=True)
        dst_label.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, dst_image)

        with Image.open(image_path) as image:
            width, height = image.size

        labels: list[str] = []
        item_records: list[dict[str, Any]] = []
        if not prediction:
            summary["images_without_predictions"] += 1
        else:
            words = [word for word in prediction.get("words", []) if isinstance(word, dict)]
            for item in row.get("pii_items", []):
                value = str(item.get("value") or "")
                match = find_best_word_window(words, value)
                if not match:
                    summary["missed_items"] += 1
                    item_records.append({"value": value, "type": item.get("type"), "status": "missed"})
                    continue
                start, end, score = match
                boxes = [bbox_to_xyxy(word.get("bbox")) for word in words[start:end]]
                merged = union_box([box for box in boxes if box is not None])
                if merged is None:
                    summary["missed_items"] += 1
                    item_records.append({"value": value, "type": item.get("type"), "status": "no_bbox"})
                    continue
                yolo_box = to_yolo(merged, width, height)
                labels.append("0 " + " ".join(f"{value:.6f}" for value in yolo_box))
                summary["matched_items"] += 1
                item_records.append(
                    {
                        "value": value,
                        "type": item.get("type"),
                        "status": "matched",
                        "match_score": round(score, 4),
                        "xyxy": [round(v, 2) for v in merged],
                    }
                )

        if labels:
            summary["images_with_labels"] += 1
        dst_label.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
        metadata_rows.append(
            {
                "document_id": row.get("document_id"),
                "image_path": str(dst_image),
                "label_path": str(dst_label),
                "split": split,
                "labels": item_records,
            }
        )

    data_yaml = output_dir / "data.yaml"
    data_yaml.write_text(
        "\n".join(
            [
                f"path: {output_dir.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                "  0: sensitive",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_jsonl(output_dir / "label_metadata.jsonl", metadata_rows)
    (output_dir / "autolabel_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "data_yaml": str(data_yaml.resolve()), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
