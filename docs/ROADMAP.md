# Synthetiq Redact Production Readiness Roadmap

Synthetiq Redact is being shaped as a local-first redaction assistant for UK council information governance teams. It assists staff with FOI, SAR, EIR, housing, parking, complaints, safeguarding, legal, and social-care review. It must not be described as a fully automatic legal disclosure decision maker.

## Current Baseline

Implemented in the pilot baseline:

- V2 backend is the default app entrypoint through `backend/main.py`.
- V2 frontend is the default React app entrypoint.
- Staff sign-in and first-admin setup.
- JWT authentication on document, image, export, review, batch, audit, analytics, and admin routes.
- Role checks for review and admin actions.
- Single-council data boundary with legacy demo-data backfill.
- Server-generated upload filenames, magic-byte file validation, upload size limit, and optional malware scanner hook.
- Protected image and export downloads through authenticated API calls.
- Review queue, batch processing, redaction approval/rejection/modify endpoints, and audit trail endpoint.
- Tamper-evident audit-chain implementation.
- Lightweight SQLite migration bridge for existing demo databases.
- Compliance and security documentation scaffolding.

Known incomplete items:

- Secure cookie and CSRF flow is still preferred over bearer tokens for production.
- Encryption at rest is documented but not fully implemented.
- Malware scanning is a hook, not a bundled scanner.
- Retention purge jobs are documented but not yet scheduled.
- Alembic migrations should replace the lightweight SQLite bridge before pilot.
- Handwriting is not reliable enough for auto-release and remains mandatory review.
- Evaluation data is still too small and synthetic-heavy for council trust.

## Phase 1: Stabilise Current App

Goal: one coherent V2 application.

Tasks:

- Keep `backend/main.py` as the V2 compatibility entrypoint.
- Keep `frontend/src/main.jsx` loading `App_v2`.
- Replace lightweight SQLite migrations with Alembic before a council pilot.
- Add backend smoke tests for health, auth, upload, progress, document fetch, image fetch, export, and audit.
- Add browser tests for upload, review queue, approve/reject, final release, and export.

Exit criteria:

- Fresh clone starts from README.
- First admin setup works.
- No document route works without auth.
- Upload to export works on a sample synthetic FOI/SAR pack.

## Phase 2: Make Redaction Reliable

Goal: measurable confidence that sensitive data is caught and low-confidence cases fail into review.

Tasks:

- Freeze a redaction taxonomy covering names, addresses, emails, phones, DOBs, NHS numbers, NI numbers, bank details, vehicle registrations, PCNs, council references, signatures, children data, health data, safeguarding data, and free-text sensitive context.
- Add deterministic validators for NHS, NI, postcode, phone, email, bank/sort code, PCN, vehicle registration, and council reference formats.
- Store every detection with type, confidence, method, text span, bounding box, and review status.
- Build a golden benchmark with typed documents, scans, photos, PDFs, DOCX, tables, forms, emails, handwriting, multilingual examples, and noisy images.
- Track per-type recall and precision.
- Replay human corrections as regression tests.

Exit criteria:

- Critical PII recall is at least 99 percent on the pilot benchmark.
- Handwriting and low-OCR-confidence documents are forced into review.
- No known critical PII misses remain in the pilot benchmark.

## Phase 3: Council Workflow

Goal: make the product usable by information governance staff.

Tasks:

- Improve side-by-side review with add, move, resize, delete, approve, reject, modify, and reason capture.
- Add keyboard shortcuts for repetitive review work.
- Add release packs: redacted file, audit trail, redaction summary, reviewer notes, and confidence summary.
- Add category profiles for FOI/SAR, EIR, housing, parking, complaints, safeguarding, legal, adult social care, and children services.
- Add admin-configurable retention periods.

Exit criteria:

- A reviewer can process a realistic FOI/SAR sample pack without developer help.
- Every release has an audit trail and redaction summary.
- Batch processing survives individual document failures.

## Phase 4: Security And Privacy Hardening

Goal: safe enough for a controlled council pilot.

Tasks:

- Move from bearer token session storage to secure HTTP-only cookies with CSRF protection, or use short-lived access tokens plus refresh rotation.
- Add object-level authorization tests.
- Add encryption at rest for uploads, OCR text, original redaction values, and exports.
- Add retention purge and secure deletion jobs.
- Add malware scanner packaging guidance.
- Add strict production config validation.
- Add backup and restore runbooks.
- Protect OpenAPI docs in production.

Exit criteria:

- No default secrets in production.
- No cross-council access.
- Security tests pass.
- Production startup refuses unsafe config.

## Phase 5: Compliance Evidence Pack

Goal: give councils the documents needed for DPO and information governance review.

Tasks:

- Complete DPIA template.
- Complete data-flow diagram.
- Complete threat model.
- Complete human review policy.
- Complete retention and deletion policy.
- Complete model card and evaluation report.
- Complete dependency and model licence matrix.
- Complete supplier/subprocessor statement.

Exit criteria:

- Pack reviewed by a DPO or information governance professional.
- Public README does not overclaim legal compliance.
- Tool clearly states that council staff remain responsible for final disclosure decisions.

## Phase 6: Pilot Deployment

Goal: controlled pilot with one council.

Tasks:

- Package Docker Compose deployment.
- Add offline model cache/download instructions.
- Add production config checker.
- Add sample synthetic FOI/SAR packs.
- Run training and a tabletop incident exercise.
- Track accuracy, review time, false positives, false negatives, corrections, export success, and failed jobs.

Exit criteria:

- Council can install without developer SSH intervention.
- No real data leaves council-controlled infrastructure.
- Pilot report is produced.

## Phase 7: Open Source Release

Goal: credible public project for councils and contributors.

Tasks:

- Finalise licence after dependency and model licence review.
- Add contributor guide, security policy, responsible-use policy, changelog, roadmap, and issue templates.
- Add synthetic demo data only.
- Add CI for backend, frontend, audits, and benchmark regression.
- Publish pilot findings without personal data.

Exit criteria:

- Public repo contains no real uploads, OCR outputs, processed files, or databases.
- Fresh clone demo works.
- CI passes.
- Licence matrix is complete.

