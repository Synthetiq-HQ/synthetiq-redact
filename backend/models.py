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


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = Column(String, nullable=False)
    original_path: Mapped[str] = Column(String, nullable=False)
    redacted_path: Mapped[Optional[str]] = Column(String, nullable=True)
    mask_path: Mapped[Optional[str]] = Column(String, nullable=True)
    status: Mapped[str] = Column(
        String,
        nullable=False,
        default="uploaded",
    )
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
    created_at: Mapped[datetime] = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    ocr_results: Mapped[List["OCRResult"]] = relationship(
        "OCRResult", back_populates="document", cascade="all, delete-orphan"
    )
    redactions: Mapped[List["Redaction"]] = relationship(
        "Redaction", back_populates="document", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="document", cascade="all, delete-orphan"
    )


class OCRResult(Base):
    __tablename__ = "ocr_results"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = Column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
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
    document_id: Mapped[int] = Column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    redaction_type: Mapped[str] = Column(String, nullable=False)
    original_value: Mapped[Optional[str]] = Column(String, nullable=True)
    bbox: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = Column(Float, nullable=True)
    method: Mapped[Optional[str]] = Column(String, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="redactions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = Column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = Column(String, nullable=False)
    user_id: Mapped[Optional[str]] = Column(String, nullable=True, default="system")
    details: Mapped[Optional[dict]] = Column(JSON, nullable=True)
    timestamp: Mapped[datetime] = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    document: Mapped["Document"] = relationship("Document", back_populates="audit_logs")
