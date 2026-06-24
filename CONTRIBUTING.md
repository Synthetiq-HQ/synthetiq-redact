# Contributing

Synthetiq Redact handles sensitive document workflows. Contributions should protect privacy, avoid overclaiming compliance, and keep human review central.

## Rules

- Do not commit real council documents, real OCR text, screenshots containing real personal data, local databases, processed files, or uploads.
- Use synthetic or consented fake data only.
- Do not add external AI processing for real documents without an explicit opt-in setting and documentation.
- Keep local-first processing as the default.
- Add tests for redaction changes, especially false-negative cases.
- Update the model card or known limitations when changing OCR, redaction, classification, or handwriting behaviour.

## Development Checks

```bash
backend/venv/bin/python -m py_compile backend/*.py
backend/venv/bin/python backend/evaluate_redaction_text.py
cd frontend && npm run build
cd frontend && npm audit --audit-level=high
```

## Pull Request Checklist

- No real personal data is included.
- Backend and frontend checks pass.
- Security-sensitive changes include tests or manual verification notes.
- Documentation is updated for user-facing behaviour changes.
- The change does not imply automatic legal compliance or automatic release.
