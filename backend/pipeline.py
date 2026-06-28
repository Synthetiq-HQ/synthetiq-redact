import json
import logging
import os
import re
import asyncio
import shutil
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from config import CONFIDENCE_THRESHOLD, PROCESSED_DIR, CATEGORIES
from database_v2 import SessionLocal
from models_v2 import Document, DocumentPage, OCRResult, Redaction, RedactionReview
from audit_v2 import log_action
from preprocessing import render_document_pages
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
from vision_verifier import compare_ocr_and_vision, run_vision_verification

# Optional image-based redaction detector pass. Off by default; the pilot model is
# review-assist only and must never replace OCR/text redaction.
ENABLE_IMAGE_REDACTION_DETECTOR = os.environ.get("ENABLE_IMAGE_REDACTION_DETECTOR", "0") == "1"

# Optional hybrid GLM-OCR + geometry mapping for precise value-level redaction.
# Off by default: when on, sensitive values are detected on GLM-OCR's clean text
# and mapped to EasyOCR word boxes by RedactionGeometryMapper. Falls back to the
# existing OCR map_to_bboxes path if GLM-OCR is unavailable.
USE_GLM_GEOMETRY_REDACTION = os.environ.get("USE_GLM_GEOMETRY_REDACTION", "0") == "1"


def _pdf_page_count(path: str) -> Optional[int]:
    if os.path.splitext(path)[1].lower() != ".pdf":
        return None
    try:
        from PyPDF2 import PdfReader
        return len(PdfReader(path).pages)
    except Exception:
        return None


def _public_error_message(exc: Exception) -> str:
    message = str(exc)
    lower = message.lower()
    if "pdf" in lower:
        return "The PDF could not be rendered. Check that the file is valid and PDF rendering support is installed."
    if "word" in lower or "docx" in lower:
        return "The Word document could not be rendered. Upload a valid .docx file."
    if "cannot load image" in lower or "could not load image" in lower:
        return "The file could not be converted into a readable image. Upload a valid PDF, DOCX, or supported image."
    return "Processing failed. Check the server logs for details."


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


def _valid_sensitive_span(span: dict) -> bool:
    """Drop obvious false-positive spans before creating image boxes."""
    stype = str(span.get("type") or "").lower()
    value = str(span.get("value") or "")
    compact = re.sub(r"\s+", "", value)
    if stype == "email":
        return "@" in value and "." in value.split("@")[-1]
    if stype == "phone":
        return len(re.sub(r"\D", "", value)) >= 10
    if stype in {"postcode", "postal_code"}:
        return bool(re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", value, re.I))
    if stype in {"reference", "case_reference", "council_ref"}:
        return any(ch.isdigit() for ch in value) and ("-" in value or len(compact) >= 6)
    return True


def _bbox_rect(bbox: dict) -> Optional[tuple[float, float, float, float]]:
    points = bbox.get("bbox") if isinstance(bbox, dict) else bbox
    if not points:
        return None
    try:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _rect_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if intersection <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _rect_overlap_min_frac(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if intersection <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    smaller = min(area_a, area_b)
    return intersection / smaller if smaller > 0 else 0.0


def _dedupe_redaction_meta(redaction_meta: list[dict]) -> list[dict]:
    """Drop near-identical boxes while preserving explicit field-line fixes."""
    flattened: list[dict] = []
    for red in redaction_meta:
        for box in red.get("bboxes", []):
            flattened.append({**red, "bboxes": [box]})

    flattened.sort(
        key=lambda item: (
            0 if item.get("method") in {"field_line", "signed_name_line"} else 1,
            -float(item.get("confidence", 0.0)),
        )
    )

    kept: list[dict] = []
    for item in flattened:
        rect = _bbox_rect(item.get("bboxes", [{}])[0].get("bbox", {}))
        if rect is None:
            kept.append(item)
            continue
        duplicate = False
        for existing in kept:
            existing_rect = _bbox_rect(existing.get("bboxes", [{}])[0].get("bbox", {}))
            same_type = item.get("type") == existing.get("type")
            if existing_rect and (
                _rect_iou(rect, existing_rect) >= 0.70
                or (same_type and _rect_overlap_min_frac(rect, existing_rect) >= 0.70)
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


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
        self._ocr_lock = threading.RLock()

    async def _set_status(self, db: Session, doc: Document, status: str, detail: str = "") -> None:
        doc.status = status
        db.commit()
        log_action(db, doc.id, f"status_change", details={"status": status, "detail": detail})

    def _apply_image_detector(self, db: Session, doc: Document, page: DocumentPage, image_path: Optional[str]) -> int:
        """
        Optional review-assist pass: add pending image-detector candidate boxes.

        Returns the number of pending candidate rows inserted. Failures are
        swallowed (logged) so a flaky/missing detector never breaks processing.
        """
        if not image_path or not os.path.exists(image_path):
            return 0
        try:
            from image_redaction_detector import get_detector, DetectorUnavailableError
            detector = get_detector()
            try:
                predictions = detector.predict(image_path, page.page_number)
            except DetectorUnavailableError as exc:
                logger.info("Image detector unavailable, skipping pass: %s", exc)
                return 0
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Image detector pass failed: %s", exc)
            return 0

        inserted = 0
        for prediction in predictions:
            db.add(Redaction(
                document_id=doc.id,
                page_id=page.id,
                page_number=page.page_number,
                redaction_type=prediction["redaction_type"],
                original_value="[image model candidate]",
                bbox=prediction["bbox"],
                confidence=prediction["confidence"],
                method=prediction["method"],
                status="pending",
            ))
            inserted += 1
        if inserted:
            doc.flag_needs_review = True
        return inserted

    def _glm_geometry_meta(self, page, words, allowed_types, review_reasons, page_label, doc, ocr_record=None):
        """
        Hybrid precise redaction: GLM-OCR clean text -> sensitive spans -> mapped
        onto EasyOCR word boxes by RedactionGeometryMapper.

        Returns redaction_meta in the same shape as RedactionEngine.map_to_bboxes
        (so the existing insertion + image-burning code is reused unchanged), or
        None to signal the caller should fall back to the OCR mapping path.
        """
        if not words:
            return None
        try:
            from glm_ocr_engine import get_glm_engine, GLMOCRUnavailable
            from redaction_geometry_mapper import RedactionGeometryMapper

            source_image = page.display_image_path or page.original_image_path or page.ocr_image_path
            try:
                glm_text = get_glm_engine().transcribe(source_image)
            except GLMOCRUnavailable as exc:
                logger.info("GLM-OCR unavailable, falling back to OCR mapping: %s", exc)
                return None

            # Surface GLM's clean transcription in the review UI (the raw OCR text
            # stays in extracted_text for word-box mapping).
            if ocr_record is not None:
                ocr_record.clean_text = glm_text

            spans = self.redaction.detect_sensitive_text(
                glm_text, llm_engine=self.llm, allowed_types=allowed_types
            )
            spans = [span for span in spans if _valid_sensitive_span(span)]
            mapped = RedactionGeometryMapper().map(
                glm_text, spans, words, int(page.width or 0), int(page.height or 0)
            )

            meta = []
            any_review = False
            for r in mapped:
                if r.get("needs_review"):
                    any_review = True
                if not r.get("bbox"):
                    continue  # suppressed low-confidence box -> review flag only
                meta.append({
                    "type": r["type"],
                    "value": r.get("original_value", ""),
                    "confidence": r.get("confidence", 0.0),
                    "method": r.get("method", "glm_geometry"),
                    "bboxes": [{"bbox": r["bbox"]["bbox"], "confidence": r.get("confidence", 0.0)}],
                })
            if any_review:
                doc.flag_needs_review = True
                review_reasons.append(f"{page_label}: GLM geometry redaction flagged candidates for review")
            return meta
        except Exception as exc:  # pragma: no cover - defensive, never break processing
            logger.warning("GLM geometry redaction failed, falling back to OCR mapping: %s", exc)
            return None

    async def process(self, doc_id: int, db_session: Optional[Session] = None, translate_enabled: bool = True) -> None:
        """Main async processing pipeline with first-class multi-page support."""
        db = db_session or SessionLocal()
        own_session = db_session is None
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return

            await self._set_status(db, doc, "preprocessing", "Rendering document pages")
            await asyncio.sleep(0.1)

            out_folder = os.path.join(PROCESSED_DIR, "documents", f"doc_{doc.id}")
            pages_folder = os.path.join(out_folder, "pages")
            os.makedirs(out_folder, exist_ok=True)
            doc.output_folder_path = out_folder
            doc.flag_needs_review = False
            doc.needs_review_reason = None

            # Reprocessing should not leave stale page/redaction/OCR rows behind.
            db.query(RedactionReview).filter(RedactionReview.document_id == doc.id).delete(synchronize_session=False)
            db.query(Redaction).filter(Redaction.document_id == doc.id).delete(synchronize_session=False)
            db.query(OCRResult).filter(OCRResult.document_id == doc.id).delete(synchronize_session=False)
            db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete(synchronize_session=False)
            db.commit()

            orig_ext = os.path.splitext(doc.original_path)[1]
            orig_copy = os.path.join(out_folder, f"original{orig_ext}")
            if doc.original_path and os.path.exists(doc.original_path) and not os.path.exists(orig_copy):
                shutil.copy2(doc.original_path, orig_copy)

            page_metas = render_document_pages(doc.original_path, pages_folder)
            pages: list[DocumentPage] = []
            for meta in page_metas:
                page = DocumentPage(
                    document_id=doc.id,
                    page_number=meta["page_number"],
                    original_image_path=meta["original_image_path"],
                    display_image_path=meta["display_image_path"],
                    ocr_image_path=meta["ocr_image_path"],
                    width=meta["width"],
                    height=meta["height"],
                    vision_status="not_run",
                )
                db.add(page)
                pages.append(page)
            db.commit()
            for page in pages:
                db.refresh(page)

            if len(pages) > 1:
                doc.flag_needs_review = True

            await self._set_status(db, doc, "ocr", f"Extracting text from {len(pages)} page(s)")
            await asyncio.sleep(0.1)

            all_raw_text: list[str] = []
            all_clean_text: list[str] = []
            all_redacted_text: list[str] = []
            page_transcriptions: list[dict] = []
            review_reasons: list[str] = []
            total_redaction_boxes = 0
            transcription_categories: list[str] = []
            ocr_confidences: list[float] = []
            handwriting_confidences: list[float] = []
            handwriting_backends: set[str] = set()
            handwriting_review_reasons: list[str] = []
            redaction_engine_paths: set[str] = set()

            for page in pages:
                page_label = f"Page {page.page_number}"
                with self._ocr_lock:
                    ocr_result = self.ocr.extract_text(page.ocr_image_path)
                    transcription = self.handwriting.transcribe(page.ocr_image_path, ocr_result)
                transcription_data = transcription.to_dict()
                text = ocr_result.get("full_text") or ""
                words = ocr_result.get("words") or []
                clean_text = transcription.full_text or text
                avg_confidence = float(ocr_result.get("average_confidence") or 0.0)
                page.ocr_confidence = avg_confidence
                ocr_confidences.append(avg_confidence)
                handwriting_confidences.append(float(transcription.confidence or 0.0))
                if transcription.backend:
                    handwriting_backends.add(transcription.backend)
                if transcription.needs_review_reason:
                    handwriting_review_reasons.append(f"{page_label}: {transcription.needs_review_reason}")
                if transcription.document_type_guess:
                    transcription_categories.append(transcription.document_type_guess)

                ocr_record = OCRResult(
                    document_id=doc.id,
                    page_id=page.id,
                    page_number=page.page_number,
                    extracted_text=text,
                    clean_text=clean_text,
                    transcription_data=transcription_data,
                    ocr_confidence=avg_confidence,
                    words=words,
                )
                db.add(ocr_record)
                db.flush()

                transcription_category = transcription.document_type_guess
                if transcription_category and transcription_category not in CATEGORIES:
                    transcription_category = "unknown"
                effective_category = doc.selected_category or transcription_category or _keyword_estimate(clean_text or text)
                profiles = get_profiles_for_category(effective_category)
                allowed_types = get_allowed_types(profiles)
                doc.redaction_profile = ",".join(profiles)

                sensitive_spans = self.redaction.detect_sensitive_text(
                    text,
                    llm_engine=self.llm,
                    allowed_types=allowed_types,
                )
                sensitive_spans.extend(
                    _spans_from_transcription_fields(text, transcription.fields, allowed_types)
                )
                await self._set_status(db, doc, "redaction", f"Finding sensitive data on {page_label}")
                redaction_meta = None
                if USE_GLM_GEOMETRY_REDACTION:
                    redaction_meta = self._glm_geometry_meta(
                        page, words, allowed_types, review_reasons, page_label, doc, ocr_record
                    )
                    if redaction_meta is not None:
                        redaction_engine_paths.add("synthetiq_redact_v3_glm_geometry")
                    else:
                        redaction_engine_paths.add("fallback_easyocr_geometry_glm_unavailable")
                        doc.flag_needs_review = True
                        review_reasons.append(
                            f"{page_label}: Synthetiq Redact v3 GLM geometry unavailable; fallback OCR geometry used"
                        )
                else:
                    redaction_engine_paths.add("fallback_easyocr_geometry_config_off")
                if redaction_meta is None:
                    redaction_meta = self.redaction.map_to_bboxes(sensitive_spans, words)
                redaction_meta.extend(
                    self.redaction.map_label_lines_to_bboxes(words, allowed_types)
                )
                redaction_meta = _dedupe_redaction_meta(redaction_meta)

                clean_spans = self.redaction.detect_sensitive_text(
                    clean_text,
                    llm_engine=self.llm,
                    allowed_types=allowed_types,
                )
                clean_spans.extend(
                    _spans_from_transcription_fields(clean_text, transcription.fields, allowed_types)
                )

                for red in redaction_meta:
                    for box in red.get("bboxes", []):
                        db.add(Redaction(
                            document_id=doc.id,
                            page_id=page.id,
                            page_number=page.page_number,
                            redaction_type=red["type"],
                            original_value=(red.get("value") or "")[:255],
                            bbox={"bbox": box["bbox"]},
                            confidence=red.get("confidence", 0.0),
                            method=red.get("method", "ocr_bboxes"),
                            status="pending",
                        ))
                        total_redaction_boxes += 1

                if ENABLE_IMAGE_REDACTION_DETECTOR:
                    model_boxes = self._apply_image_detector(
                        db, doc, page, page.display_image_path or page.original_image_path
                    )
                    if model_boxes:
                        total_redaction_boxes += model_boxes
                        review_reasons.append(f"{page_label}: image detector added review candidates")

                page_out_folder = os.path.join(out_folder, f"page_{page.page_number:04d}")
                os.makedirs(page_out_folder, exist_ok=True)
                redaction_image_path = page.display_image_path or page.original_image_path
                redacted_path = self.redaction.redact_image(redaction_image_path, redaction_meta, out_dir=page_out_folder)
                mask_path = self.redaction.generate_mask_overlay(redaction_image_path, redaction_meta, out_dir=page_out_folder)
                redacted_text = self.redaction.redact_text(clean_text, clean_spans)

                hw_applied = self.redaction.handwriting_safety_pass(
                    redacted_path,
                    words,
                    avg_confidence,
                    allowed_types,
                )
                if hw_applied:
                    doc.flag_needs_review = True
                    review_reasons.append(f"{page_label}: handwriting/low-confidence safety pass applied")
                    self.redaction.handwriting_safety_pass(
                        mask_path,
                        words,
                        avg_confidence,
                        allowed_types,
                    )

                ocr_record.redacted_text = redacted_text
                page.redacted_image_path = redacted_path
                page.mask_image_path = mask_path

                if page.page_number == 1:
                    doc.redacted_path = redacted_path
                    doc.mask_path = mask_path

                low_confidence_redactions = any(
                    red.get("confidence", 0.0) < CONFIDENCE_THRESHOLD for red in redaction_meta
                )
                if low_confidence_redactions:
                    doc.flag_needs_review = True
                    review_reasons.append(f"{page_label}: low-confidence redaction candidates")
                if avg_confidence < 0.70:
                    doc.flag_needs_review = True
                    review_reasons.append(f"{page_label}: low OCR confidence ({avg_confidence:.2f})")
                if transcription.needs_review_reason or transcription.confidence < 0.65:
                    doc.flag_needs_review = True
                if requires_review(effective_category, profiles):
                    doc.flag_needs_review = True
                    review_reasons.append(f"{page_label}: {effective_category} profile requires human review")

                vision = run_vision_verification(page.display_image_path or page.ocr_image_path, text)
                warnings = compare_ocr_and_vision(text, vision)
                page.vision_status = vision.get("status", "failed")
                page.vision_text = vision.get("full_text") or ""
                page.vision_items = vision.get("sensitive_items") or []
                page.vision_warnings = warnings
                if page.vision_status != "complete" or warnings:
                    doc.flag_needs_review = True
                    review_reasons.append(f"{page_label}: vision verification needs review")

                page_transcriptions.append({
                    "page_number": page.page_number,
                    "ocr_confidence": avg_confidence,
                    "transcription": transcription_data,
                    "vision": vision,
                    "vision_warnings": warnings,
                })
                all_raw_text.append(f"--- Page {page.page_number} ---\n{text}".strip())
                all_clean_text.append(f"--- Page {page.page_number} ---\n{clean_text}".strip())
                all_redacted_text.append(f"--- Page {page.page_number} ---\n{redacted_text}".strip())
                db.commit()

            combined_raw_text = "\n\n".join(all_raw_text)
            combined_clean_text = "\n\n".join(all_clean_text)
            combined_redacted_text = "\n\n".join(all_redacted_text)

            doc.transcription_json_path = write_transcription_json(
                out_folder,
                {
                    "document_id": doc.id,
                    "page_count": len(pages),
                    "pages": page_transcriptions,
                },
            )
            text_paths = write_text_artifacts(
                out_folder,
                doc.id,
                combined_raw_text,
                combined_clean_text,
                combined_redacted_text,
            )
            doc.text_export_path = text_paths["text_export_path"]
            doc.transcription_clean_path = text_paths["transcription_clean_path"]
            doc.handwriting_backend = ",".join(sorted(handwriting_backends)) or None
            doc.handwriting_confidence = (
                sum(handwriting_confidences) / len(handwriting_confidences)
                if handwriting_confidences else None
            )
            doc.handwriting_review_reason = "; ".join(handwriting_review_reasons[:6]) or None
            doc.engine_used = ",".join(sorted(redaction_engine_paths)) or None

            await self._set_status(db, doc, "translation", "Checking document language")
            await asyncio.sleep(0.1)
            if self.llm and self.llm.available:
                lang = self.llm.detect_language(combined_raw_text)
            else:
                lang = self.translation.detect_language(combined_raw_text)
            doc.language_detected = lang

            latest_ocr = db.query(OCRResult).filter(
                OCRResult.document_id == doc.id,
                OCRResult.page_number == 1,
            ).first()
            if lang != "en" and translate_enabled:
                if self.llm and self.llm.available:
                    translated_text = self.llm.translate(combined_raw_text)
                else:
                    translated_text = self.translation.translate(combined_raw_text, lang, "en")
                translated_spans = self.redaction.detect_sensitive_text(
                    translated_text,
                    llm_engine=self.llm,
                    allowed_types=None,
                )
                translated_text = self.redaction.redact_text(translated_text, translated_spans)
                if latest_ocr:
                    latest_ocr.translated_text = translated_text
                doc.translated = True
            else:
                doc.translated = False

            await self._set_status(db, doc, "classification", "Classifying document")
            await asyncio.sleep(0.1)
            text_for_classify = combined_redacted_text or combined_clean_text or combined_raw_text
            llm_result = {}
            if self.llm and self.llm.available:
                llm_result = self.llm.classify_and_analyse(text_for_classify)

            if llm_result.get("category"):
                doc.category = llm_result["category"]
                doc.department = llm_result.get("department") or self.classification.recommend_department(doc.category)
                doc.confidence_score = float(llm_result.get("confidence", 0.82))
            else:
                class_result = self.classification.classify_document(text_for_classify)
                doc.category = class_result["category"]
                doc.department = self.classification.recommend_department(doc.category)
                doc.confidence_score = class_result["confidence"]

            valid_transcription_categories = [
                category for category in transcription_categories
                if category in CATEGORIES and category != "unknown"
            ]
            if doc.selected_category and doc.selected_category != doc.category:
                doc.flag_needs_review = True
                review_reasons.append("Selected category disagrees with automatic classification")
            if valid_transcription_categories and doc.category not in set(valid_transcription_categories):
                doc.flag_needs_review = True
                review_reasons.append("Page transcription category disagrees with document classification")

            await self._set_status(db, doc, "routing", "Computing urgency and routing")
            await asyncio.sleep(0.1)
            if llm_result.get("urgency_score") is not None:
                doc.urgency_score = float(llm_result["urgency_score"])
                doc.sentiment = llm_result.get("sentiment", "neutral")
                doc.risk_flags = llm_result.get("risk_flags", [])
            else:
                sentiment_result = self.sentiment.analyze(text_for_classify, doc.category)
                doc.urgency_score = sentiment_result["urgency_score"]
                doc.sentiment = sentiment_result["sentiment"]
                doc.risk_flags = sentiment_result["risk_flags"]

            average_ocr_confidence = (
                sum(ocr_confidences) / len(ocr_confidences)
                if ocr_confidences else 0.0
            )
            doc.confidence_summary = {
                "page_count": len(pages),
                "average_ocr_confidence": round(average_ocr_confidence, 4),
                "vision_pages_complete": sum(1 for page in pages if page.vision_status == "complete"),
                "vision_warning_count": sum(len(page.vision_warnings or []) for page in pages),
                "redaction_count": total_redaction_boxes,
            }
            if review_reasons:
                deduped_reasons = list(dict.fromkeys(review_reasons))
                doc.needs_review_reason = "; ".join(deduped_reasons[:8])

            meta = {
                "document_id": doc.id,
                "filename": doc.filename,
                "category": doc.category,
                "selected_category": doc.selected_category,
                "redaction_profile": doc.redaction_profile,
                "handwriting_backend": doc.handwriting_backend,
                "handwriting_confidence": doc.handwriting_confidence,
                "handwriting_review_reason": doc.handwriting_review_reason,
                "needs_review_reason": doc.needs_review_reason,
                "department": doc.department,
                "urgency_score": doc.urgency_score,
                "sentiment": doc.sentiment,
                "risk_flags": doc.risk_flags or [],
                "language_detected": doc.language_detected,
                "translated": doc.translated,
                "flag_needs_review": doc.flag_needs_review,
                "page_count": len(pages),
                "ocr_confidence": average_ocr_confidence,
                "redaction_count": total_redaction_boxes,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            write_metadata_json(out_folder, meta)
            doc.redacted_docx_path = write_redacted_docx(
                out_folder,
                doc.id,
                doc.filename,
                combined_clean_text,
                combined_redacted_text,
                meta,
            )
            db.commit()

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
                    doc.status = "failed"
                    if hasattr(doc, "needs_review_reason"):
                        doc.needs_review_reason = _public_error_message(e)
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
