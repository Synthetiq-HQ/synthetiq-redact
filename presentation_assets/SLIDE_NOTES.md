# Hillingdon Document Processor - PowerPoint Chart Pack

Generated from the local codebase on 2026-04-29.

## Current Demo System

The current implementation is a fully local pipeline:

1. Upload document image/PDF.
2. Preprocess with OpenCV-style cleaning: deskew, denoise, contrast, sharpen.
3. Run EasyOCR for text plus word bounding boxes.
4. Run the handwriting transcription layer. Today it falls back to `easyocr_baseline`; the optional target is `Qwen2.5-VL` through `MLX-VLM`.
5. Apply category redaction profiles: `general_pii`, `medical_strict`, `financial_strict`, `safeguarding_strict`, `vehicle_parking`, `unknown_strict`.
6. Redact text and image coordinates with opaque black masks.
7. Detect/translate non-English text with local Qwen/Ollama or Helsinki MarianMT fallback.
8. Classify category, recommend department, detect urgency, sentiment and safeguarding risk.
9. Export redacted image, mask preview, raw OCR text, clean transcription, redacted text, JSON metadata, DOCX and audit trail.

## Measured Results From This Build

| Metric | Result | Meaning |
|---|---:|---|
| Text redaction evaluator | 50/50 passed | Field labels, regex, profiles and safe-value preservation are working. |
| Text redaction score | 100% | On the synthetic extracted-text suite. |
| Handwriting benchmark cases | 9 | Includes one real handwritten screenshot and generated category cases. |
| Avg handwriting transcription similarity | 88.8% | EasyOCR works on clean/generated handwriting but fails on the real sample. |
| Required field recall | 84.3% | Pulled down by the real handwritten screenshot. |
| Missed useful redactions | 0 | Redaction rules are now catching expected sensitive values when OCR sees them. |
| Review flag correctness | 100.0% | Low-confidence handwriting is being routed to review. |

## Model Tiers For The Slides

| Tier | What it uses | Best use | Variable API cost | Setup cost | Notes |
|---|---|---|---:|---:|---|
| Current demo | EasyOCR + regex/profile rules + optional Ollama Qwen text model | End-to-end local demo, typed documents, clean forms | £0/doc | £0 extra on existing Mac | Safe but weak on messy handwriting. |
| PP-OCRv5 add-on | PaddleOCR PP-OCRv5 + current redaction | Better OCR for handwriting while keeping word boxes | £0/doc | £0-£900 depending hardware | Official docs highlight improved English handwriting support. |
| Qwen2.5-VL 3B MLX | Local VLM on Apple Silicon through MLX-VLM | Clean full-page handwriting transcription and tags | £0/doc | £0 extra on M4 if performance is acceptable | Best next hackathon upgrade path. |
| Qwen2.5-VL 7B MLX/GPU | Larger local VLM | Better accuracy on messy letters | £0/doc | ~£900+ if using cheap GPU node | More accurate but slower/heavier. |
| Gemma 3 4B/12B | Google open multimodal model | Alternative local VLM with long context | £0/doc | depends on device | Good backup option; benchmark before choosing. |
| Batch workstation | Dedicated GPU workstation | Council-scale batching | £0/doc | ~£3.5k+ | Useful if many departments process documents concurrently. |

## Slide Talking Points

- The system is designed so **paid API cost is zero**. Cost moves to local hardware, support and electricity.
- The current code already proves the full product flow: upload, OCR, redaction, translation, routing, review, export and audit.
- Text redaction is strong in controlled extracted text: `50/50` cases passed.
- Handwriting is the known risk: EasyOCR alone failed the real handwritten screenshot, so the app safely marks it for review.
- The right technical upgrade is not replacing redaction. It is adding a stronger local transcription/tagging layer before redaction: PP-OCRv5 and/or Qwen2.5-VL through MLX-VLM.
- The safest product story: **coordinate OCR for black image masks + VLM for clean transcription and semantic tags + human review when confidence is low**.

## Chart Files

- `01_current_pipeline_flow.svg`
- `02_measured_quality_metrics.svg`
- `03_speed_cost_model_tiers.svg`
- `04_staff_time_savings.svg`
- `05_handwriting_gap.svg`
- `06_local_cost_stack.svg`
- `00_pipeline_flowchart.mmd`

## Sources For Model Claims

- PaddleOCR PP-OCRv5 documentation: supports major text types and reports upgraded complex English handwriting capability, with PP-OCRv5 improving over PP-OCRv4.
- Qwen2.5-VL 3B model card: vision-language model for text, chart, icon, layout analysis, structured outputs, and available 3B/7B/72B sizes.
- MLX-VLM GitHub: local VLM inference/fine-tuning on Apple Silicon using MLX.
- Google Gemma 3 model card: open multimodal models with text+image input, 128K context for 4B/12B/27B, and local deployment suitability.

## Important Caveat

The speed/cost tier chart uses measured current-system results plus planning estimates for not-yet-benchmarked model tiers. Before a council procurement claim, run the same `evaluate_handwriting_product.py` benchmark on the actual target hardware with PP-OCRv5 and Qwen2.5-VL enabled.
