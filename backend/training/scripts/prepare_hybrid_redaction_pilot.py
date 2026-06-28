from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except Exception:  # pragma: no cover - validation degrades gracefully
    Image = None


DEFAULT_DATASET_ROOT = Path("backend/training/datasets/synthetiq_redact_image_dataset")
DEFAULT_OUTPUT_DIR = Path("backend/training/exports/hybrid_redaction_pilot")
TRAIN_DOCS = set(range(1, 25))
VALIDATION_DOCS = set(range(25, 28))
TEST_DOCS = set(range(28, 31))
IMAGE_VARIATIONS = {
    1: "neat_blue_ink_plain_a4_left_tilt",
    2: "black_ballpoint_scanner_shadow",
    3: "typed_headings_handwritten_values_skewed_scan",
    4: "messy_legible_uneven_spacing",
    5: "phone_photo_desk_perspective",
    6: "faint_pencil_low_contrast",
    7: "older_photocopy_grey_minor_blur",
    8: "compact_handwriting_page_curl",
    9: "form_layout_printed_labels_handwritten_values",
    10: "rushed_handwriting_crossout",
}


@dataclass(frozen=True)
class PilotPaths:
    dataset_root: Path
    output_dir: Path
    manifest_path: Path
    audit_path: Path
    splits_path: Path
    runpod_readme_path: Path
    runpod_plan_path: Path
    package_root: Path
    package_zip: Path


def as_posix(path: Path) -> str:
    return path.as_posix()


def split_for_doc_number(doc_number: int) -> str:
    if doc_number in TRAIN_DOCS:
        return "train"
    if doc_number in VALIDATION_DOCS:
        return "validation"
    if doc_number in TEST_DOCS:
        return "test"
    return "holdout"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def image_dimensions(path: Path) -> tuple[int | None, int | None, str]:
    if Image is None:
        return None, None, "pillow_unavailable"
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return int(image.width), int(image.height), "ok"
    except Exception as exc:
        return None, None, f"invalid_image:{exc}"


def validate_and_build_manifest(dataset_root: Path, docs: range) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    doc_summaries: list[dict[str, Any]] = []
    problems: list[str] = []
    warnings: list[str] = []
    split_counts: dict[str, int] = {"train": 0, "validation": 0, "test": 0}
    pii_type_counts: dict[str, int] = {}

    for doc_number in docs:
        doc_id = f"DOC-{doc_number:03d}"
        doc_dir = dataset_root / doc_id
        image_dir = doc_dir / "images"
        prompt_path = doc_dir / "prompt.txt"
        answer_key_path = doc_dir / "answer_key.json"
        doc_problems: list[str] = []
        doc_warnings: list[str] = []

        if not doc_dir.exists():
            doc_problems.append("missing_doc_folder")
        if not prompt_path.exists():
            doc_problems.append("missing_prompt")
        if not answer_key_path.exists():
            doc_problems.append("missing_answer_key")
        if not image_dir.exists():
            doc_problems.append("missing_images_folder")

        answer_key: dict[str, Any] = {}
        ground_truth_text = ""
        sensitive_items: list[dict[str, Any]] = []
        document_type = "unknown"
        if answer_key_path.exists():
            answer_key = read_json(answer_key_path)
            ground_truth_text = str(answer_key.get("ground_truth_text") or "")
            sensitive_items = []
            for item in answer_key.get("sensitive_items", []):
                if not isinstance(item, dict):
                    continue
                normalized_item = {
                    "type": str(item.get("type") or "unknown"),
                    "value": str(item.get("value") or ""),
                    "expected_redaction_action": str(item.get("expected_action") or item.get("expected_redaction_action") or "review"),
                }
                value = normalized_item["value"]
                if value and value not in ground_truth_text:
                    doc_warnings.append(f"sensitive_value_not_in_truth:{normalized_item['type']}:{value}")
                    continue
                sensitive_items.append(normalized_item)
            document_type = str(answer_key.get("document_type") or "unknown")

            if not ground_truth_text.strip():
                doc_problems.append("empty_ground_truth_text")
            for item in sensitive_items:
                item_type = item["type"]
                pii_type_counts[item_type] = pii_type_counts.get(item_type, 0) + 1

        pngs = sorted(image_dir.glob("*.png")) if image_dir.exists() else []
        canonical = [path for path in pngs if path.name.startswith(f"{doc_id}_") and path.stem[-2:].isdigit()]
        stray = [path.name for path in pngs if path not in canonical]
        if len(pngs) != 10:
            doc_problems.append(f"png_count={len(pngs)}")
        if len(canonical) != 10:
            doc_problems.append(f"canonical_png_count={len(canonical)}")
        if stray:
            doc_problems.append("stray_pngs=" + ",".join(stray[:5]))

        split = split_for_doc_number(doc_number)
        for image_number in range(1, 11):
            image_name = f"{doc_id}_{image_number:02d}.png"
            image_path = image_dir / image_name
            width, height, image_status = image_dimensions(image_path) if image_path.exists() else (None, None, "missing_image")
            if image_status != "ok":
                doc_problems.append(f"{image_name}:{image_status}")
            rows.append(
                {
                    "document_id": doc_id,
                    "document_number": doc_number,
                    "document_type": document_type,
                    "image_number": image_number,
                    "variation": IMAGE_VARIATIONS[image_number],
                    "split": split,
                    "source": "synthetiq_redact_synthetic_council",
                    "licence": "synthetic_fake_only_internal",
                    "synthetic": True,
                    "image_path": as_posix(Path("backend/training/datasets/synthetiq_redact_image_dataset") / doc_id / "images" / image_name),
                    "prompt_path": as_posix(Path("backend/training/datasets/synthetiq_redact_image_dataset") / doc_id / "prompt.txt"),
                    "answer_key_path": as_posix(Path("backend/training/datasets/synthetiq_redact_image_dataset") / doc_id / "answer_key.json"),
                    "text": ground_truth_text,
                    "ground_truth_text": ground_truth_text,
                    "pii_items": sensitive_items,
                    "page_number": 1,
                    "line_bbox": None,
                    "word_bboxes": [],
                    "redaction_boxes": [],
                    "image_width": width,
                    "image_height": height,
                    "detector_label_status": "pending_ocr_autolabel",
                }
            )
            if split in split_counts:
                split_counts[split] += 1

        doc_summaries.append(
            {
                "document_id": doc_id,
                "document_type": document_type,
                "split": split,
                "png_count": len(pngs),
                "canonical_png_count": len(canonical),
                "prompt": prompt_path.exists(),
                "answer_key": answer_key_path.exists(),
                "problems": doc_problems,
                "warnings": doc_warnings,
            }
        )
        problems.extend([f"{doc_id}:{problem}" for problem in doc_problems])
        warnings.extend([f"{doc_id}:{warning}" for warning in doc_warnings])

    audit = {
        "dataset_root": str(dataset_root.resolve()),
        "status": "pass" if not problems else "fail",
        "expected_docs": len(list(docs)),
        "manifest_rows": len(rows),
        "split_counts": split_counts,
        "pii_type_counts": dict(sorted(pii_type_counts.items())),
        "document_summaries": doc_summaries,
        "problems": problems,
        "warnings": warnings,
    }
    return rows, audit


def runpod_readme() -> str:
    return """# Synthetiq Redact Hybrid Pilot - RunPod Handoff

This package is prepared locally. Upload it to a RunPod instance after the GPU is started.

## Recommended GPU

- Best value: A100 80GB
- Fast serious run: H100 80GB
- Big VLM checking: RTX PRO 6000 Blackwell 96GB

## RunPod setup

```bash
apt-get update
apt-get install -y git python3-venv python3-pip libgl1 libglib2.0-0
python3 -m venv /workspace/sr-venv
source /workspace/sr-venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements-runpod-hybrid.txt
```

If the CUDA 12.8 wheel is unavailable on the selected image, use the current PyTorch selector command from pytorch.org for the pod image.

## Preferred one-time bootstrap

After unzipping the package, run this instead of manually installing dependencies:

```bash
cd /workspace/synthetiq-redact
bash backend/training/scripts/runpod_bootstrap.sh
```

## Unpack location

Unzip this package into `/workspace/synthetiq-redact` so paths match the manifests:

```bash
cd /workspace
unzip synthetiq_redact_runpod_handoff.zip -d synthetiq-redact
cd /workspace/synthetiq-redact
```

## Validate package

```bash
python backend/training/scripts/prepare_hybrid_redaction_pilot.py --validate-only
```

## OCR/layout baseline

```bash
python backend/training/scripts/compare_ocr_backends.py \
  --manifest backend/training/exports/hybrid_redaction_pilot/hybrid_manifest.jsonl \
  --backends easyocr,paddleocr \
  --gpu \
  --limit 300 \
  --output-report backend/training/reports/runpod_ocr_baseline_report.json \
  --predictions backend/training/reports/runpod_ocr_baseline_predictions.jsonl
```

## Evaluate OCR/PII recall

```bash
python backend/training/scripts/eval_handwriting_ocr.py \
  --predictions backend/training/reports/runpod_ocr_baseline_predictions.jsonl \
  --output-report backend/training/reports/runpod_ocr_eval_report.json
```

## Auto-label redaction boxes

```bash
python backend/training/scripts/autolabel_redaction_boxes.py \
  --manifest backend/training/exports/hybrid_redaction_pilot/hybrid_manifest.jsonl \
  --predictions backend/training/reports/runpod_ocr_baseline_predictions.jsonl \
  --backend paddleocr \
  --output-dir backend/training/exports/hybrid_redaction_pilot/detector_dataset
```

## Train first redaction detector

```bash
python backend/training/scripts/train_redaction_detector.py \
  --data backend/training/exports/hybrid_redaction_pilot/detector_dataset/data.yaml \
  --model yolo11n.pt \
  --epochs 80 \
  --imgsz 1280 \
  --batch -1 \
  --device 0
```

## One-command pilot run

After dependencies are installed, this runs validation, OCR baseline, PII recall eval, auto-labelling, and detector training:

```bash
bash backend/training/scripts/runpod_hybrid_pilot.sh
```

For a background run that can continue while the browser is closed:

```bash
nohup bash backend/training/scripts/runpod_hybrid_pilot.sh > backend/training/reports/runpod_logs/full_run.log 2>&1 &
```

Check progress at any time:

```bash
python backend/training/scripts/runpod_status.py
```

The runner is resumable. Completed stages create stamps under `backend/training/reports/runpod_logs/stamps`.
To stop after a specific stage for a manual check:

```bash
STOP_AFTER_STAGE=ocr_eval bash backend/training/scripts/runpod_hybrid_pilot.sh
```

Do not train TrOCR directly on full-page images. If TrOCR is used, crop lines first.
"""


def runpod_plan() -> dict[str, Any]:
    return {
        "project": "Synthetiq Redact hybrid redaction pilot",
        "deliverable": "local-first OCR/layout baseline plus redaction detector bootstrap",
        "gpu_recommendation": {
            "default": "A100 80GB",
            "fastest_short_run": "H100 80GB",
            "large_vlm_checking": "RTX PRO 6000 Blackwell 96GB",
        },
        "do_first_on_runpod": [
            "Unzip handoff package under /workspace/synthetiq-redact",
            "Install dependencies",
            "Run package validation",
            "Run easyocr and paddleocr baseline on all 300 images",
            "Evaluate PII recall and runtime",
            "Use predictions to create detector labels",
            "Train the first YOLO redaction detector",
            "Inspect status and reports before spending more credit",
        ],
        "run_commands": [
            "bash backend/training/scripts/runpod_bootstrap.sh",
            "nohup bash backend/training/scripts/runpod_hybrid_pilot.sh > backend/training/reports/runpod_logs/full_run.log 2>&1 &",
            "python backend/training/scripts/runpod_status.py",
        ],
        "do_not_do": [
            "Do not push dataset images to GitHub",
            "Do not train TrOCR on full-page images as the main model",
            "Do not trust detector labels until a sample overlay review passes",
        ],
    }


def requirements_text() -> str:
    return """pillow>=11.0.0
numpy>=2.1.0
opencv-python-headless>=4.10.0
easyocr>=1.7.2
paddlepaddle-gpu>=3.0.0
paddleocr>=2.7.0
transformers>=4.47.0
accelerate>=1.2.0
datasets>=3.0.0
ultralytics>=8.3.0
scikit-image>=0.24.0
python-dotenv>=1.0.1
"""


def remove_tree(path: Path) -> None:
    def handle_remove_error(func: Any, failed_path: str, _exc_info: Any) -> None:
        os.chmod(failed_path, stat.S_IWRITE)
        func(failed_path)

    if path.exists():
        shutil.rmtree(path, onerror=handle_remove_error)


def copy_package(paths: PilotPaths) -> None:
    remove_tree(paths.package_root)
    paths.package_root.mkdir(parents=True, exist_ok=True)

    copy_pairs = [
        (Path("backend/training/scripts"), paths.package_root / "backend/training/scripts"),
        (Path("backend/training/configs"), paths.package_root / "backend/training/configs"),
        (Path("backend/training/README.md"), paths.package_root / "backend/training/README.md"),
    ]
    for src, dst in copy_pairs:
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), dirs_exist_ok=True)
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    export_dst = paths.package_root / "backend/training/exports/hybrid_redaction_pilot"
    export_dst.mkdir(parents=True, exist_ok=True)
    for src in (
        paths.manifest_path,
        paths.audit_path,
        paths.splits_path,
        paths.runpod_readme_path,
        paths.runpod_plan_path,
        paths.output_dir / "requirements-runpod-hybrid.txt",
    ):
        if src.exists():
            shutil.copy2(src, export_dst / src.name)

    dataset_src = paths.dataset_root
    dataset_dst = paths.package_root / "backend/training/datasets/synthetiq_redact_image_dataset"
    for doc_number in range(1, 31):
        doc_id = f"DOC-{doc_number:03d}"
        shutil.copytree(dataset_src / doc_id, dataset_dst / doc_id, dirs_exist_ok=True)

    (paths.package_root / "requirements-runpod-hybrid.txt").write_text(requirements_text(), encoding="utf-8")

    if paths.package_zip.exists():
        paths.package_zip.unlink()
    with zipfile.ZipFile(paths.package_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for file_path in sorted(paths.package_root.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(paths.package_root))


def build_paths(dataset_root: Path, output_dir: Path) -> PilotPaths:
    return PilotPaths(
        dataset_root=dataset_root,
        output_dir=output_dir,
        manifest_path=output_dir / "hybrid_manifest.jsonl",
        audit_path=output_dir / "dataset_audit.json",
        splits_path=output_dir / "splits.json",
        runpod_readme_path=output_dir / "RUNPOD_HANDOFF.md",
        runpod_plan_path=output_dir / "runpod_training_plan.json",
        package_root=output_dir / "package_root",
        package_zip=output_dir / "synthetiq_redact_runpod_handoff.zip",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and package the Synthetiq Redact hybrid redaction pilot dataset.")
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    output_dir = Path(args.output_dir)
    paths = build_paths(dataset_root, output_dir)

    rows, audit = validate_and_build_manifest(paths.dataset_root, range(1, 31))
    write_json(paths.audit_path, audit)
    write_jsonl(paths.manifest_path, rows)
    write_json(
        paths.splits_path,
        {
            "train_docs": [f"DOC-{i:03d}" for i in sorted(TRAIN_DOCS)],
            "validation_docs": [f"DOC-{i:03d}" for i in sorted(VALIDATION_DOCS)],
            "test_docs": [f"DOC-{i:03d}" for i in sorted(TEST_DOCS)],
            "policy": "split_by_document_to_prevent_same_text_leakage",
        },
    )
    paths.runpod_readme_path.write_text(runpod_readme(), encoding="utf-8")
    write_json(paths.runpod_plan_path, runpod_plan())
    (paths.output_dir / "requirements-runpod-hybrid.txt").write_text(requirements_text(), encoding="utf-8")

    if args.package and not args.validate_only:
        copy_package(paths)

    summary = {
        "status": audit["status"],
        "manifest": str(paths.manifest_path.resolve()),
        "audit": str(paths.audit_path.resolve()),
        "rows": len(rows),
        "splits": audit["split_counts"],
        "package_zip": str(paths.package_zip.resolve()) if args.package and paths.package_zip.exists() else None,
        "problems": audit["problems"][:20],
        "warnings": audit["warnings"][:20],
    }
    print(json.dumps(summary, indent=2))
    return 0 if audit["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
