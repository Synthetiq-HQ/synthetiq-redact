# Synthetiq Redact Demo Release

## Demo Scope

This release packages the local council-document redaction prototype for GitHub.

Included:

- FastAPI backend.
- React staff web app.
- OCR, redaction, classification, translation, audit, and export pipeline.
- Synthetic demo documents.
- Redaction profile evaluator.
- Handwriting evaluation harness.
- Presentation assets for the hackathon demo.

Excluded:

- Runtime uploads.
- Processed redacted images.
- Local SQLite databases.
- Virtual environments.
- Node modules and build folders.
- Any user test images.

## Validation

- Backend Python compile passed.
- Text redaction evaluator passed 50/50.
- Frontend production build passed.
- Handwriting fallback tested on low-confidence handwritten PII.

## Known Demo Limitations

- Messy handwriting is still the hardest case.
- EasyOCR remains the default OCR engine.
- MLX-VLM/Qwen2.5-VL is optional and must be configured locally.
- Low-confidence handwriting should always be reviewed by staff.

