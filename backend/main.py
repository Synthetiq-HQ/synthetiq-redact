import asyncio
import os
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload

from config import UPLOAD_DIR, PROCESSED_DIR, DB_PATH, DEPARTMENTS
from database import init_db, get_db, SessionLocal
from models import Document, OCRResult, Redaction, AuditLog
from audit import log_action
from pipeline import DocumentPipeline
from ocr_engine import OCREngine
from redaction import RedactionEngine
from translation import TranslationEngine
from classification import ClassificationEngine
from sentiment_urgency import SentimentUrgencyEngine
from llm_engine import LLMEngine
from handwriting_transcription import HandwritingTranscriptionEngine

app = FastAPI(title="Hillingdon Council Document Processor", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for AI model warm-up
app.state.ocr_engine = None
app.state.redaction_engine = None
app.state.translation_engine = None
app.state.classification_engine = None
app.state.sentiment_engine = None
app.state.llm_engine = None
app.state.handwriting_engine = None
app.state.pipeline = None


@app.on_event("startup")
async def startup_event():
    init_db()
    print("[startup] Initialising AI models...")
    app.state.ocr_engine = OCREngine()
    app.state.redaction_engine = RedactionEngine()
    app.state.translation_engine = TranslationEngine()
    app.state.classification_engine = ClassificationEngine()
    app.state.sentiment_engine = SentimentUrgencyEngine()
    app.state.llm_engine = LLMEngine()
    app.state.handwriting_engine = HandwritingTranscriptionEngine()
    app.state.pipeline = DocumentPipeline(
        ocr_engine=app.state.ocr_engine,
        redaction_engine=app.state.redaction_engine,
        translation_engine=app.state.translation_engine,
        classification_engine=app.state.classification_engine,
        sentiment_engine=app.state.sentiment_engine,
        llm_engine=app.state.llm_engine,
        handwriting_engine=app.state.handwriting_engine,
    )
    print("[startup] Models loaded.")


@app.on_event("shutdown")
async def shutdown_event():
    print("[shutdown] Cleaning up...")


async def _run_pipeline(doc_id: int, translate_enabled: bool = True) -> None:
    """Background task wrapper for pipeline."""
    db = SessionLocal()
    try:
        await app.state.pipeline.process(doc_id, db, translate_enabled=translate_enabled)
    finally:
        db.close()


# Status -> percent mapping for SSE
STATUS_PERCENT = {
    "uploaded": 5,
    "preprocessing": 15,
    "ocr": 30,
    "redaction": 50,
    "translation": 60,
    "classification": 75,
    "routing": 85,
    "complete": 100,
    "needs_review": 100,
    "error": 100,
}


@app.post("/api/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    translate: str = Form("0"),
    selected_category: str = Form(""),
    db: Session = Depends(get_db),
):
    """Upload a document and start processing."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".pdf", ".gif", ".bmp", ".tiff"):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    safe_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        filename=file.filename,
        original_path=file_path,
        status="uploaded",
        selected_category=selected_category or None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    log_action(db, doc.id, "uploaded", details={"filename": file.filename, "path": file_path})

    translate_enabled = translate == "1"
    background_tasks.add_task(_run_pipeline, doc.id, translate_enabled)

    return {"document_id": doc.id, "status": "uploaded"}


@app.get("/api/progress/{doc_id}")
async def progress_stream(doc_id: int, db: Session = Depends(get_db)):
    """SSE stream of document processing progress."""
    async def event_generator():
        last_status = None
        while True:
            db_local = SessionLocal()
            try:
                doc = db_local.query(Document).filter(Document.id == doc_id).first()
                if not doc:
                    yield f"data: {json.dumps({'status': 'error', 'message': 'Document not found', 'percent': 0})}\n\n"
                    break
                if doc.status != last_status:
                    last_status = doc.status
                    percent = STATUS_PERCENT.get(doc.status, 0)
                    message = {
                        "uploaded": "Document uploaded...",
                        "preprocessing": "Preprocessing image...",
                        "ocr": "Extracting text with OCR...",
                        "redaction": "Detecting and redacting sensitive data...",
                        "translation": "Translating non-English text...",
                        "classification": "Classifying document...",
                        "routing": "Computing urgency and routing...",
                        "complete": "Processing complete!",
                        "needs_review": "Processing complete — flagged for review",
                        "error": "Processing failed",
                    }.get(doc.status, "Processing...")
                    payload = json.dumps({"status": doc.status, "message": message, "percent": percent})
                    yield f"data: {payload}\n\n"
                if doc.status in ("complete", "error", "needs_review"):
                    break
            finally:
                db_local.close()
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/document/{doc_id}")
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    """Get full document details with nested OCR and redactions."""
    doc = (
        db.query(Document)
        .options(
            joinedload(Document.ocr_results),
            joinedload(Document.redactions),
            joinedload(Document.audit_logs),
        )
        .filter(Document.id == doc_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    ocr_data = None
    if doc.ocr_results:
        ocr = doc.ocr_results[0]
        ocr_data = {
            "id": ocr.id,
            "extracted_text": ocr.extracted_text,
            "redacted_text": ocr.redacted_text,
            "translated_text": ocr.translated_text,
            "clean_text": ocr.clean_text,
            "transcription_data": ocr.transcription_data,
            "ocr_confidence": ocr.ocr_confidence,
            "words": ocr.words,
        }

    redactions_data = [
        {
            "id": r.id,
            "type": r.redaction_type,
            "original_value": r.original_value,
            "bbox": r.bbox,
            "confidence": r.confidence,
            "method": r.method,
        }
        for r in doc.redactions
    ]

    return {
        "id": doc.id,
        "filename": doc.filename,
        "original_path": doc.original_path,
        "redacted_path": doc.redacted_path,
        "mask_path": doc.mask_path,
        "status": doc.status,
        "category": doc.category,
        "department": doc.department,
        "urgency_score": doc.urgency_score,
        "sentiment": doc.sentiment,
        "risk_flags": doc.risk_flags,
        "confidence_score": doc.confidence_score,
        "language_detected": doc.language_detected,
        "translated": doc.translated,
        "flag_needs_review": doc.flag_needs_review,
        "selected_category": doc.selected_category,
        "redaction_profile": doc.redaction_profile,
        "output_folder_path": doc.output_folder_path,
        "transcription_clean_path": doc.transcription_clean_path,
        "transcription_json_path": doc.transcription_json_path,
        "redacted_docx_path": doc.redacted_docx_path,
        "handwriting_backend": doc.handwriting_backend,
        "handwriting_confidence": doc.handwriting_confidence,
        "handwriting_review_reason": doc.handwriting_review_reason,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "ocr": ocr_data,
        "redactions": redactions_data,
    }


@app.get("/api/document/{doc_id}/image")
async def get_document_image(
    doc_id: int,
    type: str = Query("original", enum=["original", "redacted", "mask"]),
    db: Session = Depends(get_db),
):
    """Serve original, redacted, or mask image."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if type == "original":
        path = doc.original_path
    elif type == "redacted":
        path = doc.redacted_path
    elif type == "mask":
        path = doc.mask_path
    else:
        raise HTTPException(status_code=400, detail="Invalid image type")

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(path)


@app.get("/api/document/{doc_id}/export")
async def export_document(
    doc_id: int,
    type: str = Query("text", enum=["text", "clean", "json", "docx"]),
    db: Session = Depends(get_db),
):
    """Download a processed document export."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    export_map = {
        "text": (doc.text_export_path, "text/plain", f"document_{doc_id}_redacted.txt"),
        "clean": (doc.transcription_clean_path, "text/plain", f"document_{doc_id}_clean_transcription.txt"),
        "json": (doc.transcription_json_path, "application/json", f"document_{doc_id}_transcription.json"),
        "docx": (
            doc.redacted_docx_path,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"document_{doc_id}_redacted.docx",
        ),
    }
    path, media_type, filename = export_map[type]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{type} export not available")
    return FileResponse(path, media_type=media_type, filename=filename)


@app.post("/api/document/{doc_id}/approve")
async def approve_document(doc_id: int, db: Session = Depends(get_db)):
    """Approve a processed document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "complete"
    doc.flag_needs_review = False
    db.commit()
    log_action(db, doc.id, "approved")
    return {"message": "Document approved", "status": "complete"}


@app.post("/api/document/{doc_id}/review")
async def review_document(doc_id: int, db: Session = Depends(get_db)):
    """Flag a document for human review."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "needs_review"
    doc.flag_needs_review = True
    db.commit()
    log_action(db, doc.id, "flagged_for_review")
    return {"message": "Document flagged for review", "status": "needs_review"}


@app.get("/api/documents")
async def list_documents(db: Session = Depends(get_db)):
    """List all documents with summary fields."""
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "status": d.status,
            "category": d.category,
            "department": d.department,
            "urgency_score": d.urgency_score,
            "sentiment": d.sentiment,
            "risk_flags": d.risk_flags,
            "flag_needs_review": d.flag_needs_review,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


@app.get("/api/departments")
async def list_departments():
    """List department mappings."""
    return {"departments": DEPARTMENTS}


@app.get("/health")
async def health_check():
    """Health check with model status."""
    model_status = {
        "ocr": app.state.ocr_engine is not None,
        "redaction": app.state.redaction_engine is not None,
        "translation": app.state.translation_engine is not None,
        "classification": app.state.classification_engine is not None,
        "sentiment": app.state.sentiment_engine is not None,
        "llm_qwen": app.state.llm_engine is not None and app.state.llm_engine.available,
        "handwriting_vlm": app.state.handwriting_engine is not None and app.state.handwriting_engine.available,
    }
    core_ok = all(v for k, v in model_status.items() if k not in ("llm_qwen", "handwriting_vlm"))
    return {
        "status": "healthy" if core_ok else "degraded",
        "models": model_status,
    }
