# Security Notes

Synthetiq Redact is a local-first demo prototype.

## Data Handling

- Do not commit real uploads, processed documents, local databases, or generated OCR reports.
- Use only synthetic demo data in the repository.
- Treat OCR output as sensitive because it may contain personal data.
- Treat redaction previews and masks as sensitive until reviewed.

## Production Requirements

Before production use, add:

- Staff authentication and role-based access control.
- Encryption for stored files and database records.
- Configurable retention and deletion policies.
- Formal audit log review.
- Security testing for upload handling.
- Human review workflow for low-confidence handwriting and safeguarding cases.

## Reporting Issues

For demo use, report issues through the GitHub repository issue tracker.

