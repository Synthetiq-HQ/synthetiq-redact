# DPIA Template

This is a template for council review. It is not legal advice.

## 1. Processing Overview

- Project name: Synthetiq Redact
- Controller: council to complete
- Processor or supplier: council to complete
- Purpose: assist staff with identifying and reviewing sensitive information before FOI, SAR, EIR, or casework disclosure.
- Data location: council-controlled local server or private cloud.
- External AI for real documents: no by default.

## 2. Data Categories

- Names, addresses, dates of birth, emails, phone numbers.
- NHS numbers, National Insurance numbers, bank/sort code details.
- Vehicle registrations, PCNs, council references, case IDs.
- Signatures and handwritten notes.
- Health, housing, legal, safeguarding, and social-care context.
- Children and vulnerable-person references.

## 3. Necessity And Proportionality

- Why automated assistance is needed:
- Why human review remains required:
- Why local-first processing is used:
- Alternatives considered:

## 4. Risk Assessment

| Risk | Likelihood | Impact | Mitigation | Owner |
| --- | --- | --- | --- | --- |
| Missed personal data in released document | | | Human review, benchmark thresholds, low-confidence review routing | |
| Over-redaction | | | Reviewer approval and modification tools | |
| Unauthorized document access | | | Auth, role checks, council boundary, object-level tests | |
| Malware in uploads | | | Upload validation and malware scanner hook | |
| Data retained too long | | | Retention policy and purge job | |
| External data transfer | | | No external AI for real documents | |

## 5. Human Review

- Which document classes require review:
- Which roles can approve release:
- How disagreements are escalated:
- How corrections become benchmark cases:

## 6. Retention

- Upload retention period:
- Export retention period:
- Audit-log retention period:
- Deletion approval process:

## 7. Transparency

- Internal user guidance:
- Data subject/public-facing explanation if required:
- Limitations statement:

## 8. Approval

- DPO reviewer:
- Information governance reviewer:
- IT/security reviewer:
- Pilot approval date:
- Review date:

