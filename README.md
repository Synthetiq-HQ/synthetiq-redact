# Synthetiq Redact

Secure local-AI document redaction for council-style workflows.

Synthetiq Redact is a hackathon prototype for processing uploaded document photos locally. It extracts text, detects sensitive information, applies opaque image redactions, routes documents by category, flags urgency and safeguarding risks, and exports audit-ready records.

## What It Does

- Upload document photos from a web app.
- Clean images before OCR using local preprocessing.
- Extract text and word boxes with open-source OCR.
- Redact sensitive values, not labels.
- Apply opaque black image masks, not blur.
- Use category-specific redaction profiles.
- Translate non-English text locally where configured.
- Classify documents into council departments.
- Detect urgency, sentiment, and safeguarding risk.
- Export redacted images, text, JSON metadata, and DOCX files.
- Keep full audit trails in SQLite.

## Local-Only AI

This project is designed to avoid paid OCR or LLM APIs.

Current local components:

- **EasyOCR** for OCR and word-level bounding boxes.
- **spaCy** for local entity recognition.
- **Helsinki-NLP MarianMT** for local translation fallback.
- **Ollama/Qwen** optional local LLM support for classification, translation, and PII detection.
- **MLX-VLM/Qwen2.5-VL** optional local handwriting transcription path for Apple Silicon.

No Google Cloud Vision, AWS Textract, Azure OCR, OpenAI Vision, or paid cloud OCR is required.

## Redaction Safety Model

The core rule is:

```text
Keep field labels visible.
Redact sensitive values.
If handwriting confidence is low, fail safely and require human review.
```

Examples:

```text
Phone: [REDACTED-phone]
Email: [REDACTED-email]
Address: [REDACTED-address]
NHS Number: [REDACTED-nhs_number]
```

For difficult handwriting, Synthetiq Redact includes a visual fallback that masks likely value regions even when OCR cannot confidently read the value.

## Project Structure

```text
backend/              FastAPI backend, OCR, redaction, routing, audit
frontend/             React + Vite staff web app
mobile/               Experimental Flutter mobile client
presentation_assets/  Demo charts and slide notes
```

## Quick Start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

Backend health:

```text
http://127.0.0.1:8000/health
```

## Optional Local LLM Setup

The backend can use a local Ollama model named:

```text
qwen2.5-council
```

If Ollama is not running, the app falls back to deterministic local rules.

For Apple Silicon handwriting transcription, configure MLX-VLM:

```bash
export HANDWRITING_TRANSCRIPTION_BACKEND=qwen_vlm_mlx
export HANDWRITING_VLM_MODEL=mlx-community/Qwen2.5-VL-3B-Instruct-4bit
```

The app still works without MLX-VLM, using EasyOCR baseline plus safety review.

## Validation Commands

From the repository root:

```bash
backend/venv/bin/python -m py_compile backend/*.py
backend/venv/bin/python backend/evaluate_redaction_text.py
backend/venv/bin/python backend/evaluate_handwriting_product.py --include-generated
cd frontend && npm run build
```

Latest local validation before release:

- Text redaction evaluator: `50/50 passed`
- Frontend production build: passed
- Low-confidence handwriting safety fallback: tested on a handwritten PII page

## Demo Data

The repository only includes synthetic demo documents. Runtime uploads, processed files, local databases, generated reports, and user test images are excluded by `.gitignore`.

## Current Limitations

- EasyOCR is weak on messy handwriting.
- The visual handwriting fallback protects likely sensitive regions but can over-redact.
- Human review is required for low-confidence handwriting, safeguarding, unknown, and legal/FOI-style documents.
- Production deployment would need authentication, role-based access control, retention policies, and council system integration.

## SDG Alignment

Synthetiq Redact supports UN SDG 16 by helping public-sector teams handle sensitive documents more consistently, transparently, and safely.

