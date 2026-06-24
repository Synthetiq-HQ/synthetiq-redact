import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VISION_MODEL = os.environ.get("VISION_VERIFIER_MODEL", "gemma4:e4b-it-qat")
VISION_TIMEOUT_SECONDS = int(os.environ.get("VISION_VERIFIER_TIMEOUT", "240"))
VISION_MAX_SIDE = int(os.environ.get("VISION_VERIFIER_MAX_SIDE", "1600"))
OLLAMA_GENERATE_URL = os.environ.get("OLLAMA_GENERATE_URL", "http://127.0.0.1:11434/api/generate")

CRITICAL_TYPES = {
    "person_name",
    "address",
    "postcode",
    "phone",
    "email",
    "dob",
    "council_ref",
    "case_ref",
    "child_name",
    "child_age",
    "medical_details",
    "social_care_context",
    "safeguarding",
    "signature",
}

VISION_PROMPT = """You are a local second-reader for a UK council document redaction tool.
Read this page image and return ONLY valid JSON.

Schema:
{
  "full_text": "page transcription preserving line breaks where possible",
  "sensitive_items": [
    {"type": "person_name|address|postcode|phone|email|dob|council_ref|case_ref|child_name|child_age|medical_details|social_care_context|safeguarding|signature|notes", "value": "exact visible text", "confidence": 0.0}
  ],
  "uncertain_items": ["text you are unsure about"],
  "quality_notes": "brief page quality note"
}

Rules:
- Copy identifiers, emails, references, and numbers exactly as visible.
- Do not normalise fake personal data into a more common value.
- If unsure, add the value to uncertain_items.
- No markdown and no explanation outside JSON.
"""


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _downscale_for_vision(image_path: str) -> str:
    """Create a compact JPEG for local VLM processing."""
    from PIL import Image, ImageOps

    source = Path(image_path)
    out_path = source.with_name(f"{source.stem}_vision.jpg")
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        longest = max(image.size)
        if longest > VISION_MAX_SIDE:
            scale = VISION_MAX_SIDE / longest
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        image.save(out_path, "JPEG", quality=80, optimize=True)
    return str(out_path)


def _parse_response(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Vision response was not a JSON object")
    parsed.setdefault("full_text", "")
    parsed.setdefault("sensitive_items", [])
    parsed.setdefault("uncertain_items", [])
    parsed.setdefault("quality_notes", "")
    if not isinstance(parsed["sensitive_items"], list):
        parsed["sensitive_items"] = []
    if not isinstance(parsed["uncertain_items"], list):
        parsed["uncertain_items"] = []
    return parsed


def run_vision_verification(image_path: str, ocr_text: str) -> dict[str, Any]:
    """Run local Gemma/Gamma vision verification for one page."""
    start = time.perf_counter()
    vision_image = _downscale_for_vision(image_path)
    payload = {
        "model": VISION_MODEL,
        "prompt": VISION_PROMPT,
        "images": [base64.b64encode(Path(vision_image).read_bytes()).decode("ascii")],
        "stream": False,
        "format": "json",
        "think": False,
        "options": {"temperature": 0, "num_predict": 1600},
    }
    request = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=VISION_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode())
        parsed = _parse_response(body.get("response", ""))
        warnings = compare_ocr_and_vision(ocr_text, parsed)
        return {
            "status": "complete",
            "model": VISION_MODEL,
            "elapsed_seconds": round(time.perf_counter() - start, 2),
            "full_text": parsed.get("full_text", ""),
            "sensitive_items": parsed.get("sensitive_items", []),
            "uncertain_items": parsed.get("uncertain_items", []),
            "quality_notes": parsed.get("quality_notes", ""),
            "warnings": warnings,
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Vision verification failed for %s: %s", image_path, exc)
        return {
            "status": "failed",
            "model": VISION_MODEL,
            "elapsed_seconds": round(time.perf_counter() - start, 2),
            "full_text": "",
            "sensitive_items": [],
            "uncertain_items": [],
            "quality_notes": "",
            "warnings": [f"Vision verification failed: {exc}"],
        }


def compare_ocr_and_vision(ocr_text: str, vision: dict[str, Any]) -> list[dict[str, Any]]:
    """Return warning objects where vision saw sensitive data OCR may have missed."""
    warnings: list[dict[str, Any]] = []
    ocr_compact = _compact(ocr_text)
    for item in vision.get("sensitive_items", []) or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "notes")
        value = str(item.get("value") or "").strip()
        if len(value) < 2:
            continue
        matched = _compact(value) in ocr_compact
        if not matched or item_type in CRITICAL_TYPES:
            warnings.append(
                {
                    "type": item_type,
                    "value": value,
                    "matched_ocr": matched,
                    "severity": "high" if item_type in CRITICAL_TYPES else "medium",
                    "message": (
                        "Vision found sensitive data not confidently mapped to OCR"
                        if not matched
                        else "Vision confirmed high-risk sensitive data"
                    ),
                }
            )
    for uncertain in vision.get("uncertain_items", []) or []:
        text = str(uncertain).strip()
        if text:
            warnings.append(
                {
                    "type": "uncertain",
                    "value": text,
                    "matched_ocr": _compact(text) in ocr_compact,
                    "severity": "medium",
                    "message": "Vision model was uncertain about this text",
                }
            )
    return warnings
