"""
Image-based redaction detector service.

Wraps the locally trained YOLO/Ultralytics detector that predicts "sensitive"
regions on document page images. This is a *review-assist* layer only: the pilot
model is not production accurate (precision ~0.53, recall ~0.66), so every box it
produces must be inserted as a pending redaction and reviewed by a human.

Design goals:
- Lazy load. The model is only loaded the first time a prediction is requested,
  so importing this module (and starting the backend) never fails because of a
  missing model file or a missing `ultralytics` install.
- Graceful degradation. If the model or ultralytics is unavailable, callers get a
  clear "unavailable" signal instead of a crash.
- Server-side configuration only. The model path comes from environment variables
  or a known local fallback; it is never accepted from API input.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any


# Class label produced by predictions. Kept distinct from OCR/manual types so the
# review UI and audit trail can tell model candidates apart.
REDACTION_TYPE = "model_sensitive"
DETECTION_METHOD = "image_detector_yolo"

# Environment variable names checked, in order, for the model path.
MODEL_PATH_ENV_VARS = (
    "SYNTHETIQ_REDACT_DETECTOR_MODEL",
    "SYNTHTIQ_REDACT_DETECTOR_MODEL",  # tolerate the shortened spelling
    "REDACTION_DETECTOR_MODEL",
)

# Local fallback: the best trained pilot artifact on this machine.
DEFAULT_MODEL_PATH = str(
    Path(__file__).resolve().parent
    / "training"
    / "models"
    / "synthetiq-redaction-detector-runpod-a100-20260626"
    / "synthetiq-redaction-detector"
    / "weights"
    / "best.pt"
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "").strip() or default))
    except (TypeError, ValueError):
        return default


def _resolve_model_path() -> Optional[str]:
    """Return the configured model path, or None if nothing usable is found."""
    for var in MODEL_PATH_ENV_VARS:
        value = os.environ.get(var, "").strip()
        if value:
            return value
    if os.path.exists(DEFAULT_MODEL_PATH):
        return DEFAULT_MODEL_PATH
    return None


class DetectorUnavailableError(RuntimeError):
    """Raised when a prediction is requested but the detector cannot run."""


class ImageRedactionDetector:
    """Lazily-loaded wrapper around the trained Ultralytics detector."""

    def __init__(self) -> None:
        self._model = None
        self._load_attempted = False
        self._unavailable_reason: Optional[str] = None
        self._lock = threading.Lock()

        # Configurable inference settings (server-side only).
        self.conf_threshold = _env_float("REDACTION_DETECTOR_CONF", 0.25)
        self.padding = _env_int("REDACTION_DETECTOR_PADDING", 6)
        self.imgsz = _env_int("REDACTION_DETECTOR_IMGSZ", 1280)
        self.model_path = _resolve_model_path()

    # -- availability -------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load the model once; record a reason if it cannot be loaded."""
        if self._load_attempted:
            return
        with self._lock:
            if self._load_attempted:
                return
            self._load_attempted = True

            if not self.model_path or not os.path.exists(self.model_path):
                self._unavailable_reason = (
                    "Redaction detector model file is not available on the server."
                )
                return
            try:
                from ultralytics import YOLO  # type: ignore
            except Exception:  # pragma: no cover - depends on optional install
                self._unavailable_reason = (
                    "Image redaction detector is not installed on the server."
                )
                return
            try:
                self._model = YOLO(self.model_path)
            except Exception as exc:  # pragma: no cover - load failure
                self._unavailable_reason = f"Redaction detector failed to load: {exc}"
                self._model = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._model is not None

    @property
    def unavailable_reason(self) -> Optional[str]:
        self._ensure_loaded()
        return self._unavailable_reason

    def status(self) -> Dict[str, Any]:
        """Lightweight status payload safe to log (no absolute paths exposed)."""
        return {
            "available": self.available,
            "reason": self._unavailable_reason,
            "conf_threshold": self.conf_threshold,
            "padding": self.padding,
        }

    # -- prediction ---------------------------------------------------------

    def predict(self, image_path: str, page_number: int = 1) -> List[Dict[str, Any]]:
        """
        Run detection on a single page image.

        Returns a list of prediction dicts. Each contains both a DB-ready bbox in
        the app's four-corner format and plain x/y/w/h for drawing/testing:

            {
                "bbox": {"bbox": [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]},
                "x": int, "y": int, "w": int, "h": int,
                "confidence": float,
                "redaction_type": "model_sensitive",
                "method": "image_detector_yolo",
                "page_number": int,
            }

        Raises DetectorUnavailableError if the model cannot run.
        """
        self._ensure_loaded()
        if self._model is None:
            raise DetectorUnavailableError(
                self._unavailable_reason or "Redaction detector is unavailable."
            )
        if not image_path or not os.path.exists(image_path):
            raise DetectorUnavailableError("Page image is not available for detection.")

        # Clamp boxes to the real image dimensions.
        from PIL import Image

        with Image.open(image_path) as img:
            max_w, max_h = img.size

        results = self._model.predict(
            source=image_path,
            imgsz=self.imgsz,
            conf=self.conf_threshold,
            verbose=False,
        )

        predictions: List[Dict[str, Any]] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                try:
                    xyxy = box.xyxy[0].tolist()
                    confidence = float(box.conf[0].item())
                except Exception:
                    continue
                if len(xyxy) != 4:
                    continue
                x0, y0, x1, y1 = xyxy
                # Pad so boxes fully cover handwriting, then clamp to image bounds.
                x0 = max(0.0, min(float(x0) - self.padding, float(max_w)))
                y0 = max(0.0, min(float(y0) - self.padding, float(max_h)))
                x1 = max(0.0, min(float(x1) + self.padding, float(max_w)))
                y1 = max(0.0, min(float(y1) + self.padding, float(max_h)))
                if x1 - x0 < 2 or y1 - y0 < 2:
                    continue

                xi, yi = int(round(x0)), int(round(y0))
                wi, hi = int(round(x1 - x0)), int(round(y1 - y0))
                predictions.append(
                    {
                        "bbox": {
                            "bbox": [
                                [round(x0, 2), round(y0, 2)],
                                [round(x1, 2), round(y0, 2)],
                                [round(x1, 2), round(y1, 2)],
                                [round(x0, 2), round(y1, 2)],
                            ]
                        },
                        "x": xi,
                        "y": yi,
                        "w": wi,
                        "h": hi,
                        "confidence": round(confidence, 4),
                        "redaction_type": REDACTION_TYPE,
                        "method": DETECTION_METHOD,
                        "page_number": page_number,
                    }
                )
        return predictions


# Module-level singleton so the model is loaded at most once per process.
_DETECTOR: Optional[ImageRedactionDetector] = None
_DETECTOR_LOCK = threading.Lock()


def get_detector() -> ImageRedactionDetector:
    global _DETECTOR
    if _DETECTOR is None:
        with _DETECTOR_LOCK:
            if _DETECTOR is None:
                _DETECTOR = ImageRedactionDetector()
    return _DETECTOR
