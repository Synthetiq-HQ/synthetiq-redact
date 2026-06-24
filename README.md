# Synthetiq Redact

Local-first document redaction review for UK council-style workflows.

Synthetiq Redact is an open-source redaction assistant for FOI, SAR, EIR, and council casework documents. It extracts text, detects sensitive information, applies opaque image redactions, routes uncertain work to human review, exports redacted records, and keeps an audit trail.

It assists redaction review. It does not make final legal disclosure decisions, and it should not be described as fully automatic compliance software.

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
- Require staff sign-in for document, image, export, review, batch, audit, analytics, and admin routes.
- Support a single-council pilot boundary with role-based review/admin actions.

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
docs/                 Roadmap, security, compliance, and data strategy docs
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

`backend/main.py` now loads the secured V2 app. On first launch, create the first admin account from the frontend "First setup" tab.

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
cd frontend && npm audit --audit-level=high
```

Latest local validation before release:

- Text redaction evaluator: `50/50 passed`
- Frontend production build: passed
- Frontend npm audit: no vulnerabilities
- Low-confidence handwriting safety fallback: tested on a handwritten PII page

## Production Readiness Docs

- [Production roadmap](docs/ROADMAP.md)
- [Security architecture](docs/SECURITY_ARCHITECTURE.md)
- [Responsible use](docs/RESPONSIBLE_USE.md)
- [Public release checklist](docs/OPEN_SOURCE_RELEASE_CHECKLIST.md)
- [Data flow](docs/compliance/DATA_FLOW.md)
- [Threat model](docs/compliance/THREAT_MODEL.md)
- [DPIA template](docs/compliance/DPIA_TEMPLATE.md)
- [Human review policy](docs/compliance/HUMAN_REVIEW_POLICY.md)
- [Retention and deletion policy](docs/compliance/RETENTION_AND_DELETION.md)
- [Model card](docs/compliance/MODEL_CARD.md)
- [Handwriting data strategy](docs/HANDWRITING_DATA_STRATEGY.md)
- [Licence matrix](docs/compliance/LICENSE_MATRIX.md)
- [Supplier/subprocessor statement](docs/compliance/SUPPLIER_SUBPROCESSOR_STATEMENT.md)

## Demo Data

The repository only includes synthetic demo documents. Runtime uploads, processed files, local databases, generated reports, and user test images are excluded by `.gitignore`.

## Current Limitations

- EasyOCR is weak on messy handwriting.
- The visual handwriting fallback protects likely sensitive regions but can over-redact.
- PDF uploads are currently rendered as page 1 for OCR/redaction and are forced into human review; full multi-page PDF redaction is still required before production.
- Human review is required for low-confidence handwriting, safeguarding, unknown, and legal/FOI-style documents.
- The current auth baseline uses browser session storage for bearer tokens; production should move to secure HTTP-only cookies with CSRF or short-lived access tokens plus refresh rotation.
- Encryption at rest, bundled malware scanning, retention purge jobs, full Alembic migrations, backup/restore runbooks, and council deployment packaging are still required before production.
- The current benchmark is too small and synthetic-heavy for council trust.

## SDG Alignment

Synthetiq Redact supports UN SDG 16 by helping public-sector teams handle sensitive documents more consistently, transparently, and safely.
