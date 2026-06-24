# Security Policy

Synthetiq Redact is local-first software for sensitive document workflows. Treat uploads, OCR output, processed files, redaction metadata, audit logs, screenshots, and exports as sensitive.

## Reporting Security Issues

Do not open a public issue for vulnerabilities involving authentication bypass, document access, upload handling, data leakage, secrets, or model/data exposure.

Use GitHub private vulnerability reporting if it is enabled for the repository. If it is not enabled, contact the maintainer privately before publishing details.

## Current Security Baseline

- Authentication is required for document, image, export, review, batch, audit, analytics, and admin endpoints.
- Review and admin actions use role checks.
- Documents are scoped to a single-council pilot boundary through `council_id`.
- Runtime uploads are stored outside the frontend static build.
- Uploads use server-generated filenames.
- Uploads are limited by size and checked by magic bytes.
- Optional malware scanning can be enabled with `SYNTHETIQ_MALWARE_SCAN_COMMAND`.
- Production startup refuses default `JWT_SECRET` and `AUDIT_SECRET`.
- CORS is configurable and defaults to local development origins.
- OpenAPI docs are disabled when `APP_ENV=production`.
- Audit logs use chained hashes and HMAC signatures.

## Production Blockers

Before a real council deployment, complete:

- HTTP-only secure cookie auth with CSRF, or short-lived access tokens with refresh rotation.
- Encryption at rest for uploaded files, OCR text, original redaction values, and exports.
- Key management and rotation guidance.
- Bundled or documented malware scanning deployment.
- Retention purge and secure deletion jobs.
- Full object-level authorization tests.
- Backup and restore tests.
- Dependency scanning and secret scanning in CI.
- Production deployment hardening guide.
- DPO/information governance review of the compliance pack.

## Data Handling Rules

- Never commit real council documents, OCR text, processed files, local databases, generated reports, or screenshots containing personal data.
- Do not send real council documents to external AI, OCR, image-generation, or evaluation APIs.
- Use synthetic or consented fake data for public testing.
- Assume generated redaction previews may still contain personal data until reviewed.

