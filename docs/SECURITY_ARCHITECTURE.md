# Security Architecture

## Security Goal

Synthetiq Redact should be deployable as a local-first council-controlled redaction assistant. Real council documents must stay inside council-controlled infrastructure unless the council explicitly approves otherwise.

## Current Controls

- Authentication is required on document, image, export, review, batch, audit, analytics, and admin endpoints.
- Role checks protect admin and review actions.
- Documents are scoped by `council_id`.
- Runtime uploads are stored outside the frontend static build.
- Upload filenames are generated server-side.
- Upload content is checked by file magic bytes as well as extension.
- Upload size is limited by `MAX_UPLOAD_BYTES`.
- Optional malware scanning can be enabled with `SYNTHETIQ_MALWARE_SCAN_COMMAND`.
- Production refuses startup if default `JWT_SECRET` or `AUDIT_SECRET` is used.
- CORS defaults to local development origins and can be set with `CORS_ORIGINS`.
- Public OpenAPI docs are disabled when `APP_ENV=production`.
- Audit logs use chained hashes and HMAC signatures.

## Production Gaps

- Replace session-storage bearer tokens with HTTP-only secure cookies plus CSRF, or a short-lived access-token and refresh-token flow.
- Encrypt uploaded files, OCR text, original redaction values, and exports at rest.
- Add key rotation and recovery procedures.
- Add scheduled retention purge and secure deletion.
- Package a supported malware scanner such as ClamAV for deployments that require it.
- Add backup and restore tests.
- Add object-level authorization tests.
- Add dependency scanning and secret scanning to CI.
- Add operational monitoring that does not log OCR text or sensitive values.

## Required Production Environment Variables

- `APP_ENV=production`
- `JWT_SECRET` with a strong non-default value.
- `AUDIT_SECRET` with a strong non-default value.
- `CORS_ORIGINS` set to the real frontend origin.
- `MAX_UPLOAD_BYTES` set to the council-approved limit.
- `SYNTHETIQ_MALWARE_SCAN_COMMAND` if malware scanning is enabled.

## Data Handling Rules

- Do not commit uploads, processed files, local databases, OCR output, or evaluation documents containing real people.
- Treat OCR text and redaction previews as personal data.
- Do not send real council documents to external AI, OCR, image-generation, or evaluation APIs.
- Use synthetic or consented fake documents for public demos and tests.

