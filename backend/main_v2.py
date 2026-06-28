import asyncio
import os
import json
import uuid
import hashlib
import hmac
import math
import re
import shlex
import secrets
import subprocess
import io
import zipfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, BackgroundTasks, Query, status, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
import bcrypt
import jwt

from config import UPLOAD_DIR, PROCESSED_DIR, DB_PATH, DEPARTMENTS
from database_v2 import init_db, get_db, SessionLocal
from models_v2 import (
    Document, DocumentPage, OCRResult, Redaction, AuditLog,
    User, Council, BatchJob, RedactionReview, Webhook, RetentionPolicy,
    batch_job_documents
)
from audit_v2 import log_action, verify_audit_chain
from pipeline import DocumentPipeline
from ocr_engine_v2 import OCREngineManager
from redaction import RedactionEngine
from translation import TranslationEngine
from classification import ClassificationEngine
from sentiment_urgency import SentimentUrgencyEngine
from llm_engine import LLMEngine
from handwriting_transcription import HandwritingTranscriptionEngine
from image_redaction_detector import get_detector, DetectorUnavailableError

APP_ENV = os.environ.get("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"
DEFAULT_DEV_JWT_SECRET = "dev-only-synthetiq-redact-secret-change-before-production"
DEFAULT_DEV_AUDIT_SECRET = "dev-only-synthetiq-audit-secret-change-before-production"
JWT_SECRET = os.environ.get("JWT_SECRET", DEFAULT_DEV_JWT_SECRET)
AUDIT_SECRET = os.environ.get("AUDIT_SECRET", DEFAULT_DEV_AUDIT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.environ.get("JWT_EXPIRATION_HOURS", "8"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".docx", ".gif", ".bmp", ".tiff", ".tif"}
ALLOWED_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".bmp": (b"BM",),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".tif": (b"II*\x00", b"MM\x00*"),
}
VALID_ROLES = {"admin", "reviewer", "processor", "auditor", "dpo", "caseworker"}
DEFAULT_COUNCIL_NAME = os.environ.get("DEFAULT_COUNCIL_NAME", "Pilot Council")
ENABLE_MULTI_USER_AUTH = os.environ.get("ENABLE_MULTI_USER_AUTH", "0") == "1"
LOCAL_USER_EMAIL = os.environ.get("LOCAL_USER_EMAIL", "local_user@synthetiq.local")
WEBHOOKS_ENABLED = os.environ.get("ENABLE_WEBHOOKS", "0") == "1"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://tauri.localhost,https://tauri.localhost,tauri://localhost",
    ).split(",")
    if origin.strip()
]
CORS_ORIGIN_REGEX = os.environ.get(
    "CORS_ORIGIN_REGEX",
    r"^(tauri|http|https)://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?$",
)

if IS_PRODUCTION and (
    JWT_SECRET == DEFAULT_DEV_JWT_SECRET or AUDIT_SECRET == DEFAULT_DEV_AUDIT_SECRET
):
    raise RuntimeError("Production requires explicit JWT_SECRET and AUDIT_SECRET values.")

app = FastAPI(
    title="Synthetiq Redact v2.0",
    version="2.0.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)

# Global state for AI model warm-up
app.state.ocr_engine = None
app.state.redaction_engine = None
app.state.translation_engine = None
app.state.classification_engine = None
app.state.sentiment_engine = None
app.state.llm_engine = None
app.state.handwriting_engine = None
app.state.pipeline = None


# ============================================================================
# AUTH HELPERS
# ============================================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: int, email: str, role: str, council_id: Optional[int]) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "council_id": council_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not ENABLE_MULTI_USER_AUTH:
        return get_or_create_local_user(db)

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = decode_token(credentials.credentials)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or unknown user")
    return user

def require_role(allowed_roles: List[str]):
    async def role_checker(user: User = Depends(get_current_user)):
        if not ENABLE_MULTI_USER_AUTH:
            return user
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return role_checker


def get_or_create_default_council(db: Session) -> Council:
    council = db.query(Council).order_by(Council.id.asc()).first()
    if council:
        return council
    council = Council(name=DEFAULT_COUNCIL_NAME, deployment_id=str(uuid.uuid4()))
    db.add(council)
    db.commit()
    db.refresh(council)
    return council


def get_or_create_local_user(db: Session) -> User:
    """Create/reuse the single local user used when auth is disabled."""
    council = get_or_create_default_council(db)
    user = db.query(User).filter(User.email == LOCAL_USER_EMAIL).first()
    if not user:
        user = User(
            email=LOCAL_USER_EMAIL,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role="admin",
            council_id=council.id,
            is_active=True,
            department="Local",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    changed = False
    if user.council_id is None:
        user.council_id = council.id
        changed = True
    if user.role != "admin":
        user.role = "admin"
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if changed:
        db.commit()
        db.refresh(user)
    return user


def backfill_default_council(db: Session, council: Council) -> None:
    """Attach legacy demo records to the default council for the pilot baseline."""
    changed = False
    for model in (User, Document, BatchJob, AuditLog):
        updated = (
            db.query(model)
            .filter(model.council_id.is_(None))
            .update({"council_id": council.id}, synchronize_session=False)
        )
        changed = changed or updated > 0
    if changed:
        db.commit()


def _ensure_user_council(db: Session, user: User) -> User:
    if user.council_id is None:
        council = get_or_create_default_council(db)
        user.council_id = council.id
        db.commit()
        db.refresh(user)
    return user


def _get_document_or_404(db: Session, doc_id: int, user: User) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _ensure_user_council(db, user)
    if doc.council_id is None:
        doc.council_id = user.council_id
        db.commit()
        db.refresh(doc)
    if doc.council_id != user.council_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _safe_file_response(path: Optional[str], media_type: Optional[str] = None, filename: Optional[str] = None):
    if not path:
        raise HTTPException(status_code=404, detail="File not found")

    requested = os.path.realpath(path)
    allowed_roots = [os.path.realpath(UPLOAD_DIR), os.path.realpath(PROCESSED_DIR)]
    if not any(requested == root or requested.startswith(root + os.sep) for root in allowed_roots):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.exists(requested):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(requested, media_type=media_type, filename=filename)


def _redaction_source_image_path(doc: Document) -> Optional[str]:
    """Return the rendered image used for coordinate-based redaction."""
    first_page = sorted(doc.pages or [], key=lambda page: page.page_number)[0] if doc.pages else None
    if first_page:
        return _page_source_image_path(first_page)

    if doc.original_path:
        stem = Path(doc.original_path).stem
        display = Path(PROCESSED_DIR) / f"{stem}_display.png"
        if display.exists():
            return str(display)

        preprocessed = Path(PROCESSED_DIR) / f"{stem}_preprocessed.png"
        if preprocessed.exists():
            return str(preprocessed)

        original_suffix = Path(doc.original_path).suffix.lower()
        if original_suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"} and os.path.exists(doc.original_path):
            return doc.original_path

    if doc.output_folder_path:
        folder = Path(doc.output_folder_path)
        for candidate in folder.glob("original.*"):
            if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"}:
                return str(candidate)

    return None


def _page_source_image_path(page: DocumentPage) -> Optional[str]:
    """Return the geometry-stable image used for page coordinate editing."""
    for path in (page.display_image_path, page.original_image_path, page.ocr_image_path):
        if path and os.path.exists(path):
            return path
    return None


def _get_page_or_404(db: Session, doc: Document, page_number: int) -> DocumentPage:
    page = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc.id, DocumentPage.page_number == page_number)
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


def _latest_page_ocr(db: Session, doc: Document, page: DocumentPage) -> Optional[OCRResult]:
    return (
        db.query(OCRResult)
        .filter(OCRResult.document_id == doc.id, OCRResult.page_number == page.page_number)
        .order_by(OCRResult.id.desc())
        .first()
    )


def _ocr_response(ocr: Optional[OCRResult]) -> Optional[dict]:
    if not ocr:
        return None
    return {
        "id": ocr.id,
        "page_id": ocr.page_id,
        "page_number": ocr.page_number,
        "extracted_text": ocr.extracted_text,
        "redacted_text": ocr.redacted_text,
        "translated_text": ocr.translated_text,
        "clean_text": ocr.clean_text,
        "transcription_data": ocr.transcription_data,
        "ocr_confidence": ocr.ocr_confidence,
        "words": ocr.words,
    }


def _page_response(db: Session, doc: Document, page: DocumentPage, can_view_original_value: bool = True) -> dict:
    redactions = (
        db.query(Redaction)
        .filter(Redaction.document_id == doc.id, Redaction.page_number == page.page_number)
        .order_by(Redaction.id.asc())
        .all()
    )
    warnings = page.vision_warnings or []
    return {
        "id": page.id,
        "document_id": page.document_id,
        "page_number": page.page_number,
        "width": page.width,
        "height": page.height,
        "ocr_confidence": page.ocr_confidence,
        "vision_status": page.vision_status or "not_run",
        "vision_text": page.vision_text,
        "vision_items": page.vision_items or [],
        "vision_warnings": warnings,
        "redaction_count": len([red for red in redactions if red.status != "rejected"]),
        "warning_count": len(warnings),
        "has_original": bool(_page_source_image_path(page)),
        "has_redacted": bool(page.redacted_image_path),
        "has_mask": bool(page.mask_image_path),
        "ocr": _ocr_response(_latest_page_ocr(db, doc, page)),
        "redactions": [_redaction_response(red, can_view_original_value) for red in redactions],
    }


def _normalise_bbox_payload(raw_bbox: str, image_path: Optional[str] = None) -> dict:
    try:
        payload = json.loads(raw_bbox)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid redaction box") from exc

    bbox = payload.get("bbox") if isinstance(payload, dict) else payload
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise HTTPException(status_code=400, detail="Redaction box must contain four points")

    points = []
    for point in bbox:
        if not isinstance(point, list) or len(point) != 2:
            raise HTTPException(status_code=400, detail="Redaction box points must be [x, y]")
        x, y = point
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise HTTPException(status_code=400, detail="Redaction box coordinates must be numbers")
        if not math.isfinite(float(x)) or not math.isfinite(float(y)):
            raise HTTPException(status_code=400, detail="Redaction box coordinates must be finite")
        points.append((float(x), float(y)))

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    if image_path:
        try:
            from PIL import Image

            with Image.open(image_path) as image:
                max_w, max_h = image.size
            x0, x1 = max(0.0, x0), min(float(max_w), x1)
            y0, y1 = max(0.0, y0), min(float(max_h), y1)
        except Exception:
            x0, x1 = max(0.0, x0), max(0.0, x1)
            y0, y1 = max(0.0, y0), max(0.0, y1)
    else:
        x0, x1 = max(0.0, x0), max(0.0, x1)
        y0, y1 = max(0.0, y0), max(0.0, y1)

    if x1 - x0 < 4 or y1 - y0 < 4:
        raise HTTPException(status_code=400, detail="Redaction box is too small")

    return {
        "bbox": [
            [round(x0, 2), round(y0, 2)],
            [round(x1, 2), round(y0, 2)],
            [round(x1, 2), round(y1, 2)],
            [round(x0, 2), round(y1, 2)],
        ]
    }


def _redaction_bbox_points(bbox: dict) -> Optional[list[list[float]]]:
    points = bbox.get("bbox") if isinstance(bbox, dict) else None
    if not points:
        return None
    try:
        return [[float(point[0]), float(point[1])] for point in points]
    except (TypeError, ValueError, IndexError):
        return None


def _active_redaction_rows(db: Session, doc: Document, page: Optional[DocumentPage] = None) -> list[Redaction]:
    query = db.query(Redaction).filter(
        Redaction.document_id == doc.id,
        Redaction.status != "rejected",
    )
    if page is not None:
        query = query.filter(Redaction.page_number == page.page_number)
    return query.order_by(Redaction.page_number.asc(), Redaction.id.asc()).all()


def _draw_redactions_on_image(image, redactions: list[Redaction], overlay: bool = False):
    from PIL import Image, ImageDraw

    base = image.convert("RGB")
    if overlay:
        rgba = base.convert("RGBA")
        layer = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        fill = (220, 38, 38, 100)
        outline = (127, 29, 29, 210)
    else:
        draw = ImageDraw.Draw(base)
        fill = (0, 0, 0)
        outline = None

    for redaction in redactions:
        points = _redaction_bbox_points(redaction.bbox or {})
        if not points:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        rect = (min(xs), min(ys), max(xs), max(ys))
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            continue
        draw.rectangle(rect, fill=fill, outline=outline, width=2 if outline else 1)

    if overlay:
        return Image.alpha_composite(rgba, layer).convert("RGB")
    return base


def _write_burned_page_image(db: Session, doc: Document, page: DocumentPage, overlay: bool = False) -> str:
    from PIL import Image

    source_image_path = _page_source_image_path(page)
    if not source_image_path:
        raise HTTPException(status_code=404, detail="No rendered page image is available")

    active_redactions = _active_redaction_rows(db, doc, page)
    with Image.open(source_image_path) as source:
        image = _draw_redactions_on_image(source, active_redactions, overlay=overlay)

    out_folder = Path(doc.output_folder_path or Path(PROCESSED_DIR) / "exports" / f"doc_{doc.id}") / f"page_{page.page_number:04d}"
    out_folder.mkdir(parents=True, exist_ok=True)
    out_path = out_folder / ("redaction_preview_active.png" if overlay else "redacted_active.png")
    image.save(out_path, "PNG", optimize=True)
    if overlay:
        page.mask_image_path = str(out_path)
        if page.page_number == 1:
            doc.mask_path = str(out_path)
    else:
        page.redacted_image_path = str(out_path)
        if page.page_number == 1:
            doc.redacted_path = str(out_path)
    db.commit()
    return str(out_path)


def _write_burned_redaction_image(db: Session, doc: Document, overlay: bool = False) -> str:
    first_page = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
        .first()
    )
    if first_page:
        return _write_burned_page_image(db, doc, first_page, overlay=overlay)

    from PIL import Image

    source_image_path = _redaction_source_image_path(doc)
    if not source_image_path:
        raise HTTPException(status_code=404, detail="No rendered image is available")

    with Image.open(source_image_path) as source:
        image = _draw_redactions_on_image(source, _active_redaction_rows(db, doc), overlay=overlay)

    out_folder = Path(doc.output_folder_path or Path(PROCESSED_DIR) / "exports" / f"doc_{doc.id}")
    out_folder.mkdir(parents=True, exist_ok=True)
    out_path = out_folder / ("redaction_preview_active.png" if overlay else "redacted_active.png")
    image.save(out_path, "PNG", optimize=True)
    if overlay:
        doc.mask_path = str(out_path)
    else:
        doc.redacted_path = str(out_path)
    db.commit()
    return str(out_path)


def _write_burned_redaction_pdf(db: Session, doc: Document) -> str:
    """
    Produce a raster PDF with redactions burned into pixels across all pages.

    This intentionally does not preserve source PDF text layers, annotations,
    forms, attachments, embedded files, or source metadata.
    """
    from PIL import Image

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        source_image_path = _redaction_source_image_path(doc)
        if not source_image_path:
            raise HTTPException(status_code=404, detail="No rendered image is available for PDF export")
        pages = [DocumentPage(document_id=doc.id, page_number=1, display_image_path=source_image_path)]

    images = []
    for page in pages:
        source_image_path = _page_source_image_path(page)
        if not source_image_path:
            raise HTTPException(status_code=404, detail=f"No rendered image is available for page {page.page_number}")
        with Image.open(source_image_path) as source:
            image = _draw_redactions_on_image(source, _active_redaction_rows(db, doc, page), overlay=False)
            images.append(image.convert("RGB"))

    out_folder = Path(doc.output_folder_path or Path(PROCESSED_DIR) / "exports" / f"doc_{doc.id}")
    out_folder.mkdir(parents=True, exist_ok=True)
    out_path = out_folder / "redacted_document.pdf"
    if not images:
        raise HTTPException(status_code=404, detail="No pages are available for PDF export")
    first, rest = images[0], images[1:]
    first.save(
        out_path,
        "PDF",
        resolution=200.0,
        save_all=True,
        append_images=rest,
        title="",
        author="",
        subject="",
        keywords="",
        creator="Synthetiq Redact",
        producer="Synthetiq Redact",
    )
    return str(out_path)


def _verify_burned_pdf_export(db: Session, doc: Document, pdf_path: str) -> dict:
    """Verify the exported PDF is a safe raster-burn artifact."""
    from PyPDF2 import PdfReader

    checks: list[dict] = []

    def add_check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    expected_page_count = len(pages) or 1
    active_redactions = _active_redaction_rows(db, doc)
    page_numbers = {page.page_number for page in pages} or {1}

    try:
        reader = PdfReader(pdf_path)
        add_check(
            "page_count",
            len(reader.pages) == expected_page_count,
            f"expected {expected_page_count}, got {len(reader.pages)}",
        )

        extracted_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        add_check("no_extractable_text", extracted_text == "", "hidden text found" if extracted_text else "")

        annotations = []
        for index, page in enumerate(reader.pages, start=1):
            if page.get("/Annots"):
                annotations.append(index)
        add_check("no_annotations", not annotations, f"annotations on pages {annotations}" if annotations else "")

        root = reader.trailer.get("/Root", {})
        acro_form = root.get("/AcroForm") if hasattr(root, "get") else None
        add_check("no_forms", not acro_form, "AcroForm/XFA data found" if acro_form else "")

        names = root.get("/Names") if hasattr(root, "get") else None
        embedded_files = None
        if names and hasattr(names, "get"):
            embedded_files = names.get("/EmbeddedFiles")
        add_check("no_embedded_files", not embedded_files, "embedded files found" if embedded_files else "")

        metadata = reader.metadata or {}
        allowed_metadata_keys = {"/Producer", "/Creator", "/CreationDate", "/ModDate"}
        unsafe_metadata = []
        for key, value in dict(metadata).items():
            text_value = str(value).strip() if value is not None else ""
            if not text_value:
                continue
            filename_markers = [marker for marker in (doc.filename, doc.source_filename) if marker]
            contains_source_name = any(marker in text_value for marker in filename_markers)
            if key in allowed_metadata_keys and not contains_source_name:
                continue
            if text_value not in {"Synthetiq Redact"}:
                unsafe_metadata.append(key)
        add_check("metadata_generic", not unsafe_metadata, f"non-generic metadata keys: {unsafe_metadata}" if unsafe_metadata else "")
    except Exception as exc:
        add_check("pdf_readable", False, str(exc))

    missing_page_or_bbox = [
        red.id for red in active_redactions
        if (red.page_number or 1) not in page_numbers or not _redaction_bbox_points(red.bbox or {})
    ]
    add_check(
        "active_redactions_have_page_boxes",
        not missing_page_or_bbox,
        f"redactions missing page/bbox: {missing_page_or_bbox}" if missing_page_or_bbox else "",
    )

    passed = all(check["passed"] for check in checks)
    return {
        "passed": passed,
        "pdf_path": pdf_path,
        "page_count": expected_page_count,
        "active_redactions": len(active_redactions),
        "checks": checks,
    }


def _redaction_response(redaction: Redaction, can_view_original_value: bool = True) -> dict:
    return {
        "id": redaction.id,
        "page_id": redaction.page_id,
        "page_number": redaction.page_number or 1,
        "type": redaction.redaction_type,
        "redaction_type": redaction.redaction_type,
        "original_value": redaction.original_value if can_view_original_value else None,
        "masked_value": redaction.masked_value or f"[REDACTED-{redaction.redaction_type}]",
        "visibility_mode": "full",
        "bbox": redaction.bbox,
        "confidence": redaction.confidence,
        "method": redaction.method,
        "status": redaction.status or "pending",
    }


def _record_redaction_review(
    db: Session,
    redaction: Redaction,
    user: User,
    *,
    decision: str,
    action_type: str,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    previous_bbox: Optional[dict] = None,
    new_bbox: Optional[dict] = None,
    previous_type: Optional[str] = None,
    new_type: Optional[str] = None,
    reason: str = "",
) -> RedactionReview:
    review = RedactionReview(
        redaction_id=redaction.id,
        document_id=redaction.document_id,
        page_id=redaction.page_id,
        page_number=redaction.page_number or 1,
        reviewer_id=user.id,
        decision=decision,
        action_type=action_type,
        previous_status=previous_status,
        new_status=new_status,
        previous_bbox=previous_bbox,
        new_bbox=new_bbox,
        previous_type=previous_type,
        new_type=new_type,
        reason=reason,
    )
    db.add(review)
    return review


def _safe_original_filename(filename: Optional[str]) -> str:
    raw = Path(filename or "document").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", raw).strip(" .")
    return cleaned[:120] or "document"


def _extension_for_upload(filename: Optional[str]) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    return ext


def _validate_upload_bytes(content: bytes, ext: str) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB upload limit")
    allowed = ALLOWED_MAGIC.get(ext, ())
    if allowed and not any(content.startswith(prefix) for prefix in allowed):
        raise HTTPException(status_code=400, detail="File content does not match its extension")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise HTTPException(status_code=400, detail="File content does not match its extension")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="File content does not match its extension") from exc


def _scan_uploaded_file(path: str) -> None:
    command_template = os.environ.get("SYNTHETIQ_MALWARE_SCAN_COMMAND", "").strip()
    if not command_template:
        return
    command = shlex.split(command_template) + [path]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        try:
            os.remove(path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="Upload failed malware scan")


async def _store_upload(file: UploadFile, user: User) -> tuple[str, str, str]:
    ext = _extension_for_upload(file.filename)
    source_filename = _safe_original_filename(file.filename)
    storage_key = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{ext}"
    council_prefix = f"council_{user.council_id or 'default'}"
    target_dir = os.path.join(UPLOAD_DIR, council_prefix)
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, storage_key)

    content = await file.read()
    _validate_upload_bytes(content, ext)
    with open(file_path, "wb") as f:
        f.write(content)
    _scan_uploaded_file(file_path)
    return file_path, source_filename, storage_key


# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    init_db()
    db = SessionLocal()
    try:
        council = get_or_create_default_council(db)
        backfill_default_council(db, council)
        if not ENABLE_MULTI_USER_AUTH:
            get_or_create_local_user(db)
    finally:
        db.close()
    print("[startup] Initialising Synthetiq Redact v2.0...")
    
    app.state.ocr_engine = OCREngineManager()
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
    print("[startup] All engines loaded.")


@app.on_event("shutdown")
async def shutdown_event():
    print("[shutdown] Cleaning up...")


# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.post("/api/auth/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("processor"),
    db: Session = Depends(get_db)
):
    """Bootstrap the first user or register users when explicitly enabled."""
    public_register = os.environ.get("ALLOW_PUBLIC_REGISTER", "0") == "1"
    user_count = db.query(User).count()
    if user_count > 0 and not public_register:
        raise HTTPException(status_code=403, detail="Public registration is disabled; ask an admin to create the user.")
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if user_count == 0:
        role = "admin"

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    council = get_or_create_default_council(db)
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
        council_id=council.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_token(user.id, user.email, user.role, user.council_id)
    return {"token": token, "user": {"id": user.id, "email": user.email, "role": user.role}}


@app.post("/api/auth/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Login and get JWT token."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = _ensure_user_council(db, user)
    token = create_token(user.id, user.email, user.role, user.council_id)
    return {"token": token, "user": {"id": user.id, "email": user.email, "role": user.role, "council_id": user.council_id}}


@app.post("/api/auth/logout")
async def logout(user: User = Depends(get_current_user)):
    """Bearer-token logout placeholder for frontend session clearing."""
    return {"message": "Logged out"}


@app.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return {"id": user.id, "email": user.email, "role": user.role, "department": user.department, "council_id": user.council_id}


# ============================================================================
# USERS (Admin only)
# ============================================================================

@app.get("/api/admin/users")
@app.get("/api/users")
async def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """List all users."""
    admin = _ensure_user_council(db, admin)
    users = db.query(User).filter(User.council_id == admin.council_id).all()
    return [{"id": u.id, "email": u.email, "role": u.role, "department": u.department, "is_active": u.is_active, "council_id": u.council_id} for u in users]


@app.post("/api/admin/users")
@app.post("/api/users")
async def create_user(
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("processor"),
    department: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """Create a new user."""
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    admin = _ensure_user_council(db, admin)
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
        department=department or None,
        council_id=admin.council_id,
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.patch("/api/admin/users/{user_id}")
async def update_user(
    user_id: int,
    role: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    active: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """Update a user within the current council."""
    admin = _ensure_user_council(db, admin)
    user = db.query(User).filter(User.id == user_id, User.council_id == admin.council_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if role is not None:
        if role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = role
    if department is not None:
        user.department = department or None
    if active is not None:
        user.is_active = active
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role, "department": user.department, "is_active": user.is_active}


@app.delete("/api/admin/users/{user_id}")
@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """Deactivate a user."""
    admin = _ensure_user_council(db, admin)
    user = db.query(User).filter(User.id == user_id, User.council_id == admin.council_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"message": "User deactivated"}


# ============================================================================
# DOCUMENT UPLOAD & PROCESSING (v2)
# ============================================================================

@app.post("/api/documents")
@app.post("/api/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    translate: str = Form("0"),
    allow_ocr_fallback: str = Form("0"),
    selected_category: str = Form(""),
    category: str = Form(""),
    redaction_profile: str = Form("standard"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a document and start processing."""
    user = _ensure_user_council(db, user)
    file_path, source_filename, storage_key = await _store_upload(file, user)
    effective_category = selected_category or category

    doc = Document(
        council_id=user.council_id,
        uploaded_by=user.id,
        filename=source_filename,
        source_filename=source_filename,
        original_path=file_path,
        storage_key=storage_key,
        status="uploaded",
        selected_category=effective_category or None,
        redaction_profile=redaction_profile,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    log_action(db, doc.id, "uploaded", user_id=user.id, details={
        "filename": source_filename,
        "storage_key": storage_key,
        "uploaded_by": user.email,
    })

    translate_enabled = translate in ("1", "true", "True", "yes", "on")
    fallback_enabled = allow_ocr_fallback in ("1", "true", "True", "yes", "on")
    background_tasks.add_task(_run_pipeline, doc.id, translate_enabled, user.id, fallback_enabled)

    return {"document_id": doc.id, "status": "uploaded", "message": "Document queued for processing"}


async def _run_pipeline(doc_id: int, translate_enabled: bool, user_id: int, allow_fallback_ocr: bool = False) -> None:
    """Background task wrapper for pipeline.

    The OCR/redaction pipeline is CPU/GPU-heavy and mostly synchronous. Run it in
    a worker thread so status polling and image requests stay responsive while a
    document is processing.
    """
    webhook_payload = await asyncio.to_thread(
        _run_pipeline_sync,
        doc_id,
        translate_enabled,
        user_id,
        allow_fallback_ocr,
    )
    if webhook_payload:
        db = SessionLocal()
        try:
            await _emit_webhook(db, "doc.complete", webhook_payload)
        finally:
            db.close()


def _run_pipeline_sync(
    doc_id: int,
    translate_enabled: bool,
    user_id: int,
    allow_fallback_ocr: bool = False,
) -> Optional[Dict[str, Any]]:
    """Synchronous worker-thread body for document processing."""
    db = SessionLocal()
    try:
        asyncio.run(app.state.pipeline.process(
            doc_id,
            db,
            translate_enabled=translate_enabled,
            allow_fallback_ocr=allow_fallback_ocr,
        ))
        
        # Log completion
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            if doc.status in ("error", "failed"):
                log_action(db, doc.id, "processing_failed", user_id=user_id, details={
                    "status": doc.status,
                    "category": doc.category,
                })
                return None
            log_action(db, doc.id, "processing_complete", user_id=user_id, details={
                "status": doc.status,
                "category": doc.category,
                "redaction_count": len(doc.redactions),
            })
            
            # Emit webhook if configured
            return {
                "document_id": doc.id,
                "status": doc.status,
                "category": doc.category,
                "flag_needs_review": doc.flag_needs_review,
            }
        return None
    except Exception as e:
        db.rollback()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "failed"
            doc.needs_review_reason = str(e)[:1000]
            db.commit()
            log_action(db, doc.id, "error", user_id=user_id, details={"error": str(e)})
        return None
    finally:
        db.close()


# ============================================================================
# BATCH PROCESSING (v2)
# ============================================================================

@app.post("/api/batches")
@app.post("/api/batch")
async def create_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    name: str = Form(""),
    redaction_profile: str = Form("standard"),
    translate: str = Form("0"),
    allow_ocr_fallback: str = Form("0"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a batch processing job."""
    user = _ensure_user_council(db, user)
    job_id = str(uuid.uuid4())
    
    fallback_enabled = allow_ocr_fallback in ("1", "true", "True", "yes", "on")

    job = BatchJob(
        id=job_id,
        council_id=user.council_id,
        name=name or f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        status="queued",
        total_docs=len(files),
        config={
            "redaction_profile": redaction_profile,
            "translate": translate == "1",
            "allow_ocr_fallback": fallback_enabled,
        },
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    
    # Save files and create documents
    document_ids = []
    for file in files:
        file_path, source_filename, storage_key = await _store_upload(file, user)
        
        doc = Document(
            council_id=user.council_id,
            uploaded_by=user.id,
            filename=source_filename,
            source_filename=source_filename,
            original_path=file_path,
            storage_key=storage_key,
            status="uploaded",
            redaction_profile=redaction_profile,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        document_ids.append(doc.id)
        job.documents.append(doc)
    
    db.commit()
    
    # Start processing in background
    background_tasks.add_task(_run_batch, job_id, document_ids, translate == "1", user.id, fallback_enabled)
    
    return {"job_id": job_id, "total_docs": len(document_ids), "status": "queued"}


async def _run_batch(
    job_id: str,
    document_ids: List[int],
    translate_enabled: bool,
    user_id: int,
    allow_fallback_ocr: bool = False,
):
    """Process all documents in a batch."""
    db = SessionLocal()
    try:
        job = db.query(BatchJob).filter(BatchJob.id == job_id).first()
        if not job:
            return
        
        job.status = "processing"
        db.commit()
        
        for i, doc_id in enumerate(document_ids):
            try:
                await app.state.pipeline.process(
                    doc_id,
                    db,
                    translate_enabled=translate_enabled,
                    allow_fallback_ocr=allow_fallback_ocr,
                )
                job.processed_docs += 1
            except Exception as e:
                job.failed_docs += 1
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    doc.status = "failed"
                    doc.needs_review_reason = str(e)[:1000]
            
            db.commit()
        
        job.status = "complete"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        
        # Emit webhook
        await _emit_webhook(db, "batch.completed", {
            "job_id": job.id,
            "total": job.total_docs,
            "processed": job.processed_docs,
            "failed": job.failed_docs,
        })
        
    except Exception as e:
        job = db.query(BatchJob).filter(BatchJob.id == job_id).first()
        if job:
            job.status = "failed"
            db.commit()
    finally:
        db.close()


@app.get("/api/batches")
@app.get("/api/batch")
async def list_batches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """List batch jobs for the current council (newest first)."""
    user = _ensure_user_council(db, user)
    jobs = (
        db.query(BatchJob)
        .filter(BatchJob.council_id == user.council_id)
        .order_by(BatchJob.created_at.desc())
        .all()
    )
    return {
        "batches": [
            {
                "id": j.id,
                "name": j.name,
                "status": j.status,
                "total_docs": j.total_docs,
                "processed_docs": j.processed_docs,
                "failed_docs": j.failed_docs,
                "progress_percent": (j.processed_docs / j.total_docs * 100) if j.total_docs > 0 else 0,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ],
    }


@app.get("/api/batches/{job_id}")
@app.get("/api/batch/{job_id}")
async def get_batch_status(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get batch job status and progress."""
    user = _ensure_user_council(db, user)
    job = db.query(BatchJob).filter(BatchJob.id == job_id, BatchJob.council_id == user.council_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "total_docs": job.total_docs,
        "processed_docs": job.processed_docs,
        "failed_docs": job.failed_docs,
        "progress_percent": (job.processed_docs / job.total_docs * 100) if job.total_docs > 0 else 0,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "documents": [
            {"id": d.id, "filename": d.filename, "status": d.status, "flag_needs_review": d.flag_needs_review}
            for d in job.documents
        ],
    }


# ============================================================================
# REVIEW WORKFLOW (v2)
# ============================================================================

@app.get("/api/review-queue")
async def get_review_queue(
    priority: str = Query("all", enum=["urgent", "high", "normal", "all"]),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Get documents needing review, sorted by urgency."""
    user = _ensure_user_council(db, user)
    query = db.query(Document).filter(
        Document.council_id == user.council_id,
        Document.flag_needs_review == True,
        Document.status.in_(["needs_review", "in_review"])
    )
    
    if priority == "urgent":
        query = query.filter(Document.urgency_score >= 0.8)
    elif priority == "high":
        query = query.filter(Document.urgency_score >= 0.5)
    elif priority == "normal":
        query = query.filter(Document.urgency_score < 0.5)
    
    docs = query.order_by(Document.urgency_score.desc(), Document.created_at.asc()).offset(offset).limit(limit).all()
    
    return {
        "total": query.count(),
        "offset": offset,
        "limit": limit,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "category": d.category,
                "urgency_score": d.urgency_score,
                "sentiment": d.sentiment,
                "risk_flags": d.risk_flags,
                "redaction_count": len(d.redactions),
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "reviewer_id": d.reviewer_id,
            }
            for d in docs
        ],
    }


@app.post("/api/documents/{doc_id}/assign")
@app.post("/api/document/{doc_id}/assign-review")
async def assign_review(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Assign a document to the current user for review."""
    doc = _get_document_or_404(db, doc_id, user)
    
    doc.status = "in_review"
    doc.reviewer_id = user.id
    db.commit()
    
    log_action(db, doc.id, "review_assigned", user_id=user.id, details={"reviewer": user.email})
    
    return {"message": "Document assigned for review", "document_id": doc.id}


@app.post("/api/redactions/{redaction_id}/approve")
async def approve_redaction(
    redaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Approve a redaction."""
    user = _ensure_user_council(db, user)
    red = db.query(Redaction).join(Document).filter(
        Redaction.id == redaction_id,
        Document.council_id == user.council_id,
    ).first()
    if not red:
        raise HTTPException(status_code=404, detail="Redaction not found")

    old_status = red.status or "pending"
    red.status = "approved"
    red.reviewer_id = user.id
    red.reviewed_at = datetime.now(timezone.utc)

    _record_redaction_review(
        db,
        red,
        user,
        decision="approved",
        action_type="approve",
        previous_status=old_status,
        new_status=red.status,
        previous_bbox=red.bbox,
        new_bbox=red.bbox,
        previous_type=red.redaction_type,
        new_type=red.redaction_type,
    )
    db.commit()
    
    return {"message": "Redaction approved"}


@app.post("/api/redactions/{redaction_id}/reject")
async def reject_redaction(
    redaction_id: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Reject a redaction (remove it)."""
    user = _ensure_user_council(db, user)
    red = db.query(Redaction).join(Document).filter(
        Redaction.id == redaction_id,
        Document.council_id == user.council_id,
    ).first()
    if not red:
        raise HTTPException(status_code=404, detail="Redaction not found")

    old_status = red.status or "pending"
    red.status = "rejected"
    red.reviewer_id = user.id
    red.reviewed_at = datetime.now(timezone.utc)
    red.review_reason = reason

    _record_redaction_review(
        db,
        red,
        user,
        decision="rejected",
        action_type="remove",
        previous_status=old_status,
        new_status=red.status,
        previous_bbox=red.bbox,
        new_bbox=red.bbox,
        previous_type=red.redaction_type,
        new_type=red.redaction_type,
        reason=reason,
    )
    db.commit()
    
    return {"message": "Redaction rejected"}


@app.post("/api/documents/{doc_id}/redactions")
@app.post("/api/document/{doc_id}/redactions")
@app.post("/api/document/{doc_id}/pages/{page_number}/redactions")
async def create_manual_redaction(
    doc_id: int,
    page_number: int = 1,
    bbox: str = Form(...),
    redaction_type: str = Form("manual"),
    reason: str = Form("Manual redaction"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Create a reviewer-drawn manual redaction box."""
    doc = _get_document_or_404(db, doc_id, user)
    page = _get_page_or_404(db, doc, page_number)
    source_image_path = _page_source_image_path(page)
    normalised_bbox = _normalise_bbox_payload(bbox, source_image_path)
    clean_type = re.sub(r"[^a-z0-9_]+", "_", redaction_type.lower()).strip("_")[:40] or "manual"

    redaction = Redaction(
        document_id=doc.id,
        page_id=page.id,
        page_number=page.page_number,
        redaction_type=clean_type,
        original_value=None,
        masked_value=f"[REDACTED-{clean_type}]",
        bbox=normalised_bbox,
        confidence=1.0,
        method="manual",
        status="pending",
        reviewer_id=user.id,
        review_reason=reason,
    )
    db.add(redaction)
    doc.flag_needs_review = True
    if doc.status not in ("review_approved", "exported"):
        doc.status = "in_review"
    doc.reviewer_id = user.id
    db.commit()
    db.refresh(redaction)

    _record_redaction_review(
        db,
        redaction,
        user,
        decision="created",
        action_type="create",
        previous_status=None,
        new_status=redaction.status,
        previous_bbox=None,
        new_bbox=redaction.bbox,
        previous_type=None,
        new_type=redaction.redaction_type,
        reason=reason,
    )
    log_action(db, doc.id, "manual_redaction_created", user_id=user.id, details={
        "redaction_id": redaction.id,
        "page_number": page.page_number,
        "type": redaction.redaction_type,
    })
    db.commit()

    return _redaction_response(redaction)


@app.post("/api/documents/{doc_id}/redactions/from-text")
@app.post("/api/document/{doc_id}/redactions/from-text")
@app.post("/api/document/{doc_id}/pages/{page_number}/redactions/from-text")
async def create_text_redaction(
    doc_id: int,
    page_number: int = 1,
    selected_text: str = Form(...),
    selection_start: Optional[int] = Form(None),
    selection_end: Optional[int] = Form(None),
    redaction_type: str = Form("manual"),
    reason: str = Form("Text selection redaction"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Create redaction boxes from selected OCR text."""
    doc = _get_document_or_404(db, doc_id, user)
    page = _get_page_or_404(db, doc, page_number)
    ocr = (
        db.query(OCRResult)
        .filter(OCRResult.document_id == doc.id, OCRResult.page_number == page.page_number)
        .order_by(OCRResult.id.desc())
        .first()
    )
    if not ocr or not ocr.words:
        raise HTTPException(status_code=400, detail="OCR text is not available for this document")

    clean_text = ocr.clean_text or ""
    raw_ocr_text = ocr.extracted_text or ""
    text = clean_text or raw_ocr_text
    raw_value = selected_text.strip()
    if len(raw_value) < 2:
        raise HTTPException(status_code=400, detail="Select text before redacting")

    start = selection_start
    end = selection_end
    if start is not None and end is not None:
        start = max(0, min(int(start), len(text)))
        end = max(0, min(int(end), len(text)))
        if end < start:
            start, end = end, start
        value = text[start:end].strip()
        if len(value) < 2:
            raise HTTPException(status_code=400, detail="Selected text is too short")
        leading = len(text[start:end]) - len(text[start:end].lstrip())
        trailing = len(text[start:end]) - len(text[start:end].rstrip())
        start += leading
        end -= trailing
        value = text[start:end]
    else:
        collapsed = re.sub(r"\s+", " ", raw_value)
        flat = re.sub(r"\s+", " ", text)
        found = flat.lower().find(collapsed.lower())
        if found < 0:
            raise HTTPException(status_code=400, detail="Selected text could not be mapped to OCR coordinates")
        prefix = flat[:found]
        start = len(prefix)
        end = start + len(collapsed)
        value = text[start:end]

    clean_type = re.sub(r"[^a-z0-9_]+", "_", redaction_type.lower()).strip("_")[:40] or "manual"
    span = {
        "type": clean_type,
        "start": start,
        "end": end,
        "value": value,
        "confidence": 1.0,
        "method": "text_selection",
    }
    redaction_meta = []
    if clean_text:
        try:
            from redaction_geometry_mapper import RedactionGeometryMapper
            mapper = RedactionGeometryMapper()
            mapped_selection = mapper.map_selected_text(
                value,
                ocr.words,
                int(page.width or 0),
                int(page.height or 0),
                clean_type,
            )
            mapped = [mapped_selection] if mapped_selection else mapper.map(
                clean_text,
                [span],
                ocr.words,
                int(page.width or 0),
                int(page.height or 0),
            )
            for item in mapped:
                if not item or not item.get("bbox"):
                    continue
                redaction_meta.append({
                    "type": clean_type,
                    "value": value,
                    "confidence": item.get("confidence", 1.0),
                    "method": "text_selection",
                    "bboxes": [{"bbox": item["bbox"]["bbox"], "confidence": item.get("confidence", 1.0)}],
                })
        except Exception:
            redaction_meta = []

    if not redaction_meta:
        # Fallback for older records without clean text: map the selected value
        # against the OCR word stream, never clean-text offsets against raw OCR.
        flat_ocr = " ".join(str(word.get("text") or "") for word in (ocr.words or []))
        collapsed = re.sub(r"\s+", " ", raw_value).strip()
        found = flat_ocr.lower().find(collapsed.lower())
        if found < 0:
            raise HTTPException(status_code=400, detail="Selected text could not be mapped to document boxes")
        span = {
            "type": clean_type,
            "start": found,
            "end": found + len(collapsed),
            "value": raw_value,
            "confidence": 1.0,
            "method": "text_selection",
        }
        redaction_meta = app.state.redaction_engine.map_to_bboxes([span], ocr.words)
    if not redaction_meta or not redaction_meta[0].get("bboxes"):
        raise HTTPException(status_code=400, detail="Selected text could not be mapped to document boxes")

    created: list[Redaction] = []
    for red in redaction_meta:
        for box in red.get("bboxes", []):
            redaction = Redaction(
                document_id=doc.id,
                page_id=page.id,
                page_number=page.page_number,
                redaction_type=clean_type,
                original_value=value[:255],
                masked_value=f"[REDACTED-{clean_type}]",
                bbox={"bbox": box["bbox"]},
                confidence=red.get("confidence", 1.0),
                method="text_selection",
                status="pending",
                reviewer_id=user.id,
                review_reason=reason,
            )
            db.add(redaction)
            created.append(redaction)

    doc.flag_needs_review = True
    if doc.status not in ("review_approved", "exported"):
        doc.status = "in_review"
    doc.reviewer_id = user.id
    db.commit()
    for redaction in created:
        db.refresh(redaction)
        _record_redaction_review(
            db,
            redaction,
            user,
            decision="created",
            action_type="create",
            previous_status=None,
            new_status=redaction.status,
            previous_bbox=None,
            new_bbox=redaction.bbox,
            previous_type=None,
            new_type=redaction.redaction_type,
            reason=reason,
        )
    log_action(db, doc.id, "text_redaction_created", user_id=user.id, details={
        "count": len(created),
        "page_number": page.page_number,
        "type": clean_type,
    })
    db.commit()

    return {"redactions": [_redaction_response(redaction) for redaction in created]}


def _bbox_to_aabb(bbox: dict) -> Optional[tuple[float, float, float, float]]:
    """Return (x0, y0, x1, y1) axis-aligned bounds for a redaction bbox."""
    points = _redaction_bbox_points(bbox or {})
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _rect_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union for two (x0, y0, x1, y1) rectangles."""
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


# IoU at or above this against an existing non-rejected box means "already covered".
MODEL_DETECT_DEDUP_IOU = 0.80
MODEL_DETECT_REVIEW_REASON = "Image detector added review candidates"


def _run_model_detection(
    db: Session,
    doc: Document,
    pages: list[DocumentPage],
    user: User,
) -> dict:
    """Run the image detector over the given pages and insert pending candidates."""
    detector = get_detector()
    created: list[Redaction] = []
    skipped_duplicates = 0

    for page in pages:
        source_image_path = _page_source_image_path(page)
        if not source_image_path:
            continue
        try:
            predictions = detector.predict(source_image_path, page.page_number)
        except DetectorUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        existing_rects = [
            rect
            for red in _active_redaction_rows(db, doc, page)
            if (rect := _bbox_to_aabb(red.bbox or {})) is not None
        ]

        for prediction in predictions:
            pred_rect = _bbox_to_aabb(prediction["bbox"])
            if pred_rect is None:
                continue
            if any(_rect_iou(pred_rect, rect) >= MODEL_DETECT_DEDUP_IOU for rect in existing_rects):
                skipped_duplicates += 1
                continue

            redaction = Redaction(
                document_id=doc.id,
                page_id=page.id,
                page_number=page.page_number,
                redaction_type=prediction["redaction_type"],
                original_value="[image model candidate]",
                masked_value=f"[REDACTED-{prediction['redaction_type']}]",
                bbox=prediction["bbox"],
                confidence=prediction["confidence"],
                method=prediction["method"],
                status="pending",
            )
            db.add(redaction)
            created.append(redaction)
            # Treat the freshly added box as existing so later boxes dedup against it.
            existing_rects.append(pred_rect)

    if created:
        doc.flag_needs_review = True
        if doc.status not in ("review_approved", "exported"):
            doc.status = "in_review"
        existing_reason = doc.needs_review_reason or ""
        if MODEL_DETECT_REVIEW_REASON not in existing_reason:
            doc.needs_review_reason = (
                f"{existing_reason}; {MODEL_DETECT_REVIEW_REASON}".strip("; ")
                if existing_reason
                else MODEL_DETECT_REVIEW_REASON
            )

    db.commit()
    for redaction in created:
        db.refresh(redaction)

    log_action(db, doc.id, "model_redaction_detection", user_id=user.id, details={
        "created_count": len(created),
        "skipped_duplicate_count": skipped_duplicates,
        "pages": [page.page_number for page in pages],
    })

    return {
        "created_count": len(created),
        "skipped_duplicate_count": skipped_duplicates,
        "redactions": [_redaction_response(redaction) for redaction in created],
    }


@app.post("/api/documents/{doc_id}/pages/{page_number}/redactions/model-detect")
@app.post("/api/document/{doc_id}/pages/{page_number}/redactions/model-detect")
async def model_detect_page_redactions(
    doc_id: int,
    page_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Run the image redaction detector on a single page (review-assist only)."""
    doc = _get_document_or_404(db, doc_id, user)
    page = _get_page_or_404(db, doc, page_number)
    return _run_model_detection(db, doc, [page], user)


@app.post("/api/documents/{doc_id}/redactions/model-detect")
@app.post("/api/document/{doc_id}/redactions/model-detect")
async def model_detect_document_redactions(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Run the image redaction detector across all pages (review-assist only)."""
    doc = _get_document_or_404(db, doc_id, user)
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        raise HTTPException(status_code=404, detail="No rendered pages are available")
    return _run_model_detection(db, doc, pages, user)


@app.post("/api/redactions/{redaction_id}/modify")
async def modify_redaction(
    redaction_id: int,
    new_bbox: str = Form(...),  # JSON string
    new_type: str = Form(""),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Modify a redaction's bbox or type."""
    user = _ensure_user_council(db, user)
    red = db.query(Redaction).join(Document).filter(
        Redaction.id == redaction_id,
        Document.council_id == user.council_id,
    ).first()
    if not red:
        raise HTTPException(status_code=404, detail="Redaction not found")

    doc = db.query(Document).filter(Document.id == red.document_id).first()
    page = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == red.document_id, DocumentPage.page_number == (red.page_number or 1))
        .first()
    )
    old_bbox = red.bbox
    old_type = red.redaction_type
    old_status = red.status or "pending"

    red.bbox = _normalise_bbox_payload(new_bbox, _page_source_image_path(page) if page else _redaction_source_image_path(doc))
    if new_type:
        red.redaction_type = re.sub(r"[^a-z0-9_]+", "_", new_type.lower()).strip("_")[:40] or old_type
    red.status = "modified"
    red.reviewer_id = user.id
    red.reviewed_at = datetime.now(timezone.utc)

    _record_redaction_review(
        db,
        red,
        user,
        decision="modified",
        action_type="modify",
        previous_status=old_status,
        new_status=red.status,
        previous_bbox=old_bbox,
        new_bbox=red.bbox,
        previous_type=old_type,
        new_type=red.redaction_type,
        reason=reason,
    )
    db.commit()
    
    return {"message": "Redaction modified", "redaction": _redaction_response(red)}


@app.post("/api/document/{doc_id}/approve-all")
async def approve_all_redactions(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Approve all pending redactions for a document."""
    doc = _get_document_or_404(db, doc_id, user)
    
    reds = db.query(Redaction).filter(
        Redaction.document_id == doc_id,
        Redaction.status == "pending"
    ).all()
    
    for red in reds:
        old_status = red.status or "pending"
        red.status = "approved"
        red.reviewer_id = user.id
        red.reviewed_at = datetime.now(timezone.utc)
        _record_redaction_review(
            db,
            red,
            user,
            decision="approved",
            action_type="approve",
            previous_status=old_status,
            new_status=red.status,
            previous_bbox=red.bbox,
            new_bbox=red.bbox,
            previous_type=red.redaction_type,
            new_type=red.redaction_type,
            reason="Approve all",
        )
    
    if doc.status not in ("review_approved", "exported"):
        doc.status = "in_review"
    doc.flag_needs_review = True
    doc.reviewer_id = user.id
    doc.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    
    log_action(db, doc.id, "all_redactions_approved", user_id=user.id, details={
        "approved_count": len(reds)
    })
    
    return {"message": f"Approved {len(reds)} redactions", "approved_count": len(reds)}


# ============================================================================
# WEBHOOKS (v2)
# ============================================================================

async def _emit_webhook(db: Session, event: str, payload: dict):
    """Emit webhook event to all configured webhooks."""
    if not WEBHOOKS_ENABLED:
        return
    webhooks = db.query(Webhook).filter(
        Webhook.active == True,
    ).all()
    
    for wh in webhooks:
        if wh.events and event not in wh.events:
            continue
        
        try:
            import httpx
            headers = {"Content-Type": "application/json"}
            if wh.secret:
                signature = hmac.new(
                    wh.secret.encode(),
                    json.dumps(payload, sort_keys=True).encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-Webhook-Signature"] = signature
            
            async with httpx.AsyncClient() as client:
                await client.post(wh.url, json=payload, headers=headers, timeout=10.0)
        except Exception as e:
            print(f"[webhook] Failed to emit to {wh.url}: {e}")


@app.post("/api/webhooks")
async def create_webhook(
    url: str = Form(...),
    events: str = Form(...),  # JSON array
    secret: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["admin"]))
):
    """Create a webhook."""
    if not WEBHOOKS_ENABLED:
        raise HTTPException(status_code=403, detail="Webhooks are disabled for the pilot baseline")
    events_list = json.loads(events)
    
    wh = Webhook(
        url=url,
        events=events_list,
        secret=secret or None,
        created_by=user.id,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    
    return {"id": wh.id, "url": wh.url, "events": wh.events, "active": wh.active}


@app.get("/api/webhooks")
async def list_webhooks(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["admin"]))
):
    """List all webhooks."""
    if not WEBHOOKS_ENABLED:
        return []
    webhooks = db.query(Webhook).all()
    return [{"id": w.id, "url": w.url, "events": w.events, "active": w.active} for w in webhooks]


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["admin"]))
):
    """Delete a webhook."""
    if not WEBHOOKS_ENABLED:
        raise HTTPException(status_code=403, detail="Webhooks are disabled for the pilot baseline")
    wh = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(wh)
    db.commit()
    return {"message": "Webhook deleted"}


# ============================================================================
# ANALYTICS (v2)
# ============================================================================

@app.get("/api/analytics/dashboard")
async def get_dashboard_analytics(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get analytics dashboard data."""
    user = _ensure_user_council(db, user)
    from_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Total documents
    base_filter = (
        Document.council_id == user.council_id,
        Document.created_at >= from_date,
    )
    total_docs = db.query(Document).filter(*base_filter).count()
    
    # By status
    complete_docs = db.query(Document).filter(
        *base_filter,
        Document.status == "complete"
    ).count()
    review_docs = db.query(Document).filter(
        *base_filter,
        Document.status.in_(["needs_review", "in_review"])
    ).count()
    error_docs = db.query(Document).filter(
        *base_filter,
        Document.status.in_(["error", "failed"])
    ).count()
    
    # Auto-approval rate
    total_processed = complete_docs + review_docs
    auto_approval_rate = (complete_docs / total_processed * 100) if total_processed > 0 else 0
    
    # Redaction stats
    total_redactions = db.query(Redaction).join(Document).filter(
        *base_filter
    ).count()
    
    approved_redactions = db.query(Redaction).join(Document).filter(
        *base_filter,
        Redaction.status == "approved"
    ).count()
    
    rejected_redactions = db.query(Redaction).join(Document).filter(
        *base_filter,
        Redaction.status == "rejected"
    ).count()
    
    # Safeguarding alerts
    safeguarding_docs = db.query(Document).filter(
        *base_filter,
        Document.risk_flags.isnot(None)
    ).count()
    
    # By category
    category_stats = {}
    for cat in ["housing_repairs", "council_tax", "parking", "complaint", 
                "waste", "adult_social_care", "children_safeguarding", "foi_legal"]:
        count = db.query(Document).filter(
            *base_filter,
            Document.category == cat
        ).count()
        if count > 0:
            category_stats[cat] = count
    
    # Average processing time estimate (based on audit logs)
    audit_entries = db.query(AuditLog).filter(
        AuditLog.council_id == user.council_id,
        AuditLog.timestamp >= from_date,
        AuditLog.action.in_(["uploaded", "processing_complete"])
    ).all()
    
    return {
        "period_days": days,
        "total_documents": total_docs,
        "complete": complete_docs,
        "needs_review": review_docs,
        "errors": error_docs,
        "auto_approval_rate": round(auto_approval_rate, 1),
        "total_redactions": total_redactions,
        "approved_redactions": approved_redactions,
        "rejected_redactions": rejected_redactions,
        "safeguarding_alerts": safeguarding_docs,
        "by_category": category_stats,
        "estimated_hours_saved": round(total_docs * 0.33, 1),  # ~20 min per doc manual
    }


# ============================================================================
# LEGACY ENDPOINTS (Keep for backwards compatibility)
# ============================================================================

@app.get("/api/documents/{doc_id}/progress")
@app.get("/api/progress/{doc_id}")
async def progress_stream(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE stream of document processing progress."""
    authorized_doc = _get_document_or_404(db, doc_id, user)
    authorized_council_id = authorized_doc.council_id

    async def event_generator():
        last_status = None
        while True:
            db_local = SessionLocal()
            try:
                doc = db_local.query(Document).filter(
                    Document.id == doc_id,
                    Document.council_id == authorized_council_id,
                ).first()
                if not doc:
                    yield f"data: {json.dumps({'status': 'error', 'message': 'Document not found', 'percent': 0})}\n\n"
                    break
                if doc.status != last_status:
                    last_status = doc.status
                    percent = STATUS_PERCENT.get(doc.status, 0)
                    message = STATUS_MESSAGES.get(doc.status, "Processing...")
                    payload = json.dumps({
                        "status": doc.status,
                        "message": message,
                        "percent": percent,
                        "engine_used": doc.engine_used,
                        "engine_status": _engine_status_payload(doc),
                    })
                    yield f"data: {payload}\n\n"
                if doc.status in ("complete", "error", "failed", "needs_review", "review_approved"):
                    break
            finally:
                db_local.close()
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
    "in_review": 100,
    "review_approved": 100,
    "error": 100,
    "failed": 100,
}

STATUS_MESSAGES = {
    "uploaded": "Document uploaded...",
    "preprocessing": "Preprocessing document...",
    "ocr": "Extracting text with OCR...",
    "redaction": "Detecting and redacting sensitive data...",
    "translation": "Translating non-English text...",
    "classification": "Classifying document...",
    "routing": "Computing urgency and routing...",
    "complete": "Processing complete!",
    "needs_review": "Processing complete — flagged for review",
    "in_review": "Under human review...",
    "review_approved": "Review complete — approved",
    "error": "Processing failed",
    "failed": "Processing failed",
}


def _engine_status_payload(doc: Document) -> dict:
    """Human-readable processing path for the review UI."""
    engine_used = doc.engine_used or ""
    handwriting_backend = doc.handwriting_backend or ""
    if "synthetiq_redact_v3_glm_geometry" in engine_used:
        return {
            "mode": "main",
            "label": "Synthetiq Redact v3",
            "detail": "GLM OCR text with value-level geometry mapping",
            "engine_used": engine_used,
            "handwriting_backend": handwriting_backend,
        }
    if "fallback_easyocr_geometry_config_off" in engine_used:
        return {
            "mode": "fallback",
            "label": "Fallback",
            "detail": "Synthetiq Redact v3 is disabled; OCR word-box fallback used",
            "engine_used": engine_used,
            "handwriting_backend": handwriting_backend,
        }
    if "fallback_easyocr_geometry" in engine_used:
        return {
            "mode": "fallback",
            "label": "Fallback",
            "detail": "Synthetiq Redact v3/GLM was unavailable; OCR word-box fallback used",
            "engine_used": engine_used,
            "handwriting_backend": handwriting_backend,
        }
    if "synthetiq_redact_v3_unavailable" in engine_used or "synthetiq_redact_v3_config_off" in engine_used:
        return {
            "mode": "blocked",
            "label": "v3 unavailable",
            "detail": doc.needs_review_reason or "Synthetiq Redact v3 could not run and fallback is off",
            "engine_used": engine_used,
            "handwriting_backend": handwriting_backend,
        }
    if doc.status in {"uploaded", "preprocessing", "ocr", "redaction"}:
        return {
            "mode": "pending",
            "label": "Selecting engine",
            "detail": "Processing path will appear here once redaction starts",
            "engine_used": engine_used,
            "handwriting_backend": handwriting_backend,
        }
    return {
        "mode": "unknown",
        "label": "Unknown path",
        "detail": "No processing path was recorded for this document",
        "engine_used": engine_used,
        "handwriting_backend": handwriting_backend,
    }


@app.get("/api/documents/{doc_id}")
@app.get("/api/document/{doc_id}")
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get full document details with nested OCR and redactions."""
    _get_document_or_404(db, doc_id, user)
    doc = (
        db.query(Document)
        .options(
            joinedload(Document.pages),
            joinedload(Document.ocr_results),
            joinedload(Document.redactions),
            joinedload(Document.audit_logs),
        )
        .filter(Document.id == doc_id, Document.council_id == user.council_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Apply role-based redaction visibility
    role = user.role
    can_view_original_value = role in {"admin", "reviewer", "dpo", "auditor"}
    
    ocr_data = None
    if doc.ocr_results:
        ocr = sorted(doc.ocr_results, key=lambda item: (item.page_number or 1, item.id))[0]
        ocr_data = _ocr_response(ocr)

    redactions_data = []
    for r in doc.redactions:
        # Apply role-based partial masking
        from redaction import get_role_policy, PARTIAL_REDACTION_POLICIES
        mode = get_role_policy(role, r.redaction_type)
        masked_value = r.masked_value or r.original_value
        
        if mode == "partial" and r.original_value:
            policy = PARTIAL_REDACTION_POLICIES.get(r.redaction_type, {})
            mask_fn = policy.get("mask")
            if mask_fn:
                masked_value = mask_fn(r.original_value)
        elif mode == "full":
            masked_value = f"[REDACTED-{r.redaction_type}]"
        
        item = _redaction_response(r, can_view_original_value=can_view_original_value)
        item["masked_value"] = masked_value
        item["visibility_mode"] = mode
        redactions_data.append(item)

    pages_data = [
        _page_response(db, doc, page, can_view_original_value=can_view_original_value)
        for page in sorted(doc.pages or [], key=lambda item: item.page_number)
    ]

    return {
        "id": doc.id,
        "filename": doc.filename,
        "source_filename": doc.source_filename,
        "has_original": bool(doc.original_path),
        "has_redacted": bool(doc.redacted_path),
        "has_mask": bool(doc.mask_path),
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
        "confidence_summary": doc.confidence_summary,
        "needs_review_reason": doc.needs_review_reason,
        "retention_due_at": doc.retention_due_at.isoformat() if doc.retention_due_at else None,
        "selected_category": doc.selected_category,
        "redaction_profile": doc.redaction_profile,
        "exports": {
            "text": bool(doc.text_export_path),
            "clean": bool(doc.transcription_clean_path),
            "json": bool(doc.transcription_json_path),
            "docx": bool(doc.redacted_docx_path),
        },
        "handwriting_backend": doc.handwriting_backend,
        "handwriting_confidence": doc.handwriting_confidence,
        "handwriting_review_reason": doc.handwriting_review_reason,
        "engine_used": doc.engine_used,
        "engine_status": _engine_status_payload(doc),
        "layout_regions": doc.layout_regions,
        "reviewer_id": doc.reviewer_id,
        "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        "review_notes": doc.review_notes,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "page_count": len(pages_data) or 1,
        "pages": pages_data,
        "ocr": ocr_data,
        "redactions": redactions_data,
        "batch_jobs": [{"id": b.id, "name": b.name} for b in doc.batch_jobs],
    }


@app.get("/api/document/{doc_id}/pages")
@app.get("/api/documents/{doc_id}/pages")
async def get_document_pages(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Return page summaries for a document."""
    doc = _get_document_or_404(db, doc_id, user)
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    can_view_original_value = user.role in {"admin", "reviewer", "dpo", "auditor"}
    return {
        "document_id": doc.id,
        "page_count": len(pages),
        "pages": [_page_response(db, doc, page, can_view_original_value) for page in pages],
    }


@app.get("/api/document/{doc_id}/pages/{page_number}")
@app.get("/api/documents/{doc_id}/pages/{page_number}")
async def get_document_page(
    doc_id: int,
    page_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Return one page with page-scoped OCR, redactions, and vision warnings."""
    doc = _get_document_or_404(db, doc_id, user)
    page = _get_page_or_404(db, doc, page_number)
    can_view_original_value = user.role in {"admin", "reviewer", "dpo", "auditor"}
    return _page_response(db, doc, page, can_view_original_value)


@app.get("/api/document/{doc_id}/pages/{page_number}/image")
@app.get("/api/documents/{doc_id}/pages/{page_number}/image")
async def get_document_page_image(
    doc_id: int,
    page_number: int,
    type: str = Query("original", enum=["original", "redacted", "mask"]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Serve a page-specific original, redacted, or mask image."""
    doc = _get_document_or_404(db, doc_id, user)
    page = _get_page_or_404(db, doc, page_number)

    if type == "original":
        path = _page_source_image_path(page)
    elif type == "redacted":
        path = _write_burned_page_image(db, doc, page, overlay=False)
    elif type == "mask":
        path = _write_burned_page_image(db, doc, page, overlay=True)
    else:
        raise HTTPException(status_code=400, detail="Invalid image type")

    return _safe_file_response(path)


@app.get("/api/documents/{doc_id}/image")
@app.get("/api/document/{doc_id}/image")
async def get_document_image(
    doc_id: int,
    type: str = Query("original", enum=["original", "redacted", "mask"]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Serve original, redacted, or mask image."""
    doc = _get_document_or_404(db, doc_id, user)

    if type == "original":
        path = _redaction_source_image_path(doc) or doc.original_path
    elif type == "redacted":
        path = _write_burned_redaction_image(db, doc, overlay=False)
    elif type == "mask":
        path = _write_burned_redaction_image(db, doc, overlay=True)
    else:
        raise HTTPException(status_code=400, detail="Invalid image type")

    return _safe_file_response(path)


@app.get("/api/documents/{doc_id}/original-file")
@app.get("/api/document/{doc_id}/original-file")
async def get_original_document_file(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Download the original uploaded file for library/archive workflows."""
    doc = _get_document_or_404(db, doc_id, user)
    original_name = Path(doc.source_filename or doc.filename or f"document_{doc_id}_original").name
    return _safe_file_response(doc.original_path, filename=original_name)


@app.get("/api/documents/{doc_id}/export")
@app.get("/api/document/{doc_id}/export")
async def export_document(
    doc_id: int,
    type: str = Query("text", enum=["text", "clean", "json", "docx", "pdf", "txt"]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Download a processed document export."""
    doc = _get_document_or_404(db, doc_id, user)
    normalized_type = "text" if type == "txt" else type
    if normalized_type == "pdf":
        pdf_path = _write_burned_redaction_pdf(db, doc)
        verification = _verify_burned_pdf_export(db, doc, pdf_path)
        if not verification["passed"]:
            failed = [check for check in verification["checks"] if not check["passed"]]
            raise HTTPException(status_code=409, detail={
                "message": "Burned PDF verification failed. Download blocked.",
                "checks": failed,
            })
        response = _safe_file_response(
            pdf_path,
            media_type="application/pdf",
            filename=f"document_{doc_id}_redacted.pdf",
        )
        doc.status = "exported" if doc.status == "review_approved" else doc.status
        db.commit()
        log_action(db, doc.id, "exported", user_id=user.id, details={"type": normalized_type})
        return response

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
    path, media_type, filename = export_map[normalized_type]
    response = _safe_file_response(path, media_type=media_type, filename=filename)
    doc.status = "exported" if doc.status == "review_approved" else doc.status
    db.commit()
    log_action(db, doc.id, "exported", user_id=user.id, details={"type": normalized_type})
    return response


def _unique_export_path(folder: Path, filename: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(2, 1000):
        candidate = folder / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Could not create a unique export filename.")


def _resolve_download_folder(folder_path: str | None) -> Path:
    if not folder_path or folder_path.strip().lower() in {"downloads", "default"}:
        return Path.home() / "Downloads"
    folder = Path(folder_path).expanduser()
    if not folder.is_absolute():
        raise HTTPException(status_code=400, detail="Use an absolute folder path.")
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail="Export path must be a folder.")
    return folder


@app.post("/api/documents/{doc_id}/export-to-folder")
@app.post("/api/document/{doc_id}/export-to-folder")
async def export_document_to_folder(
    doc_id: int,
    type: str = Form("pdf"),
    folder_path: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Copy a processed export to a local folder for the desktop app."""
    doc = _get_document_or_404(db, doc_id, user)
    normalized_type = "text" if type == "txt" else type
    folder = _resolve_download_folder(folder_path)

    if normalized_type == "original":
        raw_path = doc.original_path
        if not raw_path:
            raise HTTPException(status_code=404, detail="Original file is not available.")
        source_path = Path(raw_path)
        filename = Path(doc.source_filename or doc.filename or source_path.name).name
    elif normalized_type == "pdf":
        source_path = Path(_write_burned_redaction_pdf(db, doc))
        verification = _verify_burned_pdf_export(db, doc, str(source_path))
        if not verification["passed"]:
            failed = [check for check in verification["checks"] if not check["passed"]]
            raise HTTPException(status_code=409, detail={
                "message": "Burned PDF verification failed. Export blocked.",
                "checks": failed,
            })
        filename = f"document_{doc_id}_redacted.pdf"
    else:
        export_map = {
            "text": (doc.text_export_path, f"document_{doc_id}_redacted.txt"),
            "clean": (doc.transcription_clean_path, f"document_{doc_id}_clean_transcription.txt"),
            "json": (doc.transcription_json_path, f"document_{doc_id}_transcription.json"),
            "docx": (doc.redacted_docx_path, f"document_{doc_id}_redacted.docx"),
        }
        if normalized_type not in export_map:
            raise HTTPException(status_code=400, detail="Unsupported export type.")
        raw_path, filename = export_map[normalized_type]
        if not raw_path:
            raise HTTPException(status_code=404, detail="Requested export is not available.")
        source_path = Path(raw_path)

    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Requested export is not available.")

    target_path = _unique_export_path(folder, filename)
    shutil.copy2(source_path, target_path)
    doc.status = "exported" if doc.status == "review_approved" else doc.status
    db.commit()
    log_action(db, doc.id, "exported_to_folder", user_id=user.id, details={
        "type": normalized_type,
        "path": str(target_path),
    })
    return {
        "path": str(target_path),
        "folder": str(folder),
        "filename": target_path.name,
        "type": normalized_type,
    }


@app.post("/api/documents/{doc_id}/verify-export")
@app.post("/api/document/{doc_id}/verify-export")
async def verify_export(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Build and verify the safe burned PDF without downloading it."""
    doc = _get_document_or_404(db, doc_id, user)
    pdf_path = _write_burned_redaction_pdf(db, doc)
    verification = _verify_burned_pdf_export(db, doc, pdf_path)
    log_action(db, doc.id, "export_verified", user_id=user.id, details={
        "passed": verification["passed"],
        "checks": verification["checks"],
    })
    return verification


@app.post("/api/documents/{doc_id}/approve-release")
@app.post("/api/document/{doc_id}/approve")
async def approve_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Approve a processed document."""
    doc = _get_document_or_404(db, doc_id, user)
    doc.status = "review_approved"
    doc.flag_needs_review = False
    doc.reviewer_id = user.id
    doc.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, doc.id, "release_approved", user_id=user.id)
    return {"message": "Document approved for release", "status": "review_approved"}


@app.post("/api/document/{doc_id}/review")
async def review_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Flag a document for human review."""
    doc = _get_document_or_404(db, doc_id, user)
    doc.status = "needs_review"
    doc.flag_needs_review = True
    db.commit()
    log_action(db, doc.id, "flagged_for_review", user_id=user.id)
    return {"message": "Document flagged for review", "status": "needs_review"}


@app.get("/api/documents/{doc_id}/history")
@app.get("/api/document/{doc_id}/history")
async def get_document_history(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Return redaction edit history for a document."""
    doc = _get_document_or_404(db, doc_id, user)
    entries = (
        db.query(RedactionReview)
        .filter(RedactionReview.document_id == doc.id)
        .order_by(RedactionReview.reviewed_at.desc(), RedactionReview.id.desc())
        .limit(100)
        .all()
    )
    return {
        "document_id": doc.id,
        "undo_enabled": doc.status not in ("review_approved", "exported"),
        "entries": [
            {
                "id": entry.id,
                "redaction_id": entry.redaction_id,
                "page_id": entry.page_id,
                "page_number": entry.page_number or 1,
                "action_type": entry.action_type or entry.decision,
                "decision": entry.decision,
                "previous_status": entry.previous_status,
                "new_status": entry.new_status,
                "previous_bbox": entry.previous_bbox,
                "new_bbox": entry.new_bbox,
                "previous_type": entry.previous_type,
                "new_type": entry.new_type,
                "reason": entry.reason,
                "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
            }
            for entry in entries
        ],
    }


@app.post("/api/documents/{doc_id}/undo-last")
@app.post("/api/document/{doc_id}/undo-last")
async def undo_last_redaction_action(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Undo the latest reversible redaction action on a document."""
    doc = _get_document_or_404(db, doc_id, user)
    if doc.status in ("review_approved", "exported"):
        raise HTTPException(status_code=409, detail="Undo is disabled after final release approval or export")

    undo_entries = (
        db.query(RedactionReview)
        .filter(RedactionReview.document_id == doc.id, RedactionReview.action_type == "undo")
        .all()
    )
    undone_review_ids = set()
    for entry in undo_entries:
        match = re.search(r"Undo review (\d+)", entry.reason or "")
        if match:
            undone_review_ids.add(int(match.group(1)))

    candidates = (
        db.query(RedactionReview)
        .filter(
            RedactionReview.document_id == doc.id,
            RedactionReview.action_type.in_(["create", "modify", "remove", "approve"]),
        )
        .order_by(RedactionReview.reviewed_at.desc(), RedactionReview.id.desc())
        .all()
    )
    target_review = next((entry for entry in candidates if entry.id not in undone_review_ids), None)
    if not target_review:
        raise HTTPException(status_code=404, detail="No reversible redaction action found")

    redaction = db.query(Redaction).filter(
        Redaction.id == target_review.redaction_id,
        Redaction.document_id == doc.id,
    ).first()
    if not redaction:
        raise HTTPException(status_code=404, detail="Redaction no longer exists")

    previous_status = redaction.status
    previous_bbox = redaction.bbox
    previous_type = redaction.redaction_type

    if target_review.action_type == "create":
        redaction.status = "rejected"
    elif target_review.action_type == "modify":
        if target_review.previous_bbox is not None:
            redaction.bbox = target_review.previous_bbox
        if target_review.previous_type:
            redaction.redaction_type = target_review.previous_type
        if target_review.previous_status:
            redaction.status = target_review.previous_status
    elif target_review.action_type in {"remove", "approve"}:
        redaction.status = target_review.previous_status or "pending"
    else:
        raise HTTPException(status_code=400, detail="Action cannot be undone")

    redaction.reviewer_id = user.id
    redaction.reviewed_at = datetime.now(timezone.utc)
    doc.status = "in_review"
    doc.flag_needs_review = True
    doc.reviewer_id = user.id

    _record_redaction_review(
        db,
        redaction,
        user,
        decision="undo",
        action_type="undo",
        previous_status=previous_status,
        new_status=redaction.status,
        previous_bbox=previous_bbox,
        new_bbox=redaction.bbox,
        previous_type=previous_type,
        new_type=redaction.redaction_type,
        reason=f"Undo review {target_review.id}",
    )
    log_action(db, doc.id, "redaction_undo", user_id=user.id, details={
        "undone_review_id": target_review.id,
        "redaction_id": redaction.id,
        "page_number": redaction.page_number or 1,
    })
    db.commit()
    return {"message": "Undo applied", "redaction": _redaction_response(redaction)}


@app.get("/api/documents")
async def list_documents(
    status: str = Query("all"),
    category: str = Query(""),
    search: str = Query(""),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """List all documents with summary fields and filtering."""
    user = _ensure_user_council(db, user)
    query = db.query(Document).filter(Document.council_id == user.council_id)
    
    if status != "all":
        query = query.filter(Document.status == status)
    if category:
        query = query.filter(Document.category == category)
    if search:
        query = query.filter(Document.filename.contains(search))
    
    total = query.count()
    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "documents": [
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
                "redaction_count": len(d.redactions),
                "engine_used": d.engine_used,
                "engine_status": _engine_status_payload(d),
                "needs_review_reason": d.needs_review_reason,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in docs
        ],
    }


@app.get("/api/departments")
async def list_departments(user: User = Depends(get_current_user)):
    """List department mappings."""
    return {"departments": DEPARTMENTS}


@app.get("/api/audit/documents/{doc_id}")
async def get_document_audit(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["admin", "auditor", "dpo", "reviewer"]))
):
    """Return the document audit trail and chain verification result."""
    doc = _get_document_or_404(db, doc_id, user)
    entries = db.query(AuditLog).filter(
        AuditLog.document_id == doc.id,
    ).order_by(AuditLog.timestamp.asc()).all()
    return {
        "document_id": doc.id,
        "chain_valid": verify_audit_chain(db, doc.id),
        "entries": [
            {
                "id": entry.id,
                "action": entry.action,
                "user_id": entry.user_id,
                "details": entry.details or {},
                "previous_hash": entry.previous_hash,
                "chain_hash": entry.chain_hash,
                "signature": entry.signature,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            }
            for entry in entries
        ],
    }


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
        "version": "2.0.0",
        "local_mode": not ENABLE_MULTI_USER_AUTH,
        "models": model_status,
    }
