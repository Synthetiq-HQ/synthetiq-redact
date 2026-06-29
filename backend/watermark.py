"""
Burned-in, machine-readable provenance watermark for Synthetiq Redact exports.

We embed a small QR code (proven finder anchors + Reed-Solomon error correction)
carrying the signed export id, placed in the least-inky page corner so it avoids
content and survives PDF export, screenshots, scaling and phone photos. The id is
also written to PDF metadata as a secondary signal (printed/scanned copies lose
metadata, hence the visual mark is primary).

Decoding scans the corners first (where we place it), then the whole page, using
OpenCV's QR detector.
"""

from __future__ import annotations

import io
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

QR_MIN, QR_MAX, QR_FRAC = 90, 150, 0.12
INK_THRESHOLD = 200          # pixel < this counts as "ink"
LOW_INK_FRACTION = 0.04      # a corner is "clear" below this ink fraction
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


def _qr_image(payload: str, size: int) -> Image.Image:
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((size, size), Image.NEAREST)


def _ink_fraction(region: Image.Image) -> float:
    arr = np.asarray(region.convert("L"))
    if arr.size == 0:
        return 1.0
    return float((arr < INK_THRESHOLD).mean())


def _corner_box(corner: str, w: int, h: int, bw: int, bh: int, margin: int) -> Tuple[int, int]:
    if corner == "top-left":
        return margin, margin
    if corner == "top-right":
        return w - bw - margin, margin
    if corner == "bottom-left":
        return margin, h - bh - margin
    return w - bw - margin, h - bh - margin


def embed_watermark(image: Image.Image, payload: str, page_number: int = 1) -> Tuple[Image.Image, dict]:
    """Burn a QR of `payload` into the least-inky corner. Returns (image, position)."""
    base = image.convert("RGB")
    w, h = base.size
    qr_size = int(min(max(min(w, h) * QR_FRAC, QR_MIN), QR_MAX))
    pad = max(6, qr_size // 12)          # white quiet-zone box padding
    box_w = box_h = qr_size + pad * 2
    margin = max(8, qr_size // 8)

    # Score each corner by ink density; prefer the clearest.
    scored = []
    for corner in CORNERS:
        x, y = _corner_box(corner, w, h, box_w, box_h, margin)
        x, y = max(0, x), max(0, y)
        region = base.crop((x, y, min(w, x + box_w), min(h, y + box_h)))
        scored.append((_ink_fraction(region), corner, x, y))
    scored.sort(key=lambda t: t[0])
    ink, corner, x, y = scored[0]

    qr = _qr_image(payload, qr_size)
    # Opaque white quiet-zone box guarantees the QR stays decodable even if the
    # chosen corner has some ink. If a corner has light content we blend slightly.
    box = Image.new("RGB", (box_w, box_h), "white")
    box.paste(qr, (pad, pad))
    if ink > LOW_INK_FRACTION:
        # No clear margin: keep it as unobtrusive as possible (slight transparency).
        patch = base.crop((x, y, x + box_w, y + box_h))
        box = Image.blend(patch, box, 0.88)

    base.paste(box, (x, y))
    return base, {
        "page": page_number,
        "corner": corner,
        "box": [int(x), int(y), int(box_w), int(box_h)],
        "qr_size": int(qr_size),
        "ink": round(float(ink), 4),
    }


def embed_in_images(images: List[Image.Image], payload: str) -> Tuple[List[Image.Image], List[dict]]:
    out, positions = [], []
    for i, img in enumerate(images, start=1):
        marked, pos = embed_watermark(img, payload, page_number=i)
        out.append(marked)
        positions.append(pos)
    return out, positions


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------

def _detect(arr: np.ndarray) -> Optional[str]:
    import cv2

    detector = cv2.QRCodeDetector()
    try:
        data, _pts, _ = detector.detectAndDecode(arr)
    except Exception:
        return None
    data = (data or "").strip().upper()
    return data if data.startswith("SRD-") else None


def decode_image(image: Image.Image) -> Optional[str]:
    """Scan corners first (where we place it), then the full page."""
    import cv2

    rgb = image.convert("RGB")
    w, h = rgb.size
    gray_full = np.asarray(rgb.convert("L"))

    # Corner crops, upscaled for small marks.
    cw, ch = int(w * 0.32), int(h * 0.32)
    crops = [
        (0, 0, cw, ch), (w - cw, 0, w, ch),
        (0, h - ch, cw, h), (w - cw, h - ch, w, h),
    ]
    candidates: List[np.ndarray] = []
    for (x0, y0, x1, y1) in crops:
        crop = gray_full[y0:y1, x0:x1]
        if crop.size:
            candidates.append(crop)
            candidates.append(cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC))
    candidates.append(gray_full)

    for arr in candidates:
        found = _detect(arr)
        if found:
            return found
        # try a binarised version (helps photos / uneven lighting)
        try:
            _t, binar = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            found = _detect(binar)
            if found:
                return found
        except Exception:
            pass
    return None


def decode_pdf(path: str) -> Optional[str]:
    """Rasterise pages and decode; also check PDF metadata as a fallback."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        fitz = None

    if fitz is not None:
        try:
            doc = fitz.open(path)
            # Metadata secondary signal first (cheap).
            meta_id = (doc.metadata or {}).get("keywords", "") or ""
            for token in meta_id.replace(",", " ").split():
                if token.strip().upper().startswith("SRD-"):
                    return token.strip().upper()
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                found = decode_image(img)
                if found:
                    return found
        except Exception:
            pass
    return None


def decode_any(path: str) -> Optional[str]:
    """Decode an export id from a PDF or image file."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        return decode_pdf(path)
    try:
        with Image.open(path) as img:
            return decode_image(img)
    except Exception:
        return None


def set_pdf_metadata_id(path: str, export_id: str) -> bool:
    """Write the export id into PDF keywords metadata (secondary signal)."""
    try:
        import fitz

        doc = fitz.open(path)
        meta = doc.metadata or {}
        meta["keywords"] = export_id
        meta["producer"] = "Synthetiq Redact"
        meta["creator"] = "Synthetiq Redact"
        doc.set_metadata(meta)
        doc.saveIncr()
        doc.close()
        return True
    except Exception:
        return False
