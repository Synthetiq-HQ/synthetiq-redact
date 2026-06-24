# OCR Training Workspace

This folder contains local-only handwriting OCR training and evaluation tooling.

Generated datasets, downloaded public corpora, checkpoints, and exported model
weights are intentionally ignored by Git. Commit only code, configs, docs, and
small reports.

Primary manifest format is JSONL. Each row should contain:

```json
{
  "image_path": "absolute/or/repo-relative/path.png",
  "text": "ground truth line or page text",
  "split": "train|validation|test",
  "source": "synthetic_council|iam|nist|cvl|...",
  "licence": "licence name or review_required",
  "document_type": "foi|sar|housing_repair|parking_appeal|social_care|safeguarding|form",
  "page_number": 1,
  "line_bbox": [10, 20, 200, 40],
  "word_bboxes": [],
  "pii_items": [],
  "synthetic": true
}
```
