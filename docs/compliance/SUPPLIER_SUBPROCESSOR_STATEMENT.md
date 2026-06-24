# Supplier And Subprocessor Statement

Synthetiq Redact is intended to run locally or in council-controlled private infrastructure.

## Default Position

- No external AI provider is required for real document processing.
- No external OCR provider is required for real document processing.
- No real council documents should be sent to OpenAI, Google, AWS, Azure, or other external AI/OCR services by default.
- Synthetic test generation may use external services only when no real personal data is included.

## Council Responsibilities

Each council must decide:

- Hosting environment.
- Controller/processor role allocation.
- Lawful basis and processing purpose.
- Retention periods.
- Whether any third-party infrastructure or support supplier is involved.
- Whether outbound network access is technically blocked in production.

## Project Responsibilities

The open-source project should provide:

- Local-first defaults.
- Clear documentation of optional external integrations.
- Licence and dependency matrix.
- Security policy and vulnerability reporting path.
- Responsible-use policy.

