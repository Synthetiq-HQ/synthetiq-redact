from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from pathlib import Path
from typing import Any

from training_utils import ensure_parent, write_jsonl


def split_for_index(index: int, train_ratio: float, validation_ratio: float) -> str:
    bucket = (index % 1000) / 1000
    if bucket < train_ratio:
        return "train"
    if bucket < train_ratio + validation_ratio:
        return "validation"
    return "test"


def row_from_mapping(
    image_path: str,
    text: str,
    split: str,
    source: str,
    licence: str,
    document_type: str = "handwriting_line",
    line_bbox: list[int] | None = None,
    synthetic: bool = False,
) -> dict[str, Any]:
    return {
        "image_path": image_path,
        "text": text,
        "split": split,
        "source": source,
        "licence": licence,
        "document_type": document_type,
        "page_number": 1,
        "line_bbox": line_bbox,
        "word_bboxes": [],
        "pii_items": [],
        "synthetic": synthetic,
    }


def prepare_local_csv(args: argparse.Namespace) -> list[dict[str, Any]]:
    metadata_path = Path(args.metadata)
    image_root = Path(args.image_root or metadata_path.parent)
    rows: list[dict[str, Any]] = []

    with metadata_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader):
            image_value = raw.get(args.image_column) or raw.get("image_path") or raw.get("image")
            text_value = raw.get(args.text_column) or raw.get("text") or raw.get("transcription")
            if not image_value or not text_value:
                continue
            image_path = Path(image_value)
            if not image_path.is_absolute():
                image_path = image_root / image_path
            split = raw.get("split") or split_for_index(index, args.train_ratio, args.validation_ratio)
            rows.append(
                row_from_mapping(
                    image_path=str(image_path.resolve()),
                    text=text_value,
                    split=split,
                    source=args.source_name,
                    licence=args.licence,
                    document_type=raw.get("document_type") or "handwriting_line",
                    synthetic=False,
                )
            )
    return rows


def prepare_huggingface(args: argparse.Namespace) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except Exception as exc:
        raise RuntimeError("Install datasets to prepare Hugging Face handwriting corpora.") from exc

    dataset = load_dataset(args.hf_dataset, args.hf_config) if args.hf_config else load_dataset(args.hf_dataset)
    output_images = Path(args.output_images)
    output_images.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for split_name, split_data in dataset.items():
        for index, sample in enumerate(split_data):
            image = sample.get(args.image_column) or sample.get("image")
            text = sample.get(args.text_column) or sample.get("text") or sample.get("transcription")
            if image is None or text is None:
                continue
            image_out = output_images / f"{args.source_name}_{split_name}_{index:08d}.png"
            if hasattr(image, "save"):
                image.save(image_out)
            elif isinstance(image, (str, Path)):
                shutil.copy2(image, image_out)
            else:
                continue
            rows.append(
                row_from_mapping(
                    image_path=str(image_out.resolve()),
                    text=str(text),
                    split="validation" if split_name in {"validation", "valid", "dev"} else split_name,
                    source=args.source_name,
                    licence=args.licence,
                    synthetic=False,
                )
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare handwriting datasets into Synthetiq OCR JSONL manifests.")
    parser.add_argument("--mode", choices=["local_csv", "huggingface"], required=True)
    parser.add_argument("--output", default="backend/training/datasets/handwriting_manifest.jsonl")
    parser.add_argument("--source-name", default="handwriting_public")
    parser.add_argument("--licence", default="licence_review_required")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)

    parser.add_argument("--metadata", help="CSV with image_path and text columns for local_csv mode.")
    parser.add_argument("--image-root", help="Root for relative image paths in local_csv metadata.")
    parser.add_argument("--image-column", default="image_path")
    parser.add_argument("--text-column", default="text")

    parser.add_argument("--hf-dataset", help="Hugging Face dataset id.")
    parser.add_argument("--hf-config", default=None)
    parser.add_argument("--output-images", default="backend/training/datasets/hf_images")
    args = parser.parse_args()

    random.seed(args.seed)
    if args.mode == "local_csv":
        if not args.metadata:
            parser.error("--metadata is required for local_csv mode")
        rows = prepare_local_csv(args)
    else:
        if not args.hf_dataset:
            parser.error("--hf-dataset is required for huggingface mode")
        rows = prepare_huggingface(args)

    random.shuffle(rows)
    output = write_jsonl(ensure_parent(args.output), rows)
    summary = {
        "output": str(output),
        "rows": len(rows),
        "splits": {split: sum(1 for row in rows if row["split"] == split) for split in sorted({row["split"] for row in rows})},
        "source": args.source_name,
        "licence": args.licence,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
