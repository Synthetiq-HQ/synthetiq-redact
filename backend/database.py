from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from config import DB_PATH
from models import Base

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    """Add lightweight SQLite columns for existing prototype databases."""
    additions = {
        "documents": {
            "transcription_clean_path": "VARCHAR",
            "transcription_json_path": "VARCHAR",
            "redacted_docx_path": "VARCHAR",
            "handwriting_backend": "VARCHAR",
            "handwriting_confidence": "FLOAT",
            "handwriting_review_reason": "TEXT",
        },
        "ocr_results": {
            "clean_text": "TEXT",
            "transcription_data": "JSON",
        },
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            for column, column_type in columns.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
