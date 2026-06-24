# Model Card

## Product Role

Synthetiq Redact uses local OCR, redaction rules, entity recognition, and optional local models to propose redactions. It is a decision-support tool for council staff.

## Intended Use

- FOI/SAR/EIR redaction assistance.
- Council casework document review.
- Local-first processing of sensitive documents.
- Human-in-the-loop release workflow.

## Out Of Scope

- Fully automatic legal disclosure decisions.
- Guaranteed GDPR, FOI, SAR, or EIR compliance.
- Anonymisation claims without re-identification assessment.
- External AI processing of real council documents by default.

## Current Components

- EasyOCR and optional PaddleOCR for text extraction.
- spaCy and deterministic redaction rules for entity detection.
- Optional local Ollama/Qwen support for classification and PII suggestions.
- Optional local MLX-VLM handwriting transcription on Apple Silicon.
- Handwriting safety fallback that over-redacts likely value regions when confidence is low.

## Known Limitations

- Messy handwriting remains unreliable.
- OCR errors can cause missed detections.
- Free-text sensitivity is harder than structured fields.
- Synthetic test data is not enough to prove council reliability.
- High recall can increase over-redaction.

## Evaluation Requirements

- Per-type recall and precision.
- False-negative review focused on critical PII.
- Handwritten, scanned, photographed, PDF, DOCX, table, form, email, noisy, multilingual, and low-contrast cases.
- Human-correction replay tests.
- Separate train/dev/test writers for handwriting.

## Pilot Thresholds

- Critical PII recall target: at least 99 percent on the approved pilot benchmark.
- Handwriting: mandatory human review.
- Low OCR confidence: mandatory human review.
- Safeguarding, children, health, legal, and social-care content: mandatory human review.

