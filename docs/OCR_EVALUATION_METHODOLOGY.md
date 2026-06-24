# OCR Evaluation Methodology

OCR accuracy is defined with explicit metrics. Do not claim a vague percentage
such as "90 percent accurate" without saying which metric, dataset, split, and
threshold produced it.

## Evaluation Inputs

Use JSONL prediction files from:

```powershell
python backend\training\scripts\compare_ocr_backends.py --manifest <manifest>
```

Each prediction row includes:

- Backend name.
- Image path and page number.
- Ground-truth text.
- OCR prediction.
- Confidence.
- Word boxes where available.
- PII answer-key items.
- CER/WER for the row.

## Metrics

- CER: character error rate, lower is better.
- WER: word error rate, lower is better.
- Line recognition accuracy: exact normalized line match rate.
- Field-level recall: expected answer-key field values found in OCR output.
- PII recall: expected PII values found in OCR output.
- Critical PII false-negative count: critical answer-key values missed.
- Redaction-box mapping success: expected PII boxes matched to OCR boxes.
- Low-confidence review trigger accuracy: risky low-confidence rows routed to
  human review.

Critical PII types:

- Person names.
- Child names.
- Age and child age.
- Addresses.
- Phone numbers.
- Emails.
- DOBs.
- NHS numbers.
- NI numbers.
- Case references.
- Council references.
- Medical details.
- Safeguarding context.
- Signatures.

## Command

```powershell
python backend\training\scripts\eval_handwriting_ocr.py `
  --predictions backend\training\reports\baseline_ocr_predictions.jsonl `
  --output-report backend\training\reports\handwriting_ocr_eval_report.json
```

## Targets

First fake council-style test goal:

- Handwritten CER below 0.10 to 0.12.
- Critical PII recall above 0.99 before real council pilots.
- Critical PII false-negative count must be investigated row by row.
- Handwriting is never auto-released during pilots.
- Low-confidence handwriting forces review.

## Reporting Rules

Every report should include:

- Dataset name, source, licence, split, and synthetic/real status.
- Backend name and version where available.
- GPU/CPU environment.
- Number of rows/documents.
- CER/WER summary.
- Critical PII misses with values redacted or fake-only.
- Redaction mapping misses and IoU threshold.
- Review-trigger misses.
- Known limitations and next actions.

Do not evaluate on real council documents unless a council-approved data
protection process exists and the files remain local.
