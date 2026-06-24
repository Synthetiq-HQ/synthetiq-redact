# Threat Model

## Assets

- Original documents.
- OCR text and extracted values.
- Redacted exports.
- Audit trail.
- User identities and roles.
- Model and benchmark data.
- Secrets and signing keys.

## Main Threats

| Threat | Risk | Current Control | Required Next Control |
| --- | --- | --- | --- |
| Unauthenticated document access | Personal data leakage | Auth required on document routes | Automated auth bypass tests |
| Cross-council access | Tenant data leakage | `council_id` scoping | Object-level authorization tests |
| Malicious upload | Malware or parser exploit | Type/size validation and scanner hook | Packaged scanner and quarantine flow |
| Path traversal | File disclosure | Server-generated filenames and safe file response roots | Dedicated tests |
| Default secrets | Token or audit compromise | Production startup refuses defaults | Secret rotation guide |
| Missed redaction | Unlawful disclosure risk | Human review routing and benchmark tests | Larger benchmark and correction replay |
| Over-redaction | Poor FOI/SAR quality | Review tools | Reviewer guidance and reason capture |
| Audit tampering | Loss of accountability | Chained HMAC audit logs | External log export or append-only storage |
| Excess retention | Data minimisation risk | Retention fields | Scheduled purge and evidence logs |
| External AI leakage | Unapproved data transfer | Local-first policy | Technical egress controls and admin warnings |

## Pilot Assumption

The first pilot is single-council, self-hosted, and limited to fake or low-risk documents until the council completes its DPIA and security review.

