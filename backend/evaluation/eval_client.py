"""
HTTP client for the local Synthetiq Redact backend API.
Handles upload, progress polling, and result fetching.
"""

import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any

BASE_URL = "http://127.0.0.1:8000"


def upload_document(image_path: str | Path, category: str = "", translate: bool = False) -> dict:
    """Upload an image and return the document metadata."""
    path = Path(image_path)
    with open(path, "rb") as f:
        files = {"file": (path.name, f, f"image/{path.suffix.lstrip('.')}")}
        data = {"translate": str(translate).lower()}
        if category:
            data["category"] = category
        resp = requests.post(f"{BASE_URL}/api/upload", files=files, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()


def poll_progress(doc_id: int, timeout: int = 300) -> dict:
    """Poll SSE progress endpoint until complete/error/review."""
    start = time.time()
    last_status = ""
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{BASE_URL}/api/progress/{doc_id}", stream=True, timeout=10)
            for line in resp.iter_lines():
                if line:
                    text = line.decode("utf-8")
                    if text.startswith("data: "):
                        import json
                        try:
                            data = json.loads(text[6:])
                            last_status = data.get("status", last_status)
                            if last_status in ("complete", "error", "needs_review"):
                                return data
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        time.sleep(1)
    return {"status": last_status or "timeout", "message": "Polling timed out"}


def get_document(doc_id: int) -> dict:
    """Fetch full document details including redactions."""
    resp = requests.get(f"{BASE_URL}/api/document/{doc_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_image_bytes(doc_id: int, img_type: str = "original") -> bytes:
    """Fetch image bytes (original, redacted, mask)."""
    resp = requests.get(
        f"{BASE_URL}/api/document/{doc_id}/image",
        params={"type": img_type},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


def process_image(image_path: str | Path, category: str = "", translate: bool = False) -> Optional[Dict[str, Any]]:
    """
    End-to-end: upload, poll, return full document result.
    Returns None on failure.
    """
    try:
        upload_result = upload_document(image_path, category, translate)
        doc_id = upload_result.get("document_id")
        if not doc_id:
            print(f"[EvalClient] Upload failed for {image_path}: no doc_id")
            return None

        progress = poll_progress(doc_id)
        if progress["status"] == "error":
            print(f"[EvalClient] Pipeline error for doc {doc_id}: {progress.get('message')}")
            return None

        return get_document(doc_id)
    except Exception as e:
        print(f"[EvalClient] Exception processing {image_path}: {e}")
        return None
