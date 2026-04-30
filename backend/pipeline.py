import json
import logging
import os
import asyncio
import shutil
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from config import CONFIDENCE_THRESHOLD, PROCESSED_DIR, CATEGORIES
from database_v2 import SessionLocal
from models_v2 import Document, OCRResult, Redaction
from audit_v2 import log_action
from preprocessing import preprocess_pipeline
from ocr_engine import OCREngine
from redaction import RedactionEngine
from translation import TranslationEngine
from classification import ClassificationEngine
from sentiment_urgency import SentimentUrgencyEngine
from llm_engine import LLMEngine
from handwriting_transcription import HandwritingTranscriptionEngine
from document_exports import (
    write_metadata_json,
    write_redacted_docx,
    write_text_artifacts,
    write_transcription_json,
)
from redaction_profiles import get_profiles_for_category, get_allowed_types, requires_review


def _keyword_estimate(text: str) -> str:
    """Quick keyword scan to estimate document category before LLM classification."""
    text_lower = text.lower()
    best_category = "unknown"
    best_count = 0
    for category, keywords in CATEGORIES.items():
        count = sum(1 for kw in keywords if kw.lower() in text_lower)
        if count > best_count:
            best_count = count
            best_category = category
    return best_category


class DocumentPipeline:
    def __init__(
        self,
        ocr_engine: OCREngine,
        redaction_engine: RedactionEngine,
        translation_engine: TranslationEngine,
        classification_engine: ClassificationEngine,
        sentiment_engine: SentimentUrgencyEngine,
        llm_engine: LLMEngine = None,
        handwriting_engine: HandwritingTranscriptionEngine = None,
    ):
        self.ocr = ocr_engine
        self.redaction = redaction_engine
        self.translation = translation_engine
        self.classification = classification_engine
        self.sentiment = sentiment_engine
        self.llm = llm_engine
        self.handwriting = handwriting_engine or HandwritingTranscriptionEngine()

    async def _set_status(self, db: Session, doc: Document, status: str, detail: str = "") -> None:
        doc.status = status
        db.commit()
        log_action(db, doc.id, f"status_change", details={"status": status, "detail": detail})

    async def process(self, doc_id: int, db_session: Optional[Session] = None, translate_enabled: bool = True) -> None:
        """
        Main async processing pipeline.
        Creates its own DB session if none provided.
        """
        db = db_session or SessionLocal()
        own_session = db_session is None
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return

            # 1. Preprocessing
            await self._set_status(db, doc, "preprocessing", "Deskew, denoise, enhance, sharpen")
            await asyncio.sleep(0.1)
            preprocessed_path = preprocess_pipeline(doc.original_path)

            # 2. OCR
            await self._set_status(db, doc, "ocr", "Extracting text")
            await asyncio.sleep(0.1)
            ocr_result = self.ocr.extract_text(preprocessed_path)
            transcription = self.handwriting.transcribe(preprocessed_path, ocr_result)
            transcription_data = transcription.to_dict()

            # Store OCR result
            ocr_record = OCRResult(
                document_id=doc.id,
                extracted_text=ocr_result["full_text"],
                clean_text=transcription.full_text,
                transcription_data=transcription_data,
                ocr_confidence=ocr_result["average_confidence"],
                words=ocr_result["words"],
            )
            db.add(ocr_record)
            db.commit()

            # 3. Redaction
            await self._set_status(db, doc, "redaction", "Detecting sensitive data")
            await asyncio.sleep(0.1)
            text = ocr_result["full_text"]
            words = ocr_result["words"]
            clean_text = transcription.full_text or text

            # Resolve effective category and redaction profiles
            transcription_category = transcription.document_type_guess
            if transcription_category and transcription_category not in CATEGORIES:
                transcription_category = "unknown"
            effective_category = doc.selected_category or transcription_category or _keyword_estimate(clean_text or text)
            profiles = get_profiles_for_category(effective_category)
            allowed_types = get_allowed_types(profiles)
            doc.redaction_profile = ",".join(profiles)
            doc.handwriting_backend = transcription.backend
            doc.handwriting_confidence = transcription.confidence
            doc.handwriting_review_reason = transcription.needs_review_reason or None

            # Create per-doc output folder
            out_folder = os.path.join(PROCESSED_DIR, effective_category, f"doc_{doc.id}")
            os.makedirs(out_folder, exist_ok=True)
            doc.output_folder_path = out_folder

            # Copy original image into folder for audit trail
            orig_ext = os.path.splitext(doc.original_path)[1]
            orig_copy = os.path.join(out_folder, f"original{orig_ext}")
            if not os.path.exists(orig_copy):
                shutil.copy2(doc.original_path, orig_copy)

            sensitive_spans = self.redaction.detect_sensitive_text(
                text, llm_engine=self.llm, allowed_types=allowed_types
            )
            sensitive_spans.extend(
                _spans_from_transcription_fields(text, transcription.fields, allowed_types)
            )
            redaction_meta = self.redaction.map_to_bboxes(sensitive_spans, words)

            clean_spans = self.redaction.detect_sensitive_text(
                clean_text, llm_engine=self.llm, allowed_types=allowed_types
            )
            clean_spans.extend(
                _spans_from_transcription_fields(clean_text, transcription.fields, allowed_types)
            )

            # Store redactions
            for red in redaction_meta:
                for box in red["bboxes"]:
                    r = Redaction(
                        document_id=doc.id,
                        redaction_type=red["type"],
                        original_value=red.get("value", "")[:255],
                        bbox={"bbox": box["bbox"]},
                        confidence=red["confidence"],
                        method=red.get("method", "ocr_bboxes"),
                    )
                    db.add(r)

            # Redact image and text (outputs go into per-doc folder)
            redacted_path = self.redaction.redact_image(preprocessed_path, redaction_meta, out_dir=out_folder)
            mask_path = self.redaction.generate_mask_overlay(preprocessed_path, redaction_meta, out_dir=out_folder)
            redacted_text = self.redaction.redact_text(clean_text, clean_spans)

            # Handwriting safety pass — extra image-coordinate redactions for low-confidence docs
            hw_applied = self.redaction.handwriting_safety_pass(
                redacted_path,
                words,
                ocr_result["average_confidence"],
                allowed_types,
            )
            if hw_applied:
                doc.flag_needs_review = True
                # Keep preview in sync
                self.redaction.handwriting_safety_pass(
                    mask_path,
                    words,
                    ocr_result["average_confidence"],
                    allowed_types,
                )

            # Update OCR record with redacted text
            ocr_record.redacted_text = redacted_text
            doc.redacted_path = redacted_path
            doc.mask_path = mask_path
            doc.transcription_json_path = write_transcription_json(out_folder, transcription_data)

            text_paths = write_text_artifacts(out_folder, doc.id, text, clean_text, redacted_text)
            doc.text_export_path = text_paths["text_export_path"]
            doc.transcription_clean_path = text_paths["transcription_clean_path"]

            # Check low-confidence redactions
            low_confidence = any(r["confidence"] < CONFIDENCE_THRESHOLD for r in redaction_meta)
            if low_confidence:
                doc.flag_needs_review = True
            if transcription.needs_review_reason or transcription.confidence < 0.65:
                doc.flag_needs_review = True

            # Profile-based review (safeguarding, foi_legal, unknown always flagged)
            if requires_review(effective_category, profiles):
                doc.flag_needs_review = True

            db.commit()

            # 4. Translation (if non-English detected and enabled)
            await self._set_status(db, doc, "translation", "Detecting language")
            await asyncio.sleep(0.1)

            # Always detect language
            if self.llm and self.llm.available:
                lang = self.llm.detect_language(text)
            else:
                lang = self.translation.detect_language(text)
            doc.language_detected = lang

            if lang != "en" and translate_enabled:
                # Translation: LLM first (Qwen is multilingual), then MarianMT fallback
                if self.llm and self.llm.available:
                    translated_text = self.llm.translate(text)
                else:
                    translated_text = self.translation.translate(text, lang, "en")
                # Re-redact translated output (reuse same allowed_types from step 3)
                translated_spans = self.redaction.detect_sensitive_text(
                    translated_text, llm_engine=self.llm, allowed_types=allowed_types
                )
                translated_text = self.redaction.redact_text(translated_text, translated_spans)
                ocr_record.translated_text = translated_text
                doc.translated = True
                db.commit()
            else:
                doc.translated = False

            # 5 + 6. Classification, Routing, Sentiment — all in one LLM call if available
            await self._set_status(db, doc, "classification", "Classifying document")
            await asyncio.sleep(0.1)

            text_for_classify = ocr_record.redacted_text or clean_text or text
            llm_result = {}
            if self.llm and self.llm.available:
                llm_result = self.llm.classify_and_analyse(text_for_classify)

            if llm_result.get("category"):
                # LLM succeeded — use its output
                doc.category = llm_result["category"]
                doc.department = llm_result.get("department") or self.classification.recommend_department(doc.category)
                doc.confidence_score = float(llm_result.get("confidence", 0.82))
            else:
                # Fallback: keyword classifier
                class_result = self.classification.classify_document(text_for_classify)
                doc.category = class_result["category"]
                doc.department = self.classification.recommend_department(doc.category)
                doc.confidence_score = class_result["confidence"]

            # If staff-selected category disagrees with AI prediction → flag review
            if doc.selected_category and doc.selected_category != doc.category:
                doc.flag_needs_review = True
            if transcription_category and transcription_category != "unknown" and doc.category and transcription_category != doc.category:
                doc.flag_needs_review = True

            db.commit()

            # 6. Routing + Sentiment/Urgency
            await self._set_status(db, doc, "routing", "Computing urgency & routing")
            await asyncio.sleep(0.1)

            if llm_result.get("urgency_score") is not None:
                doc.urgency_score = float(llm_result["urgency_score"])
                doc.sentiment = llm_result.get("sentiment", "neutral")
                doc.risk_flags = llm_result.get("risk_flags", [])
            else:
                # Fallback: keyword-based sentiment/urgency
                sentiment_result = self.sentiment.analyze(text_for_classify, doc.category)
                doc.urgency_score = sentiment_result["urgency_score"]
                doc.sentiment = sentiment_result["sentiment"]
                doc.risk_flags = sentiment_result["risk_flags"]
            db.commit()

            # 7. Write metadata.json
            if doc.output_folder_path:
                meta = {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "category": doc.category,
                    "selected_category": doc.selected_category,
                    "redaction_profile": doc.redaction_profile,
                    "handwriting_backend": doc.handwriting_backend,
                    "handwriting_confidence": doc.handwriting_confidence,
                    "handwriting_review_reason": doc.handwriting_review_reason,
                    "department": doc.department,
                    "urgency_score": doc.urgency_score,
                    "sentiment": doc.sentiment,
                    "risk_flags": doc.risk_flags or [],
                    "language_detected": doc.language_detected,
                    "translated": doc.translated,
                    "flag_needs_review": doc.flag_needs_review,
                    "ocr_confidence": ocr_result["average_confidence"],
                    "redaction_count": len(redaction_meta),
                    "transcription_field_count": len(transcription.fields),
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
                write_metadata_json(doc.output_folder_path, meta)
                doc.redacted_docx_path = write_redacted_docx(
                    doc.output_folder_path,
                    doc.id,
                    doc.filename,
                    clean_text,
                    redacted_text,
                    meta,
                )
                db.commit()

            # 8. Complete
            if doc.flag_needs_review:
                await self._set_status(db, doc, "needs_review", "Flagged for review")
            else:
                await self._set_status(db, doc, "complete", "Processing finished")

        except Exception as e:
            logger.exception("Pipeline failed for doc %s: %s", doc_id, e)
            db.rollback()
            try:
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    doc.status = "error"
                    db.commit()
                    log_action(db, doc.id, "error", details={"error": str(e)})
            except Exception:
                pass
        finally:
            if own_session:
                db.close()


def _normalise_field_type(field_type: str) -> str:
    """Map VLM field types onto internal redaction types."""
    mapping = {
        "name": "person_name",
        "full_name": "person_name",
        "patient_name": "person_name",
        "child_name": "person_name",
        "national_id": "nin",
        "national_insurance": "nin",
        "nhs_number": "nhs_number",
        "bank": "bank_details",
        "sort_code": "bank_details",
        "pcn": "pcn",
        "school": "school",
        "reference": "council_ref",
        "ref": "council_ref",
        "medical": "medical_details",
        "allergy": "medical_details",
    }
    cleaned = (field_type or "").strip().lower()
    return mapping.get(cleaned, cleaned)


def _spans_from_transcription_fields(
    text: str,
    fields: list[dict],
    allowed_types: set,
) -> list[dict]:
    """Convert VLM extracted fields into text spans when values are present."""
    spans: list[dict] = []
    if not text or not fields:
        return spans
    lower_text = text.lower()
    for field in fields:
        if not isinstance(field, dict):
            continue
        value = str(field.get("value") or "").strip()
        if len(value) < 2:
            continue
        rtype = _normalise_field_type(str(field.get("type") or ""))
        if allowed_types and rtype not in allowed_types:
            continue
        idx = text.find(value)
        if idx == -1:
            idx = lower_text.find(value.lower())
        if idx == -1:
            continue
        end = idx + len(value)
        spans.append(
            {
                "type": rtype,
                "start": idx,
                "end": end,
                "value": value,
                "confidence": float(field.get("confidence") or 0.78),
                "method": "vlm_field",
            }
        )
    return spans
