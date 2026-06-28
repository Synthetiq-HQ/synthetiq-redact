"""
Local GLM-OCR engine (via Ollama) for handwriting transcription.

Runs against a local Ollama server hosting a GLM-OCR model. Uses the GPU if the
server has one, CPU otherwise (slower) - the same code path serves both the
dedicated GPU server and on-device local use.

This engine returns TEXT only (GLM-OCR has no pixel coordinates). Coordinates come
from a layout OCR (EasyOCR) and the two are fused by RedactionGeometryMapper.

Designed to fail soft: if Ollama or the model is unavailable, callers get a clear
signal and can fall back to the existing EasyOCR text path. Never crashes startup.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("GLM_OCR_MODEL", "glm-ocr:latest")
DEFAULT_TIMEOUT = float(os.environ.get("GLM_OCR_TIMEOUT", "180"))
# The model context is small (~4k tokens) and a full-res photo alone can consume
# all of it, leaving no room to generate. Resize the longest side before sending
# so the image fits with room to spare, and cap the output token budget.
DEFAULT_MAX_SIDE = int(os.environ.get("GLM_OCR_MAX_SIDE", "1280"))
DEFAULT_NUM_PREDICT = int(os.environ.get("GLM_OCR_NUM_PREDICT", "2048"))
DEFAULT_PROMPT = os.environ.get(
    "GLM_OCR_PROMPT",
    "Transcribe all text in this document image exactly as written, preserving "
    "line breaks. Output only the transcription, no commentary.",
)


class GLMOCRUnavailable(RuntimeError):
    """Raised when transcription is requested but GLM-OCR cannot run."""


class GLMOCREngine:
    def __init__(self, host: str = DEFAULT_OLLAMA_HOST, model: str = DEFAULT_MODEL,
                 timeout: float = DEFAULT_TIMEOUT, max_side: int = DEFAULT_MAX_SIDE,
                 num_predict: int = DEFAULT_NUM_PREDICT):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_side = max_side
        self.num_predict = num_predict

    def _encode_image(self, image_path: str) -> str:
        """Resize the longest side to fit the model context, return base64 JPEG."""
        import io
        from PIL import Image

        with Image.open(image_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, self.max_side / max(w, h)) if max(w, h) else 1.0
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _client(self):
        try:
            import requests  # noqa
            return requests
        except Exception as exc:  # pragma: no cover
            raise GLMOCRUnavailable(f"HTTP client unavailable: {exc}")

    def available(self) -> bool:
        """True if the Ollama server is reachable and the model is present."""
        try:
            requests = self._client()
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            names = [m.get("name", "") for m in resp.json().get("models", [])]
            base = self.model.split(":")[0]
            return any(self.model == n or n.split(":")[0] == base for n in names)
        except Exception:
            return False

    def status(self) -> dict:
        return {"host": self.host, "model": self.model, "available": self.available()}

    def transcribe(self, image_path: str) -> str:
        """Return the transcribed text for a page image, or raise GLMOCRUnavailable."""
        if not image_path or not os.path.exists(image_path):
            raise GLMOCRUnavailable("Image not found for GLM-OCR.")
        requests = self._client()
        try:
            b64 = self._encode_image(image_path)
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": DEFAULT_PROMPT,
                    "images": [b64],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": self.num_predict},
                },
                timeout=self.timeout,
            )
        except Exception as exc:
            raise GLMOCRUnavailable(f"Could not reach Ollama at {self.host}: {exc}")
        if resp.status_code != 200:
            raise GLMOCRUnavailable(f"GLM-OCR returned HTTP {resp.status_code}")
        text = (resp.json() or {}).get("response", "")
        if not text or not text.strip():
            raise GLMOCRUnavailable("GLM-OCR returned empty text.")
        return text.strip()


_ENGINE: Optional[GLMOCREngine] = None


def get_glm_engine() -> GLMOCREngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = GLMOCREngine()
    return _ENGINE
