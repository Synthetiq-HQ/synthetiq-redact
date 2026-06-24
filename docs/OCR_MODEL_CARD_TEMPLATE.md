# OCR Model Card Template

## Model

- Name:
- Version:
- Base model:
- Export path:
- Training date:
- Training owner:

## Intended Use

Local handwriting OCR support for Synthetiq Redact review workflows. The model
assists transcription and redaction mapping. It must not make final disclosure
decisions.

## Not Intended For

- Automatic release of handwritten council documents.
- Cloud processing of real council documents.
- Reading documents outside the evaluated language/domain without review.
- Bypassing human redaction review for safeguarding, legal, medical, or
  low-confidence material.

## Training Data

| Dataset | Source | Licence | Rows | Split | Notes |
| --- | --- | --- | ---: | --- | --- |
| Synthetic council | Local generator | Synthetic fake data | | train/validation/test | No real personal data |

## Evaluation Data

| Dataset | Source | Licence | Rows | Split | Synthetic |
| --- | --- | --- | ---: | --- | --- |

## Metrics

| Metric | Value | Target | Notes |
| --- | ---: | ---: | --- |
| CER | | < 0.12 | Fake council handwritten set |
| WER | | | |
| Line recognition accuracy | | | |
| Field-level recall | | | |
| PII recall | | > 0.99 for critical PII before pilot | |
| Critical PII false-negative count | | 0 preferred | Investigate every miss |
| Redaction-box mapping success | | | IoU threshold: |
| Low-confidence review trigger accuracy | | | |

## Safety Policy

- Handwriting auto-release enabled: No.
- Low-confidence handwriting forces review: Yes.
- Vision verifier role: local second-reader only.
- Human review required for safeguarding/social-care/legal/high-risk records:
  Yes.

## Known Limitations

- Messy handwriting:
- Low contrast/blur:
- Skew/phone photos:
- Box mapping:
- Unsupported languages:

## Deployment

Environment variables:

```text
HANDWRITING_OCR_BACKEND=trocr_local
HANDWRITING_OCR_MODEL_PATH=
```

Model weights must be delivered through local artifacts, Git LFS, or release
assets if absolutely needed. Do not commit large weights directly to Git.
