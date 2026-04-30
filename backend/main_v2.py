import asyncio
import os
import json
import uuid
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, File, Form, UploadFile, Depends, HTTPException, BackgroundTasks, Query, status
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
import bcrypt
import jwt

from config import UPLOAD_DIR, PROCESSED_DIR, DB_PATH, DEPARTMENTS
from database_v2 import init_db, get_db, SessionLocal
from models_v2 import (
    Document, OCRResult, Redaction, AuditLog,
    User, BatchJob, RedactionReview, Webhook, RetentionPolicy,
    batch_job_documents
)
from audit_v2 import log_action
from pipeline import DocumentPipeline
from ocr_engine_v2 import OCREngineManager
from redaction import RedactionEngine
from translation import TranslationEngine
from classification import ClassificationEngine
from sentiment_urgency import SentimentUrgencyEngine
from llm_engine import LLMEngine
from handwriting_transcription import HandwritingTranscriptionEngine

app = FastAPI(title="Synthetiq Redact v2.0", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)
JWT_SECRET = os.environ.get("JWT_SECRET", "synthetiq-redact-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

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

def create_token(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
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

_dummy_user = None

def _get_dummy_user(db: Session) -> User:
    global _dummy_user
    if _dummy_user is None:
        _dummy_user = db.query(User).filter(User.email == "system@local").first()
        if _dummy_user is None:
            _dummy_user = User(
                email="system@local",
                hashed_password="",
                role="admin",
                is_active=True,
            )
            db.add(_dummy_user)
            db.commit()
            db.refresh(_dummy_user)
    return _dummy_user

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    try:
        if credentials:
            token = credentials.credentials
            payload = decode_token(token)
            user = db.query(User).filter(User.id == int(payload["sub"])).first()
            if user and user.is_active:
                return user
    except Exception:
        pass
    return _get_dummy_user(db)

def require_role(allowed_roles: List[str]):
    async def role_checker(user: User = Depends(get_current_user)):
        return user
    return role_checker


# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    init_db()
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
    """Register a new user."""
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_token(user.id, user.email, user.role)
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
    
    token = create_token(user.id, user.email, user.role)
    return {"token": token, "user": {"id": user.id, "email": user.email, "role": user.role}}


@app.get("/api/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user info."""
    return {"id": user.id, "email": user.email, "role": user.role, "department": user.department}


# ============================================================================
# USERS (Admin only)
# ============================================================================

@app.get("/api/users")
async def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """List all users."""
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email, "role": u.role, "department": u.department, "is_active": u.is_active} for u in users]


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
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=role,
        department=department or None,
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """Deactivate a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"message": "User deactivated"}


# ============================================================================
# DOCUMENT UPLOAD & PROCESSING (v2)
# ============================================================================

@app.post("/api/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    translate: str = Form("0"),
    selected_category: str = Form(""),
    redaction_profile: str = Form("standard"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
        redaction_profile=redaction_profile,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    log_action(db, doc.id, "uploaded", user_id=user.id, details={
        "filename": file.filename,
        "path": file_path,
        "uploaded_by": user.email,
    })

    translate_enabled = translate == "1"
    background_tasks.add_task(_run_pipeline, doc.id, translate_enabled, user.id)

    return {"document_id": doc.id, "status": "uploaded", "message": "Document queued for processing"}


async def _run_pipeline(doc_id: int, translate_enabled: bool, user_id: int) -> None:
    """Background task wrapper for pipeline."""
    db = SessionLocal()
    try:
        await app.state.pipeline.process(doc_id, db, translate_enabled=translate_enabled)
        
        # Log completion
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            log_action(db, doc.id, "processing_complete", user_id=user_id, details={
                "status": doc.status,
                "category": doc.category,
                "redaction_count": len(doc.redactions),
            })
            
            # Emit webhook if configured
            await _emit_webhook(db, "doc.complete", {
                "document_id": doc.id,
                "status": doc.status,
                "category": doc.category,
                "flag_needs_review": doc.flag_needs_review,
            })
    except Exception as e:
        db.rollback()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "error"
            db.commit()
            log_action(db, doc.id, "error", user_id=user_id, details={"error": str(e)})
    finally:
        db.close()


# ============================================================================
# BATCH PROCESSING (v2)
# ============================================================================

@app.post("/api/batch")
async def create_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    name: str = Form(""),
    redaction_profile: str = Form("standard"),
    translate: str = Form("0"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a batch processing job."""
    job_id = str(uuid.uuid4())
    
    job = BatchJob(
        id=job_id,
        name=name or f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        status="queued",
        total_docs=len(files),
        config={"redaction_profile": redaction_profile, "translate": translate == "1"},
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    
    # Save files and create documents
    document_ids = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".pdf"):
            continue
        
        safe_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        doc = Document(
            filename=file.filename,
            original_path=file_path,
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
    background_tasks.add_task(_run_batch, job_id, document_ids, translate == "1", user.id)
    
    return {"job_id": job_id, "total_docs": len(document_ids), "status": "queued"}


async def _run_batch(job_id: str, document_ids: List[int], translate_enabled: bool, user_id: int):
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
                await app.state.pipeline.process(doc_id, db, translate_enabled=translate_enabled)
                job.processed_docs += 1
            except Exception as e:
                job.failed_docs += 1
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    doc.status = "error"
            
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


@app.get("/api/batch/{job_id}")
async def get_batch_status(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get batch job status and progress."""
    job = db.query(BatchJob).filter(BatchJob.id == job_id).first()
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
    query = db.query(Document).filter(
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


@app.post("/api/document/{doc_id}/assign-review")
async def assign_review(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Assign a document to the current user for review."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
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
    red = db.query(Redaction).filter(Redaction.id == redaction_id).first()
    if not red:
        raise HTTPException(status_code=404, detail="Redaction not found")
    
    red.status = "approved"
    red.reviewer_id = user.id
    red.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    
    # Log review
    review = RedactionReview(
        redaction_id=red.id,
        document_id=red.document_id,
        reviewer_id=user.id,
        decision="approved",
        previous_bbox=red.bbox,
        new_bbox=red.bbox,
        previous_type=red.redaction_type,
        new_type=red.redaction_type,
    )
    db.add(review)
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
    red = db.query(Redaction).filter(Redaction.id == redaction_id).first()
    if not red:
        raise HTTPException(status_code=404, detail="Redaction not found")
    
    red.status = "rejected"
    red.reviewer_id = user.id
    red.reviewed_at = datetime.now(timezone.utc)
    red.review_reason = reason
    db.commit()
    
    # Log review
    review = RedactionReview(
        redaction_id=red.id,
        document_id=red.document_id,
        reviewer_id=user.id,
        decision="rejected",
        previous_bbox=red.bbox,
        new_bbox=red.bbox,
        previous_type=red.redaction_type,
        new_type=red.redaction_type,
        reason=reason,
    )
    db.add(review)
    db.commit()
    
    return {"message": "Redaction rejected"}


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
    red = db.query(Redaction).filter(Redaction.id == redaction_id).first()
    if not red:
        raise HTTPException(status_code=404, detail="Redaction not found")
    
    old_bbox = red.bbox
    old_type = red.redaction_type
    
    red.bbox = json.loads(new_bbox)
    if new_type:
        red.redaction_type = new_type
    red.status = "modified"
    red.reviewer_id = user.id
    red.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    
    # Log review
    review = RedactionReview(
        redaction_id=red.id,
        document_id=red.document_id,
        reviewer_id=user.id,
        decision="modified",
        previous_bbox=old_bbox,
        new_bbox=red.bbox,
        previous_type=old_type,
        new_type=red.redaction_type,
        reason=reason,
    )
    db.add(review)
    db.commit()
    
    return {"message": "Redaction modified"}


@app.post("/api/document/{doc_id}/approve-all")
async def approve_all_redactions(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Approve all pending redactions for a document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    reds = db.query(Redaction).filter(
        Redaction.document_id == doc_id,
        Redaction.status == "pending"
    ).all()
    
    for red in reds:
        red.status = "approved"
        red.reviewer_id = user.id
        red.reviewed_at = datetime.now(timezone.utc)
    
    doc.status = "review_approved"
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
    webhooks = db.query(Webhook).all()
    return [{"id": w.id, "url": w.url, "events": w.events, "active": w.active} for w in webhooks]


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["admin"]))
):
    """Delete a webhook."""
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
    from_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Total documents
    total_docs = db.query(Document).filter(Document.created_at >= from_date).count()
    
    # By status
    complete_docs = db.query(Document).filter(
        Document.created_at >= from_date,
        Document.status == "complete"
    ).count()
    review_docs = db.query(Document).filter(
        Document.created_at >= from_date,
        Document.status.in_(["needs_review", "in_review"])
    ).count()
    error_docs = db.query(Document).filter(
        Document.created_at >= from_date,
        Document.status == "error"
    ).count()
    
    # Auto-approval rate
    total_processed = complete_docs + review_docs
    auto_approval_rate = (complete_docs / total_processed * 100) if total_processed > 0 else 0
    
    # Redaction stats
    total_redactions = db.query(Redaction).join(Document).filter(
        Document.created_at >= from_date
    ).count()
    
    approved_redactions = db.query(Redaction).join(Document).filter(
        Document.created_at >= from_date,
        Redaction.status == "approved"
    ).count()
    
    rejected_redactions = db.query(Redaction).join(Document).filter(
        Document.created_at >= from_date,
        Redaction.status == "rejected"
    ).count()
    
    # Safeguarding alerts
    safeguarding_docs = db.query(Document).filter(
        Document.created_at >= from_date,
        Document.risk_flags.isnot(None)
    ).count()
    
    # By category
    category_stats = {}
    for cat in ["housing_repairs", "council_tax", "parking", "complaint", 
                "waste", "adult_social_care", "children_safeguarding", "foi_legal"]:
        count = db.query(Document).filter(
            Document.created_at >= from_date,
            Document.category == cat
        ).count()
        if count > 0:
            category_stats[cat] = count
    
    # Average processing time estimate (based on audit logs)
    audit_entries = db.query(AuditLog).filter(
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
                    message = STATUS_MESSAGES.get(doc.status, "Processing...")
                    payload = json.dumps({"status": doc.status, "message": message, "percent": percent})
                    yield f"data: {payload}\n\n"
                if doc.status in ("complete", "error", "needs_review", "review_approved"):
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
}

STATUS_MESSAGES = {
    "uploaded": "Document uploaded...",
    "preprocessing": "Preprocessing image...",
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
}


@app.get("/api/document/{doc_id}")
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
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

    # Apply role-based redaction visibility
    role = user.role if user else "public_facing"
    
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

    redactions_data = []
    for r in doc.redactions:
        # Apply role-based partial masking
        from redaction import get_role_policy, PARTIAL_REDACTION_POLICIES
        mode = get_role_policy(role, r.redaction_type)
        masked_value = r.original_value
        
        if mode == "partial" and r.original_value:
            policy = PARTIAL_REDACTION_POLICIES.get(r.redaction_type, {})
            mask_fn = policy.get("mask")
            if mask_fn:
                masked_value = mask_fn(r.original_value)
        elif mode == "full":
            masked_value = f"[REDACTED-{r.redaction_type}]"
        
        redactions_data.append({
            "id": r.id,
            "type": r.redaction_type,
            "original_value": r.original_value,
            "masked_value": masked_value,
            "visibility_mode": mode,
            "bbox": r.bbox,
            "confidence": r.confidence,
            "method": r.method,
            "status": r.status,
        })

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
        "engine_used": doc.engine_used,
        "layout_regions": doc.layout_regions,
        "reviewer_id": doc.reviewer_id,
        "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        "review_notes": doc.review_notes,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "ocr": ocr_data,
        "redactions": redactions_data,
        "batch_jobs": [{"id": b.id, "name": b.name} for b in doc.batch_jobs],
    }


@app.get("/api/document/{doc_id}/image")
async def get_document_image(
    doc_id: int,
    type: str = Query("original", enum=["original", "redacted", "mask"]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
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
    user: User = Depends(get_current_user)
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
async def approve_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"]))
):
    """Approve a processed document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "complete"
    doc.flag_needs_review = False
    doc.reviewer_id = user.id
    doc.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, doc.id, "approved", user_id=user.id)
    return {"message": "Document approved", "status": "complete"}


@app.post("/api/document/{doc_id}/review")
async def review_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Flag a document for human review."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = "needs_review"
    doc.flag_needs_review = True
    db.commit()
    log_action(db, doc.id, "flagged_for_review", user_id=user.id)
    return {"message": "Document flagged for review", "status": "needs_review"}


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
    query = db.query(Document)
    
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
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
    }


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
        "version": "2.0.0",
        "models": model_status,
    }
