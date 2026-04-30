import json
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    Table,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship, sessionmaker

from config import DB_PATH


class Base(DeclarativeBase):
    pass


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    OCR = "ocr"
    REDACTION = "redaction"
    TRANSLATION = "translation"
    CLASSIFICATION = "classification"
    ROUTING = "routing"
    COMPLETE = "complete"
    ERROR = "error"
    NEEDS_REVIEW = "needs_review"
    IN_REVIEW = "in_review"
    REVIEW_APPROVED = "review_approved"


# Many-to-many: Document <-> BatchJob
batch_job_documents = Table(
    "batch_job_documents",
    Base.metadata,
    Column("batch_id", String, ForeignKey("batch_jobs.id")),
    Column("document_id", Integer, ForeignKey("documents.id")),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    email: Mapped[str] = Column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = Column(String, nullable=False)
    role: Mapped[str] = Column(String, nullable=False, default="processor")  # admin, reviewer, processor, auditor, caseworker
    department: Mapped[Optional[str]] = Column(String, nullable=True)
    is_active: Mapped[bool] = Column(Boolean, default=True)
    created_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    reviews = relationship("RedactionReview", back_populates="reviewer")
    audit_logs = relationship("AuditLog", back_populates="user")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[str] = Column(String, primary_key=True, index=True)
    name: Mapped[str] = Column(String, nullable=True)
    status: Mapped[str] = Column(String, nullable=False, default="queued")  # queued, processing, complete, failed
    total_docs: Mapped[int] = Column(Integer, default=0)
    processed_docs: Mapped[int] = Column(Integer, default=0)
    failed_docs: Mapped[int] = Column(Integer, default=0)
    config: Mapped[Optional[dict]] = Column(JSON, nullable=True)  # Redaction profile, etc.
    created_by: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)

    documents = relationship("Document", secondary=batch_job_documents, back_populates="batch_jobs")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = Column(String, nullable=False)
    original_path: Mapped[str] = Column(String, nullable=False)
    redacted_path: Mapped[Optional[str]] = Column(String, nullable=True)
    mask_path: Mapped[Optional[str]] = Column(String, nullable=True)
    status: Mapped[str] = Column(String, nullable=False, default="uploaded")
    category: Mapped[Optional[str]] = Column(String, nullable=True)
    department: Mapped[Optional[str]] = Column(String, nullable=True)
    urgency_score: Mapped[Optional[float]] = Column(Float, nullable=True)
    sentiment: Mapped[Optional[str]] = Column(String, nullable=True)
    risk_flags: Mapped[Optional[list]] = Column(JSON, nullable=True)
    confidence_score: Mapped[Optional[float]] = Column(Float, nullable=True)
    language_detected: Mapped[Optional[str]] = Column(String, nullable=True)
    translated: Mapped[bool] = Column(Boolean, default=False)
    flag_needs_review: Mapped[bool] = Column(Boolean, default=False)
    text_export_path: Mapped[Optional[str]] = Column(String, nullable=True)
    selected_category: Mapped[Optional[str]] = Column(String, nullable=True)
    redaction_profile: Mapped[Optional[str]] = Column(String, nullable=True)
    output_folder_path: Mapped[Optional[str]] = Column(String, nullable=True)
    transcription_clean_path: Mapped[Optional[str]] = Column(String, nullable=True)
    transcription_json_path: Mapped[Optional[str]] = Column(String, nullable=True)
    redacted_docx_path: Mapped[Optional[str]] = Column(String, nullable=True)
    handwriting_backend: Mapped[Optional[str]] = Column(String, nullable=True)
    handwriting_confidence: Mapped[Optional[float]] = Column(Float, nullable=True)
    handwriting_review_reason: Mapped[Optional[str]] = Column(Text, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # New v2 fields
    engine_used: Mapped[Optional[str]] = Column(String, nullable=True)  # paddleocr, easyocr, etc.
    layout_regions: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    reviewer_id: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    review_notes: Mapped[Optional[str]] = Column(Text, nullable=True)

    # Relationships
    ocr_results: Mapped[List["OCRResult"]] = relationship("OCRResult", back_populates="document", cascade="all, delete-orphan")
    redactions: Mapped[List["Redaction"]] = relationship("Redaction", back_populates="document", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="document", cascade="all, delete-orphan")
    reviews: Mapped[List["RedactionReview"]] = relationship("RedactionReview", back_populates="document")
    batch_jobs = relationship("BatchJob", secondary=batch_job_documents, back_populates="documents")


class OCRResult(Base):
    __tablename__ = "ocr_results"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    extracted_text: Mapped[str] = Column(Text, nullable=False)
    redacted_text: Mapped[Optional[str]] = Column(Text, nullable=True)
    translated_text: Mapped[Optional[str]] = Column(Text, nullable=True)
    clean_text: Mapped[Optional[str]] = Column(Text, nullable=True)
    transcription_data: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    ocr_confidence: Mapped[Optional[float]] = Column(Float, nullable=True)
    words: Mapped[Optional[list]] = Column(JSON, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="ocr_results")


class Redaction(Base):
    __tablename__ = "redactions"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    redaction_type: Mapped[str] = Column(String, nullable=False)
    original_value: Mapped[Optional[str]] = Column(String, nullable=True)
    bbox: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = Column(Float, nullable=True)
    method: Mapped[Optional[str]] = Column(String, nullable=True)

    # New v2 fields
    status: Mapped[str] = Column(String, default="pending")  # pending, approved, rejected, modified
    partial_mode: Mapped[Optional[str]] = Column(String, nullable=True)  # full, partial, none
    masked_value: Mapped[Optional[str]] = Column(String, nullable=True)  # The partially masked version
    reviewer_id: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    review_reason: Mapped[Optional[str]] = Column(Text, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="redactions")
    reviews = relationship("RedactionReview", back_populates="redaction")


class RedactionReview(Base):
    __tablename__ = "redaction_reviews"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    redaction_id: Mapped[int] = Column(Integer, ForeignKey("redactions.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[int] = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[int] = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = Column(String, nullable=False)  # approved, rejected, modified
    previous_bbox: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    new_bbox: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    previous_type: Mapped[Optional[str]] = Column(String, nullable=True)
    new_type: Mapped[Optional[str]] = Column(String, nullable=True)
    reason: Mapped[Optional[str]] = Column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    redaction: Mapped["Redaction"] = relationship("Redaction", back_populates="reviews")
    document: Mapped["Document"] = relationship("Document", back_populates="reviews")
    reviewer: Mapped["User"] = relationship("User", back_populates="reviews")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = Column(String, nullable=False)
    user_id: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True, default=None)
    details: Mapped[Optional[dict]] = Column(JSON, nullable=True)

    # Tamper-proof fields
    chain_hash: Mapped[Optional[str]] = Column(String, nullable=True)
    signature: Mapped[Optional[str]] = Column(String, nullable=True)
    previous_hash: Mapped[Optional[str]] = Column(String, nullable=True)

    timestamp: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document: Mapped["Document"] = relationship("Document", back_populates="audit_logs")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    url: Mapped[str] = Column(String, nullable=False)
    events: Mapped[Optional[list]] = Column(JSON, nullable=True)  # ["doc.complete", "doc.needs_review"]
    secret: Mapped[Optional[str]] = Column(String, nullable=True)
    active: Mapped[bool] = Column(Boolean, default=True)
    created_by: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    category: Mapped[str] = Column(String, unique=True, nullable=False)
    retention_years: Mapped[int] = Column(Integer, default=7)
    auto_purge: Mapped[bool] = Column(Boolean, default=False)
    created_at: Mapped[datetime] = Column(DateTime, default=lambda: datetime.now(timezone.utc))
