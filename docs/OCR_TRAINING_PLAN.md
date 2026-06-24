# OCR Training Plan

Synthetiq Redact needs handwriting OCR that is useful for redaction, not only
pretty transcription. The training pipeline therefore keeps coordinates,
confidence, review routing, and answer-key evidence first-class.

## Current Pipeline Summary

The current app renders each uploaded image or PDF page into page-specific
original, display, and OCR-enhanced images. EasyOCR extracts text and word
boxes. The redaction engine detects sensitive spans with deterministic UK PII
rules, spaCy, optional local LLM support, and category-specific profiles. Those
spans are mapped back to OCR word boxes, saved as page-scoped redaction rows,
and burned into preview images and masks.

Low-confidence handwriting is treated as unsafe. The handwriting safety pass
masks likely header/contact fields, labelled values, pattern-matched values,
dependent child names, signatures, and medical/safeguarding lines when OCR is
weak. Optional local Ollama vision verification acts as a second reader and
raises page-level warnings. The React review studio then lets staff inspect
pages, OCR text, warnings, boxes, manual boxes, text-selection redactions, and
undo history before exporting a verified burned raster PDF.

## Goal

Build a local Windows/WSL training and evaluation loop for council-style
handwriting and scans:

- Return text, line/word boxes, confidence, warnings, and redaction evidence.
- Improve line recognition on handwriting without training a giant VLM.
- Keep all real documents local and out of cloud APIs.
- Make low-confidence handwriting force human review during pilots.

First target:

- Handwritten CER under 10-12 percent on the fake council-style test set.
- Critical PII recall above 99 percent before any real council pilot.
- Zero automatic release for handwriting during pilot use.

## Recommended Architecture

Use detector plus recognizer:

1. A detector/layout backend finds page regions, lines, and words.
2. A recognizer reads line crops.
3. The backend maps recognized line/word evidence back to page coordinates.
4. Local vision models remain verifiers, not the sole OCR source.

Start with:

- EasyOCR baseline.
- PaddleOCR baseline where practical.
- Surya layout/OCR where practical.
- `microsoft/trocr-small-handwritten` or `microsoft/trocr-base-handwritten`
  fine-tuned on line crops.

## Windows GPU Setup

Native Windows path:

```powershell
cd C:\Users\INTERPOL\OneDrive\Documents\REDACT\synthetiq-redact
py -3.11 -m venv backend\venv
backend\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
python backend\training\scripts\check_gpu.py
```

If PyTorch reports CPU-only while `nvidia-smi` sees the RTX GPU, install a CUDA
PyTorch wheel that matches the installed driver:

```powershell
pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu121
python backend\training\scripts\check_gpu.py
```

WSL2 Ubuntu fallback:

```bash
wsl --install -d Ubuntu
sudo apt update
sudo apt install -y python3.11-venv git poppler-utils
cd /mnt/c/Users/INTERPOL/OneDrive/Documents/REDACT/synthetiq-redact
python3.11 -m venv backend/venv
source backend/venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
python backend/training/scripts/check_gpu.py
```

Use WSL2 if native Windows OCR/training packages become painful. Do not move
real council documents into cloud notebooks.

## Dataset Strategy

Use only legal, reviewable data:

- IAM handwriting dataset or Hugging Face mirrors where licence review passes.
- CVL handwriting database where licence review passes.
- NIST Special Database 19 for character/word recognition where applicable.
- Public OCR datasets with clear permitted usage.
- Synthetic fake council documents generated locally.
- Future consented fake council handwriting created specifically for this
  product.

Every document or line must have an answer key containing:

- Correct full text.
- Sensitive values.
- Sensitive type.
- Page number.
- Bbox when available.
- Expected redaction action.
- Expected review reason.

The manifest format is JSONL or CSV with:

- `image_path`
- `text`
- `split`
- `source`
- `licence`
- `document_type`
- `page_number`
- `line_bbox`
- `word_bboxes`
- `pii_items`
- `synthetic`

## Synthetic Council Dataset

Generate fake FOI letters, SAR requests, housing repair complaints, parking
appeals, social-care notes, safeguarding-style notes, and mixed forms:

```powershell
python backend\training\scripts\generate_council_handwriting_dataset.py --count 24
```

The generator adds safe fake names, addresses, references, medical/safeguarding
phrases, phone photos/scans style noise, skew, blur, low contrast, and shadows.
It writes page images, answer-key JSON files, and a manifest. Generated images
and answer keys stay out of Git.

## Baseline Comparison

Run a small baseline:

```powershell
python backend\training\scripts\compare_ocr_backends.py `
  --manifest backend\training\datasets\synthetic_council\manifest.jsonl `
  --limit 25 `
  --gpu
```

Optional tools that are not installed are reported as skipped, not fatal.

## Fine-Tuning

After preparing public and synthetic line manifests:

```powershell
python backend\training\scripts\train_trocr_handwriting.py `
  --manifest backend\training\datasets\handwriting_manifest.jsonl `
  --config backend\training\configs\trocr_small_handwriting.json
```

The default config uses fp16, gradient checkpointing, small per-device batches,
gradient accumulation, early stopping, and checkpoint limits. Do not commit
model weights or downloaded corpora.

## Export And Integration

Export metadata and optional local weights:

```powershell
python backend\training\scripts\export_model.py `
  --source backend\training\models\trocr-small-council-handwriting `
  --output models\trocr_local_council `
  --include-weights
```

Runtime integration target:

```text
HANDWRITING_OCR_BACKEND=trocr_local
HANDWRITING_OCR_MODEL_PATH=C:\path\to\models\trocr_local_council
```

Backend integration should add a recognizer path that returns page/line text,
line boxes, word boxes where available, confidence, and review warnings. It
should not replace human review rules until evaluation targets are met.
