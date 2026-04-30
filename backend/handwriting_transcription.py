"""
Local handwriting transcription layer.

The engine keeps EasyOCR as the deterministic baseline and optionally uses a
local vision-language model for cleaner full-page handwriting transcription.
No cloud services or paid APIs are called.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_QWEN_MLX_MODEL = os.getenv(
    "HANDWRITING_VLM_MODEL",
    "mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
)
VLM_TIMEOUT_SECONDS = int(os.getenv("HANDWRITING_VLM_TIMEOUT", "180"))

TRANSCRIPTION_PROMPT = """You are transcribing a UK council handwritten document.
Return ONLY valid JSON. Do not use markdown.

Schema:
{
  "full_text": "clean transcription preserving line breaks and paragraphs",
  "lines": [
    {"line_no": 1, "text": "line text", "confidence": 0.0-1.0, "pii_hint": false, "field_label": ""}
  ],
  "fields": [
    {"label": "Full Name", "value": "Example Name", "type": "person_name", "confidence": 0.0-1.0}
  ],
  "document_type_guess": "housing_repairs|council_tax|parking|complaint|waste|adult_social_care|children_safeguarding|foi_legal|translation|unknown",
  "needs_review_reason": ""
}

Rules:
- Preserve the letter layout as readable text.
- Extract names, addresses, phones, emails, DOB, NHS/NIN/national IDs, vehicle/PCN refs, council refs, medical details, safeguarding details, signatures.
- Keep labels separate from values in fields.
- Use "unknown" if unsure.
"""


@dataclass
class TranscriptionResult:
    """Structured handwritten transcription result."""

    backend: str
    available: bool
    full_text: str
    lines: list[dict[str, Any]]
    fields: list[dict[str, Any]]
    document_type_guess: str
    confidence: float
    needs_review_reason: str
    elapsed_ms: int
    raw_response: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serialisable result."""
        return {
            "backend": self.backend,
            "available": self.available,
            "full_text": self.full_text,
            "lines": self.lines,
            "fields": self.fields,
            "document_type_guess": self.document_type_guess,
            "confidence": self.confidence,
            "needs_review_reason": self.needs_review_reason,
            "elapsed_ms": self.elapsed_ms,
            "raw_response": self.raw_response,
            "error": self.error,
        }


class HandwritingTranscriptionEngine:
    """Pluggable handwriting transcription engine with safe local fallbacks."""

    def __init__(self, backend: str | None = None) -> None:
        self.backend = backend or os.getenv("HANDWRITING_TRANSCRIPTION_BACKEND", "auto")
        self.model_name = DEFAULT_QWEN_MLX_MODEL
        self._mlx_available = self._detect_mlx_vlm()
        logger.info(
            "Handwriting transcription backend=%s mlx_available=%s model=%s",
            self.backend,
            self._mlx_available,
            self.model_name,
        )

    @property
    def available(self) -> bool:
        """Whether a non-baseline VLM backend is available."""
        return self._mlx_available or bool(os.getenv("HANDWRITING_VLM_COMMAND"))

    def transcribe(self, image_path: str, ocr_result: dict[str, Any]) -> TranscriptionResult:
        """
        Transcribe a handwritten document.

        Uses local Qwen/MLX if available, otherwise returns a structured EasyOCR
        baseline so downstream exports still work.
        """
        if self.backend in ("auto", "qwen_vlm_mlx") and self.available:
            result = self._transcribe_qwen_mlx(image_path)
            if result.available and result.full_text.strip():
                return result
            logger.warning("VLM transcription unavailable; falling back: %s", result.error)
        return self._baseline_from_easyocr(ocr_result)

    def _detect_mlx_vlm(self) -> bool:
        """Check whether mlx-vlm import is available without loading a model."""
        try:
            import mlx_vlm  # noqa: F401

            return True
        except Exception:
            return False

    def _transcribe_qwen_mlx(self, image_path: str) -> TranscriptionResult:
        """Run local Qwen2.5-VL through MLX-VLM or a configured command."""
        start = time.perf_counter()
        raw = ""
        try:
            command_template = os.getenv("HANDWRITING_VLM_COMMAND")
            if command_template:
                raw = self._run_vlm_command(command_template, image_path)
            else:
                raw = self._run_mlx_vlm_python(image_path)
            parsed = self._parse_json_response(raw)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return self._result_from_parsed(
                parsed=parsed,
                backend="qwen_vlm_mlx",
                available=True,
                elapsed_ms=elapsed_ms,
                raw_response=raw,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return TranscriptionResult(
                backend="qwen_vlm_mlx",
                available=False,
                full_text="",
                lines=[],
                fields=[],
                document_type_guess="unknown",
                confidence=0.0,
                needs_review_reason="VLM transcription failed; EasyOCR fallback used.",
                elapsed_ms=elapsed_ms,
                raw_response=raw,
                error=str(exc),
            )

    def _run_vlm_command(self, command_template: str, image_path: str) -> str:
        """Run a user-configured local VLM command with placeholders."""
        command = command_template.format(
            image=shlex.quote(image_path),
            model=shlex.quote(self.model_name),
            prompt=shlex.quote(TRANSCRIPTION_PROMPT),
        )
        completed = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=VLM_TIMEOUT_SECONDS,
        )
        return completed.stdout.strip()

    def _run_mlx_vlm_python(self, image_path: str) -> str:
        """
        Run MLX-VLM via its Python API.

        The API has changed across versions, so this method is intentionally
        defensive and falls back if the installed package is incompatible.
        """
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config

        model, processor = load(self.model_name)
        config = load_config(self.model_name)
        formatted_prompt = apply_chat_template(
            processor,
            config,
            TRANSCRIPTION_PROMPT,
            num_images=1,
        )
        response = generate(
            model,
            processor,
            formatted_prompt,
            [image_path],
            max_tokens=1600,
            temperature=0.0,
            verbose=False,
        )
        return str(response).strip()

    def _baseline_from_easyocr(self, ocr_result: dict[str, Any]) -> TranscriptionResult:
        """Build structured output from the existing EasyOCR result."""
        start = time.perf_counter()
        words = ocr_result.get("words") or []
        full_text = self._join_words_as_lines(words) or ocr_result.get("full_text", "")
        avg_conf = float(ocr_result.get("average_confidence") or 0.0)
        lines = [
            {
                "line_no": i + 1,
                "text": line,
                "confidence": avg_conf,
                "pii_hint": self._line_has_pii_hint(line),
                "field_label": self._field_label_for_line(line),
            }
            for i, line in enumerate(full_text.splitlines() if full_text else [])
        ]
        review_reason = ""
        if avg_conf < 0.65:
            review_reason = "Low handwriting OCR confidence; review clean transcription."
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return TranscriptionResult(
            backend="easyocr_baseline",
            available=True,
            full_text=full_text,
            lines=lines,
            fields=[],
            document_type_guess="unknown",
            confidence=avg_conf,
            needs_review_reason=review_reason,
            elapsed_ms=elapsed_ms,
        )

    def _join_words_as_lines(self, words: list[dict[str, Any]]) -> str:
        """Reconstruct rough lines from EasyOCR word boxes."""
        if not words:
            return ""
        ordered = sorted(words, key=lambda w: (self._bbox_y_mid(w), self._bbox_x_min(w)))
        lines: list[list[dict[str, Any]]] = []
        for word in ordered:
            y_mid = self._bbox_y_mid(word)
            placed = False
            for line in lines:
                line_y = sum(self._bbox_y_mid(w) for w in line) / max(len(line), 1)
                line_h = max(self._bbox_height(w) for w in line) or 12
                if abs(y_mid - line_y) <= max(10, line_h * 0.65):
                    line.append(word)
                    placed = True
                    break
            if not placed:
                lines.append([word])
        rendered: list[str] = []
        for line in lines:
            line_words = sorted(line, key=self._bbox_x_min)
            rendered.append(" ".join(str(w.get("text", "")).strip() for w in line_words).strip())
        return "\n".join(line for line in rendered if line)

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        """Parse a VLM JSON response that may contain accidental fences/noise."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("VLM response JSON was not an object")
        return parsed

    def _result_from_parsed(
        self,
        parsed: dict[str, Any],
        backend: str,
        available: bool,
        elapsed_ms: int,
        raw_response: str,
    ) -> TranscriptionResult:
        """Normalise parsed VLM output."""
        lines = parsed.get("lines") if isinstance(parsed.get("lines"), list) else []
        fields = parsed.get("fields") if isinstance(parsed.get("fields"), list) else []
        confidences = [
            float(item.get("confidence"))
            for item in lines + fields
            if isinstance(item, dict) and isinstance(item.get("confidence"), (int, float))
        ]
        confidence = sum(confidences) / len(confidences) if confidences else 0.78
        full_text = str(parsed.get("full_text") or "").strip()
        if not full_text and lines:
            full_text = "\n".join(str(item.get("text", "")) for item in lines if isinstance(item, dict))
        needs_review_reason = str(parsed.get("needs_review_reason") or "").strip()
        if confidence < 0.7 and not needs_review_reason:
            needs_review_reason = "VLM transcription confidence below threshold."
        return TranscriptionResult(
            backend=backend,
            available=available,
            full_text=full_text,
            lines=lines,
            fields=fields,
            document_type_guess=str(parsed.get("document_type_guess") or "unknown"),
            confidence=round(confidence, 4),
            needs_review_reason=needs_review_reason,
            elapsed_ms=elapsed_ms,
            raw_response=raw_response,
        )

    def _line_has_pii_hint(self, line: str) -> bool:
        """Simple hints used in baseline output."""
        lowered = line.lower()
        return any(
            token in lowered
            for token in (
                "name",
                "address",
                "email",
                "phone",
                "dob",
                "birth",
                "signature",
                "ref",
                "allergy",
                "medical",
                "nhs",
                "national id",
            )
        )

    def _field_label_for_line(self, line: str) -> str:
        """Return a likely field label from a line."""
        if ":" in line:
            return line.split(":", 1)[0].strip()
        lowered = line.lower()
        for label in ("name", "address", "email", "phone", "date", "signature", "notes"):
            if lowered.startswith(label):
                return label
        return ""

    def _bbox_x_min(self, word: dict[str, Any]) -> float:
        points = word.get("bbox") or [[0, 0]]
        return min(float(p[0]) for p in points)

    def _bbox_y_mid(self, word: dict[str, Any]) -> float:
        points = word.get("bbox") or [[0, 0]]
        ys = [float(p[1]) for p in points]
        return (min(ys) + max(ys)) / 2

    def _bbox_height(self, word: dict[str, Any]) -> float:
        points = word.get("bbox") or [[0, 0]]
        ys = [float(p[1]) for p in points]
        return max(ys) - min(ys)
