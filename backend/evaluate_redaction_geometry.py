"""
Fast geometry regression tests for image redaction boxes.

This avoids OCR and checks the handwriting safety fallback directly. The goal is
to prevent page-wide black blocks while still masking likely PII lines.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

from redaction import RedactionEngine


OUT_DIR = Path("data/processed/geometry_eval")


def _box(text: str, x0: int, y0: int, x1: int, y1: int, confidence: float = 0.42) -> dict:
    return {
        "text": text,
        "bbox": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "confidence": confidence,
    }


def _black_components(path: Path) -> list[tuple[int, int, int, int, int]]:
    image = cv2.imread(str(path))
    if image is None:
        raise AssertionError(f"Could not read {path}")
    mask = np.all(image < 8, axis=2).astype("uint8")
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    components = []
    for idx in range(1, count):
        x, y, w, h, area = stats[idx]
        if area >= 20:
            components.append((int(x), int(y), int(w), int(h), int(area)))
    return components


def _black_ratio(path: Path, rect: tuple[int, int, int, int]) -> float:
    image = cv2.imread(str(path))
    if image is None:
        raise AssertionError(f"Could not read {path}")
    x0, y0, x1, y1 = rect
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0
    return float(np.all(crop < 8, axis=2).mean())


def run_synthetic_handwriting_geometry() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = OUT_DIR / "handwritten_letter_base.png"
    output_path = OUT_DIR / "handwritten_letter_redacted.png"

    image = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    cv2.imwrite(str(image_path), image)
    cv2.imwrite(str(output_path), image)

    blocks = [
        _box("23 June 2026", 140, 90, 330, 125),
        _box("Aisha Rahman", 140, 165, 340, 205),
        _box("42 Willowbrook Road", 140, 215, 440, 255),
        _box("Hayes", 140, 265, 230, 305),
        _box("UB3 2FA", 140, 315, 260, 355),
        _box("Phone:", 140, 405, 230, 445),
        _box("07700 900 482", 245, 405, 455, 445),
        _box("Email:", 140, 455, 225, 495),
        _box("aisha.rahman.fake@example.com", 240, 455, 635, 495),
        _box("Date of birth:", 140, 505, 330, 545),
        _box("14 March 1987", 345, 505, 560, 545),
        _box("Council reference:", 140, 555, 390, 595),
        _box("HILL-FOI-28491", 405, 555, 650, 595),
        _box("To the Information Governance Team,", 140, 655, 620, 695),
        _box("Subject: Subject Access Request", 140, 730, 620, 770),
        _box("My son Adam Rahman age 9 has asthma", 140, 905, 720, 945),
        _box("and the damp made breathing worse", 140, 955, 650, 995),
        _box("Yours sincerely,", 140, 1200, 365, 1240),
        _box("Aisha Rahman", 140, 1260, 360, 1310),
    ]

    engine = RedactionEngine()
    changed = engine.handwriting_safety_pass(
        str(output_path),
        blocks,
        avg_confidence=0.42,
        allowed_types={
            "person_name",
            "address",
            "phone",
            "email",
            "dob",
            "council_ref",
            "signature",
            "medical_details",
            "notes",
        },
    )
    if not changed:
        raise AssertionError("Expected safety pass to apply redactions")

    components = _black_components(output_path)
    if not components:
        raise AssertionError("Expected black redaction boxes")

    max_width = max(width for _, _, width, _, _ in components)
    max_height = max(height for _, _, _, height, _ in components)
    max_area = max(area for *_, area in components)

    if max_width > 760:
        raise AssertionError(f"Redaction component too wide: {max_width}px")
    if max_height > 130:
        raise AssertionError(f"Redaction component too tall: {max_height}px")
    if max_area > 75_000:
        raise AssertionError(f"Redaction component too large: {max_area}px")

    # Date line should remain mostly visible; previous bug blacked the full top.
    date_black_ratio = _black_ratio(output_path, (0, 60, 1000, 145))
    if date_black_ratio > 0.05:
        raise AssertionError(f"Date/top line over-redacted: {date_black_ratio:.3f}")

    # Sender address continuation lines must be masked even when one line is
    # not a clean street/postcode regex match.
    town_black_ratio = _black_ratio(output_path, (125, 255, 260, 315))
    postcode_black_ratio = _black_ratio(output_path, (125, 305, 285, 365))
    if town_black_ratio < 0.35:
        raise AssertionError(f"Town/address continuation not redacted: {town_black_ratio:.3f}")
    if postcode_black_ratio < 0.35:
        raise AssertionError(f"Postcode/address continuation not redacted: {postcode_black_ratio:.3f}")

    # Signature should be redacted, but the entire bottom of the page should not.
    bottom_black_ratio = _black_ratio(output_path, (0, 1180, 1000, 1400))
    if bottom_black_ratio > 0.12:
        raise AssertionError(f"Bottom region over-redacted: {bottom_black_ratio:.3f}")

    return {
        "changed": changed,
        "component_count": len(components),
        "max_component_width": max_width,
        "max_component_height": max_height,
        "max_component_area": max_area,
        "date_black_ratio": round(date_black_ratio, 4),
        "town_black_ratio": round(town_black_ratio, 4),
        "postcode_black_ratio": round(postcode_black_ratio, 4),
        "bottom_black_ratio": round(bottom_black_ratio, 4),
        "output_path": str(output_path),
    }


def run_field_label_line_bleed_geometry() -> dict:
    words = [
        _box("Date", 119, 455, 191, 491, confidence=0.77),
        _box("of", 204, 456, 240, 488, confidence=0.55),
        _box("birth :", 259, 453, 351, 489, confidence=0.81),
        _box("14", 372, 454, 408, 486, confidence=0.99),
        _box("March", 423, 449, 511, 487, confidence=0.99),
        _box("1987", 523, 443, 591, 481, confidence=0.99),
        _box("Counc; |", 121, 501, 233, 541, confidence=0.73),
        _box("reference :", 248, 495, 407, 539, confidence=0.98),
        _box("HILL-Fol-28491", 425, 490, 657, 533, confidence=0.77),
    ]
    flat_text = " ".join(word["text"] for word in words)

    engine = RedactionEngine()
    spans = engine.detect_sensitive_text(
        flat_text,
        llm_engine=None,
        allowed_types={"dob", "council_ref"},
    )
    redactions = engine.map_to_bboxes(spans, words)

    dob_boxes = [
        box["bbox"]
        for redaction in redactions
        if redaction["type"] == "dob"
        for box in redaction["bboxes"]
    ]
    if not dob_boxes:
        raise AssertionError("Expected a DOB redaction box")

    for bbox in dob_boxes:
        ys = [point[1] for point in bbox]
        if max(ys) >= 495:
            raise AssertionError(f"DOB redaction leaked into next visual line: {bbox}")

    return {
        "dob_box_count": len(dob_boxes),
        "max_dob_y": max(max(point[1] for point in bbox) for bbox in dob_boxes),
    }


def main() -> None:
    result = run_synthetic_handwriting_geometry()
    print("PASS handwriting_geometry")
    for key, value in result.items():
        print(f"{key}: {value}")
    bleed_result = run_field_label_line_bleed_geometry()
    print("PASS field_label_line_bleed")
    for key, value in bleed_result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
