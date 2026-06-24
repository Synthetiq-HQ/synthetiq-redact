from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models_v2 import Base
from config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all tables and apply lightweight SQLite migrations."""
    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations()
    _backfill_document_pages()


def _apply_sqlite_migrations():
    """Add V2 pilot-readiness columns to existing SQLite demo databases.

    This is intentionally small and deterministic. A full production deployment
    should replace this with Alembic migrations before the first council pilot.
    """
    if not DB_PATH.endswith(".sqlite3"):
        return

    migrations = {
        "users": {
            "council_id": "INTEGER",
        },
        "documents": {
            "council_id": "INTEGER",
            "uploaded_by": "INTEGER",
            "source_filename": "VARCHAR",
            "storage_key": "VARCHAR",
            "redacted_storage_key": "VARCHAR",
            "confidence_summary": "JSON",
            "needs_review_reason": "TEXT",
            "retention_due_at": "DATETIME",
            "engine_used": "VARCHAR",
            "layout_regions": "JSON",
            "reviewer_id": "INTEGER",
            "reviewed_at": "DATETIME",
            "review_notes": "TEXT",
        },
        "batch_jobs": {
            "council_id": "INTEGER",
        },
        "audit_logs": {
            "council_id": "INTEGER",
            "chain_hash": "VARCHAR",
            "signature": "VARCHAR",
            "previous_hash": "VARCHAR",
            "user_id": "INTEGER",
        },
        "redactions": {
            "page_id": "INTEGER",
            "page_number": "INTEGER DEFAULT 1",
            "status": "VARCHAR DEFAULT 'pending'",
            "partial_mode": "VARCHAR",
            "masked_value": "VARCHAR",
            "reviewer_id": "INTEGER",
            "reviewed_at": "DATETIME",
            "review_reason": "TEXT",
        },
        "ocr_results": {
            "page_id": "INTEGER",
            "page_number": "INTEGER DEFAULT 1",
        },
        "redaction_reviews": {
            "page_id": "INTEGER",
            "page_number": "INTEGER DEFAULT 1",
            "action_type": "VARCHAR",
            "previous_status": "VARCHAR",
            "new_status": "VARCHAR",
        },
    }

    with engine.begin() as conn:
        for table_name, columns in migrations.items():
            existing = conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            if not existing:
                continue
            existing_names = {row[1] for row in existing}
            for column_name, definition in columns.items():
                if column_name not in existing_names:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )


def _backfill_document_pages():
    """Create page 1 rows for legacy documents and attach legacy rows."""
    if not DB_PATH.endswith(".sqlite3"):
        return
    with engine.begin() as conn:
        tables = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}
        if "documents" not in table_names or "document_pages" not in table_names:
            return

        docs = conn.exec_driver_sql(
            "SELECT id, original_path, redacted_path, mask_path FROM documents"
        ).fetchall()
        for doc_id, original_path, redacted_path, mask_path in docs:
            existing = conn.exec_driver_sql(
                "SELECT id FROM document_pages WHERE document_id = ? AND page_number = 1",
                (doc_id,),
            ).fetchone()
            if existing:
                page_id = existing[0]
            else:
                conn.exec_driver_sql(
                    """
                    INSERT INTO document_pages (
                        document_id, page_number, original_image_path,
                        display_image_path, ocr_image_path, redacted_image_path,
                        mask_image_path, vision_status
                    ) VALUES (?, 1, ?, ?, ?, ?, ?, 'not_run')
                    """,
                    (doc_id, original_path, original_path, original_path, redacted_path, mask_path),
                )
                page_id = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()

            for table in ("ocr_results", "redactions", "redaction_reviews"):
                if table in table_names:
                    conn.exec_driver_sql(
                        f"UPDATE {table} SET page_id = ?, page_number = 1 WHERE document_id = ? AND page_id IS NULL",
                        (page_id, doc_id),
                    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
