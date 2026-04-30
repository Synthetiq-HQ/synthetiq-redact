import os
import json
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# For tamper-proof audit, we would use proper crypto libraries
# For now, use HMAC-SHA256 for integrity
AUDIT_SECRET = os.environ.get("AUDIT_SECRET", "synthetiq-audit-secret-change-in-production")


def _compute_hash(data: str, previous_hash: str) -> str:
    """Compute chained hash for tamper-proof audit."""
    combined = f"{previous_hash}:{data}"
    return hashlib.sha256(combined.encode()).hexdigest()


def _sign_hash(hash_value: str) -> str:
    """Sign the hash with HMAC."""
    return hmac.new(AUDIT_SECRET.encode(), hash_value.encode(), hashlib.sha256).hexdigest()


def log_action(db, document_id: int, action: str, user_id: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
    """
    Log an action with tamper-proof chain hashing.
    Each entry includes the hash of the previous entry, creating a chain.
    """
    from models_v2 import AuditLog

    # Get the previous hash
    last_entry = (
        db.query(AuditLog)
        .filter(AuditLog.document_id == document_id)
        .order_by(AuditLog.timestamp.desc())
        .first()
    )
    previous_hash = last_entry.chain_hash if last_entry else "0" * 64

    # Build the entry data
    entry_data = {
        "document_id": document_id,
        "action": action,
        "user_id": user_id,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "previous_hash": previous_hash,
    }
    
    # Compute chain hash
    data_str = json.dumps(entry_data, sort_keys=True)
    chain_hash = _compute_hash(data_str, previous_hash)
    signature = _sign_hash(chain_hash)

    # Create the audit log entry
    entry = AuditLog(
        document_id=document_id,
        action=action,
        user_id=user_id,
        details=details,
        chain_hash=chain_hash,
        signature=signature,
        previous_hash=previous_hash,
    )
    db.add(entry)
    db.commit()
    return entry


def verify_audit_chain(db, document_id: int) -> bool:
    """
    Verify the audit chain for a document hasn't been tampered with.
    Returns True if chain is valid, False if tampered.
    """
    from models_v2 import AuditLog

    entries = (
        db.query(AuditLog)
        .filter(AuditLog.document_id == document_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )

    if not entries:
        return True

    expected_previous = "0" * 64
    
    for entry in entries:
        # Verify previous hash links
        if entry.previous_hash != expected_previous:
            return False
        
        # Rebuild entry data
        entry_data = {
            "document_id": entry.document_id,
            "action": entry.action,
            "user_id": entry.user_id,
            "details": entry.details,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "previous_hash": entry.previous_hash,
        }
        
        # Verify chain hash
        data_str = json.dumps(entry_data, sort_keys=True)
        computed_hash = _compute_hash(data_str, entry.previous_hash)
        if computed_hash != entry.chain_hash:
            return False
        
        # Verify signature
        expected_sig = _sign_hash(entry.chain_hash)
        if expected_sig != entry.signature:
            return False
        
        expected_previous = entry.chain_hash

    return True
