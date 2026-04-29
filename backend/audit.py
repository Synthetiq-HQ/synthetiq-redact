from sqlalchemy.orm import Session
from models import AuditLog


def log_action(db: Session, document_id: int, action: str, user_id: str = "system", details: dict = None) -> AuditLog:
    """Create an audit log entry."""
    entry = AuditLog(
        document_id=document_id,
        action=action,
        user_id=user_id,
        details=details or {},
    )
    db.add(entry)
    db.commit()
    return entry
