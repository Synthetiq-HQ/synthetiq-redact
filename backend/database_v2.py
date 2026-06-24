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
            "status": "VARCHAR DEFAULT 'pending'",
            "partial_mode": "VARCHAR",
            "masked_value": "VARCHAR",
            "reviewer_id": "INTEGER",
            "reviewed_at": "DATETIME",
            "review_reason": "TEXT",
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
