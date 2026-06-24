# Retention And Deletion Policy Template

This template must be adapted by each council.

## Data Stores

- Original uploads.
- Redacted images and exports.
- OCR text and structured OCR data.
- Redaction records and original detected values.
- Audit logs.
- User accounts and role assignments.

## Default Pilot Position

- Keep uploaded and processed documents only for the approved pilot period.
- Keep audit logs for the council-approved evidence period.
- Do not keep real council documents in development environments.
- Do not publish real documents, OCR text, screenshots, or local databases.

## Deletion Requirements

- Deletion must remove original uploads, processed outputs, exports, OCR text, and redaction values.
- Audit logs may need separate retention rules for accountability.
- Retention purge jobs should record what was deleted without storing sensitive content.

## Implementation Status

- Retention fields exist in the V2 data model.
- Scheduled purge and secure deletion jobs are still required before production.

