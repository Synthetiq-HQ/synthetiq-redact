"""
Local-only provenance for Synthetiq Redact exports.

Each installed server has a permanent local **instance** (id + secret), created once.
Every redacted export gets a signed, self-verifying **export ID**:

    SRD-{serverShortId}-{randomToken}-{checksum}

- `serverShortId` identifies the producing server (derived from the instance id).
- `randomToken` is random (not sequential), so ids are not guessable in order.
- `checksum` is an HMAC of the core using this server's secret, so another server
  cannot forge an id that validates here, and an id from another server is
  recognised as "foreign" (wrong server) rather than silently trusted.

The id maps (in a local SQLite store) to the originating document, hashes, policy,
timestamp, user, page count and watermark positions. Nothing is global/public.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_DATA_DIR = Path(
    os.environ.get("SYNTHETIQ_DATA_DIR")
    or (Path(__file__).resolve().parent / "data" / "provenance")
)


def _b32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def file_sha256(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ProvenanceStore:
    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._instance = self._load_or_create_instance()
        self.db_path = self.dir / "provenance.db"
        self._init_db()

    # -- instance -----------------------------------------------------------

    def _load_or_create_instance(self) -> Dict[str, str]:
        path = self.dir / "instance.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        instance_id = secrets.token_hex(16)
        info = {
            "instance_id": instance_id,
            "secret": secrets.token_hex(32),
            "short_id": _b32(hashlib.sha256(instance_id.encode()).digest())[:6].upper(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(info, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return info

    @property
    def short_id(self) -> str:
        return self._instance["short_id"]

    @property
    def _secret(self) -> bytes:
        return self._instance["secret"].encode("ascii")

    def instance_info(self) -> Dict[str, Any]:
        return {
            "instance_id": self._instance["instance_id"],
            "short_id": self.short_id,
            "created_at": self._instance.get("created_at"),
        }

    # -- id generation / verification --------------------------------------

    def _checksum(self, core: str) -> str:
        mac = hmac.new(self._secret, core.encode("ascii"), hashlib.sha256).digest()
        return _b32(mac)[:4].upper()

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def new_export_id(self) -> str:
        token = _b32(secrets.token_bytes(5))[:8].upper()
        core = f"{self.short_id}-{token}"
        return f"SRD-{self.short_id}-{token}-{self._checksum(core)}"

    def verify_format(self, export_id: str) -> str:
        """Return 'ours' | 'foreign' | 'invalid'."""
        parts = (export_id or "").strip().upper().split("-")
        if len(parts) != 4 or parts[0] != "SRD":
            return "invalid"
        _, short, token, checksum = parts
        if short != self.short_id:
            return "foreign"
        if self._checksum(f"{short}-{token}") != checksum:
            return "invalid"
        return "ours"

    # -- store --------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exports (
                    export_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    document_id INTEGER,
                    redacted_output_id TEXT,
                    user_id INTEGER,
                    original_hash TEXT,
                    redacted_hash TEXT,
                    engine_used TEXT,
                    page_count INTEGER,
                    filename TEXT,
                    watermark_positions TEXT,
                    metadata TEXT,
                    signature TEXT
                )
                """
            )

    def create_export(
        self,
        *,
        document_id: Optional[int] = None,
        filename: Optional[str] = None,
        user_id: Optional[int] = None,
        original_hash: Optional[str] = None,
        redacted_hash: Optional[str] = None,
        engine_used: Optional[str] = None,
        page_count: Optional[int] = None,
        watermark_positions: Optional[list] = None,
        redacted_output_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            export_id = self.new_export_id()
            created_at = datetime.now(timezone.utc).isoformat()
            redacted_output_id = redacted_output_id or _b32(secrets.token_bytes(6)).upper()
            record = {
                "export_id": export_id,
                "created_at": created_at,
                "document_id": document_id,
                "redacted_output_id": redacted_output_id,
                "user_id": user_id,
                "original_hash": original_hash,
                "redacted_hash": redacted_hash,
                "engine_used": engine_used,
                "page_count": page_count,
                "filename": filename,
                "watermark_positions": json.dumps(watermark_positions or []),
                "metadata": json.dumps(extra or {}),
            }
            record["signature"] = self._sign(
                export_id + "|" + json.dumps(record, sort_keys=True)
            )
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO exports
                       (export_id, created_at, document_id, redacted_output_id, user_id,
                        original_hash, redacted_hash, engine_used, page_count, filename,
                        watermark_positions, metadata, signature)
                       VALUES (:export_id,:created_at,:document_id,:redacted_output_id,:user_id,
                        :original_hash,:redacted_hash,:engine_used,:page_count,:filename,
                        :watermark_positions,:metadata,:signature)""",
                    record,
                )
            return self._row_to_public(record)

    def update_export(self, export_id: str, *, redacted_hash: Optional[str] = None,
                      watermark_positions: Optional[list] = None) -> None:
        sets, vals = [], []
        if redacted_hash is not None:
            sets.append("redacted_hash=?")
            vals.append(redacted_hash)
        if watermark_positions is not None:
            sets.append("watermark_positions=?")
            vals.append(json.dumps(watermark_positions))
        if not sets:
            return
        vals.append(export_id.strip().upper())
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE exports SET {', '.join(sets)} WHERE export_id=?", vals)

    def lookup(self, export_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM exports WHERE export_id=?", (export_id.strip().upper(),)
            ).fetchone()
        return self._row_to_public(dict(row)) if row else None

    @staticmethod
    def _row_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        for key in ("watermark_positions", "metadata"):
            val = out.get(key)
            if isinstance(val, str):
                try:
                    out[key] = json.loads(val)
                except Exception:
                    out[key] = val
        out.pop("signature", None)
        return out

    def decode_result(self, export_id: str) -> Dict[str, Any]:
        """Classify a scanned id and return the record if it belongs here."""
        status = self.verify_format(export_id)
        if status == "foreign":
            return {"status": "foreign", "export_id": export_id.strip().upper(),
                    "message": "This ID was produced by a different Synthetiq Redact server."}
        if status == "invalid":
            return {"status": "invalid", "message": "Not a valid Synthetiq Redact ID for this server."}
        record = self.lookup(export_id)
        if record:
            return {"status": "found", "record": record}
        return {"status": "not_in_library",
                "export_id": export_id.strip().upper(),
                "message": "Valid format for this server, but no matching export was found."}


_STORE: Optional[ProvenanceStore] = None
_STORE_LOCK = threading.Lock()


def get_provenance_store() -> ProvenanceStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = ProvenanceStore()
    return _STORE
