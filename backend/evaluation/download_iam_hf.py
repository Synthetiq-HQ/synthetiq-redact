"""Download IAM handwritten form images from HuggingFace (kenza-ily/iam_disco).

These are real scanned handwritten forms. Labels are just 'handwritten' vs 'printed'
classification, not text transcriptions. We use them for realistic OCR/redaction
evaluation even without exact ground truth — the vision judge assesses quality."""

import os
import json
from pathlib import Path
from datasets import load_dataset


def download_iam_handwritten(output_dir: str, max_samples: int = 50):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Downloading IAM handwritten forms from HuggingFace to {out} ...")
    ds = load_dataset("kenza-ily/iam_disco", split="train", streaming=True)

    saved = 0
    for sample in ds:
        if sample["label"] != 0:  # 0 = handwritten, 1 = printed
            continue

        img = sample["image"]
        filename = f"iam_handwritten_{saved:04d}.png"
        img_path = out / filename
        img.save(img_path)

        # Minimal metadata (no exact transcription available in this HF dataset)
        meta = {
            "source": "kenza-ily/iam_disco",
            "split": "train",
            "label": "handwritten",
            "image_size": img.size,
            "ground_truth_text": None,  # Not provided by this HF mirror
        }
        with open(out / f"{filename}.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        saved += 1
        if saved >= max_samples:
            break

    print(f"Saved {saved} handwritten form images to {out}")
    return saved


if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    download_iam_handwritten(
        output_dir="evaluation/datasets/iam_forms", max_samples=count
    )
