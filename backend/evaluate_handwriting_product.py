"""
Handwriting product evaluation harness.

Runs real-looking document images through preprocessing, EasyOCR baseline, the
optional handwriting transcription layer, and profile-aware text redaction.
Produces a report that shows transcription quality, field recall, tag use, and
whether useful redactions were created.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from document_exports import write_redacted_docx, write_text_artifacts, write_transcription_json
from handwriting_transcription import HandwritingTranscriptionEngine
from ocr_engine import OCREngine
from preprocessing import preprocess_pipeline
from redaction import RedactionEngine
from redaction_profiles import get_allowed_types, get_profiles_for_category, requires_review

TYPE_ALIASES = {
    "nhs_number": "nin",
    "pcn": "vehicle_reg",
}


@dataclass(frozen=True)
class HandwritingCase:
    """A real-image handwriting evaluation case."""

    id: str
    image_path: str
    category: str
    expected_text: str
    required_values: list[str]
    expected_redacted_values: list[str]
    expected_not_redacted_values: list[str]
    expected_types: list[str]
    expected_needs_review: bool


EXPECTED_HOUSING_LETTER = """Rafid Sorker
14 Willow Crescent
Uxbridge, UB8 2PL
Email: sorkehrafid574@gmail.com
Phone: 07456839201

Date: 12 March 2026

Dear Sir/Madam

I am writing to report a serious issue with mould in my property. I have a medically diagnosed allergy to mould and dust, and my symptoms have worsened due to the current conditions in my home.

The damp and mould are affecting my breathing and overall health. I have previously reported this issue (Ref: HILL-REQ-48389), but it has not been resolved.

I kindly request an urgent inspection.

Yours faithfully,
Rafid Sorker"""


def discover_default_cases() -> list[HandwritingCase]:
    """Return default cases from the current workspace if matching images exist."""
    candidates = [
        "data/uploads/20260429_130836_Problems.png",
        "data/uploads/20260429_130432_Screenshot 2026-04-29 at 1.59.26 pm.png",
        "data/processed/unknown/doc_15/original.png",
    ]
    base = Path(__file__).parent
    for candidate in candidates:
        path = base / candidate
        if path.exists():
            return [
                HandwritingCase(
                    id="handwritten_housing_letter",
                    image_path=str(path),
                    category="adult_social_care",
                    expected_text=EXPECTED_HOUSING_LETTER,
                    required_values=[
                        "Rafid Sorker",
                        "14 Willow Crescent",
                        "UB8 2PL",
                        "sorkehrafid574@gmail.com",
                        "07456839201",
                        "HILL-REQ-48389",
                        "medically diagnosed allergy",
                        "breathing and overall health",
                    ],
                    expected_redacted_values=[
                        "Rafid Sorker",
                        "14 Willow Crescent",
                        "UB8 2PL",
                        "sorkehrafid574@gmail.com",
                        "07456839201",
                        "HILL-REQ-48389",
                        "medically diagnosed allergy",
                        "breathing and overall health",
                    ],
                    expected_not_redacted_values=[
                        "Date: 12 March 2026",
                        "Dear Sir/Madam",
                        "urgent inspection",
                    ],
                    expected_types=[
                        "person_name",
                        "address",
                        "email",
                        "phone",
                        "council_ref",
                        "notes",
                    ],
                    expected_needs_review=True,
                )
            ]
    return []


def _load_demo_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a readable local font for synthetic handwritten-style cases."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
        "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _write_demo_image(path: Path, text: str, *, messy: bool = False) -> None:
    """Create a synthetic local handwritten-style document image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    font = _load_demo_font(30 if not messy else 27)
    width, height = 1200, 1600
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    for y in range(80, height - 80, 62):
        draw.line((70, y, width - 70, y + (6 if messy and y % 3 == 0 else 0)), fill=(205, 210, 215), width=2)

    y = 80
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            y += 42
            continue
        x = 85 + ((index % 3) * 7 if messy else 0)
        draw.text((x, y), line, fill=(25, 28, 32), font=font)
        y += 46 if messy else 52

    if messy:
        draw.line((90, 420, 850, 405), fill=(90, 90, 90), width=2)
        draw.ellipse((920, 120, 1030, 210), outline=(220, 205, 180), width=8)

    image.save(path)


def generated_demo_cases(out_root: str) -> list[HandwritingCase]:
    """Create and return a broader synthetic handwritten benchmark pack."""
    root = Path(out_root) / "generated_inputs"
    definitions = [
        {
            "id": "generated_housing",
            "category": "housing_repairs",
            "text": """Maya Patel
31 Demo Road
Uxbridge UB8 1ZZ
Email: maya.patel.demo@example.com
Phone: 07700 111222

Date: 3 April 2026

I am reporting mould and no heating in the bedroom.
Reference: REF-448812
Please arrange an urgent repair visit.""",
            "required": ["Maya Patel", "31 Demo Road", "UB8 1ZZ", "maya.patel.demo@example.com", "07700 111222", "REF-448812"],
            "types": ["person_name", "address", "email", "phone", "council_ref"],
            "safe": ["Date: 3 April 2026", "urgent repair"],
        },
        {
            "id": "generated_medical_social",
            "category": "adult_social_care",
            "text": """Patient Name: Omar Lewis
DOB: 09/02/1949
NHS Number: 485 777 9210
Address: 19 Demo Close, Hayes UB3 2AA
Medication: insulin and ramipril
Notes: lives alone and has dizziness at night.""",
            "required": ["Omar Lewis", "09/02/1949", "485 777 9210", "19 Demo Close", "insulin", "dizziness at night"],
            "types": ["person_name", "dob", "nhs_number", "address", "notes"],
            "safe": [],
        },
        {
            "id": "generated_parking",
            "category": "parking",
            "text": """Parking Appeal
Name: Chloe Evans
Address: 8 Demo Avenue, Ruislip HA4 0BB
PCN: PCN-HT2026-7744
Vehicle Reg: AB12 XYZ
Phone: 01895 333444
Date: 24 May 2024
I had a valid permit on display.""",
            "required": ["Chloe Evans", "8 Demo Avenue", "PCN-HT2026-7744", "AB12 XYZ", "01895 333444"],
            "types": ["person_name", "address", "phone", "vehicle_reg", "pcn"],
            "safe": ["Date: 24 May 2024", "valid permit"],
        },
        {
            "id": "generated_safeguarding",
            "category": "children_safeguarding",
            "text": """Safeguarding Concern
Child Name: Ellie Brooks
DOB: 14/10/2016
School: Demo Primary School
Address: 5 Demo Lane, Hayes UB3 4RT
Parent: Karen Brooks
The child said she feels unsafe at home.""",
            "required": ["Ellie Brooks", "14/10/2016", "Demo Primary School", "5 Demo Lane", "Karen Brooks", "unsafe at home"],
            "types": ["person_name", "dob", "school", "address", "notes"],
            "safe": [],
            "review": True,
        },
        {
            "id": "generated_hardship",
            "category": "council_tax",
            "text": """Council Tax Hardship Form
Full Name: Aisha Khan
NI Number: QQ 12 34 56 C
Bank Account: 12345678
Sort Code: 20-11-99
Email: aisha.khan.demo@example.com
I cannot afford food this month.""",
            "required": ["Aisha Khan", "QQ 12 34 56 C", "12345678", "20-11-99", "aisha.khan.demo@example.com", "cannot afford food"],
            "types": ["person_name", "nin", "bank_details", "email", "notes"],
            "safe": ["Council Tax Hardship Form"],
        },
        {
            "id": "generated_messy_complaint",
            "category": "complaint",
            "text": """To the counsil
My name is Ben Carter
I live at 44 Demo Street UB10 1XY
Phone 07700 444555
I complane about bins not collected again.
This is disgusting and ignored.""",
            "required": ["Ben Carter", "44 Demo Street", "UB10 1XY", "07700 444555"],
            "types": ["person_name", "address", "phone"],
            "safe": ["bins not collected"],
            "messy": True,
        },
        {
            "id": "generated_translation",
            "category": "translation",
            "text": """Solicitud de ayuda
Nombre: Lucia Romero
Direccion: 77 Demo Court, Uxbridge UB8 2PQ
Telefono: 07700 888999
NIN: AB123456C
No puedo pagar el alquiler este mes.""",
            "required": ["Lucia Romero", "77 Demo Court", "UB8 2PQ", "07700 888999", "AB123456C"],
            "types": ["person_name", "address", "phone", "nin"],
            "safe": ["Solicitud de ayuda"],
        },
        {
            "id": "generated_unknown_safe",
            "category": "unknown",
            "text": """Hello World
This is a synthetic safe note.
No resident details are included.
Please test the document flow only.""",
            "required": [],
            "types": [],
            "safe": ["Hello World", "synthetic safe note"],
            "review": True,
        },
    ]

    cases: list[HandwritingCase] = []
    for item in definitions:
        image_path = root / f"{item['id']}.png"
        _write_demo_image(image_path, item["text"], messy=bool(item.get("messy")))
        cases.append(
            HandwritingCase(
                id=item["id"],
                image_path=str(image_path),
                category=item["category"],
                expected_text=item["text"],
                required_values=item["required"],
                expected_redacted_values=item["required"],
                expected_not_redacted_values=item["safe"],
                expected_types=item["types"],
                expected_needs_review=bool(item.get("review", requires_review(item["category"], get_profiles_for_category(item["category"])))),
            )
        )
    return cases


def normalise(text: str) -> str:
    """Normalise text for loose OCR comparisons."""
    return " ".join(text.lower().replace(",", " ").replace(".", " ").split())


def similarity(a: str, b: str) -> float:
    """Return loose sequence similarity."""
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def contains_loose(text: str, value: str) -> bool:
    """Case-insensitive containment with whitespace normalisation."""
    return normalise(value) in normalise(text)


def evaluate_case(
    case: HandwritingCase,
    out_root: str,
    ocr: OCREngine,
    transcriber: HandwritingTranscriptionEngine,
    redaction: RedactionEngine,
) -> dict[str, Any]:
    """Run one image case through OCR/transcription/redaction evaluation."""
    start = time.perf_counter()
    case_out = os.path.join(out_root, case.id)
    os.makedirs(case_out, exist_ok=True)

    preprocessed = preprocess_pipeline(case.image_path)
    ocr_result = ocr.extract_text(preprocessed)
    transcription = transcriber.transcribe(preprocessed, ocr_result)
    clean_text = transcription.full_text or ocr_result["full_text"]

    profiles = get_profiles_for_category(case.category)
    allowed_types = get_allowed_types(profiles)
    spans = redaction.detect_sensitive_text(clean_text, llm_engine=None, allowed_types=allowed_types)
    redacted_text = redaction.redact_text(clean_text, spans)
    detected_types = {span["type"] for span in spans}
    needs_review = (
        requires_review(case.category, profiles)
        or transcription.confidence < 0.75
        or bool(transcription.needs_review_reason)
    )

    text_paths = write_text_artifacts(
        case_out,
        doc_id=0,
        raw_text=ocr_result["full_text"],
        clean_text=clean_text,
        redacted_text=redacted_text,
    )
    transcription_json = write_transcription_json(case_out, transcription.to_dict())
    docx_path = write_redacted_docx(
        case_out,
        doc_id=0,
        filename=os.path.basename(case.image_path),
        clean_text=clean_text,
        redacted_text=redacted_text,
        metadata={
            "category": case.category,
            "redaction_profile": ",".join(profiles),
            "flag_needs_review": needs_review,
        },
    )

    required_found = [value for value in case.required_values if contains_loose(clean_text, value)]
    missed_required = [value for value in case.required_values if value not in required_found]
    missed_redactions = [
        value for value in case.expected_redacted_values if contains_loose(redacted_text, value)
    ]
    safe_values_present = [
        value for value in case.expected_not_redacted_values if contains_loose(clean_text, value)
    ]
    safe_values_missing_from_ocr = [
        value for value in case.expected_not_redacted_values if value not in safe_values_present
    ]
    redacted_safe = [
        value for value in safe_values_present if not contains_loose(redacted_text, value)
    ]
    canonical_detected_types = detected_types | {TYPE_ALIASES.get(rtype, rtype) for rtype in detected_types}
    missing_types = [rtype for rtype in case.expected_types if rtype not in canonical_detected_types]
    review_ok = needs_review == case.expected_needs_review

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    result = {
        "id": case.id,
        "image_path": case.image_path,
        "category": case.category,
        "profiles": profiles,
        "backend": transcription.backend,
        "ocr_confidence": ocr_result["average_confidence"],
        "transcription_confidence": transcription.confidence,
        "similarity": similarity(clean_text, case.expected_text),
        "required_field_recall": len(required_found) / len(case.required_values) if case.required_values else 1.0,
        "required_found": required_found,
        "missed_required": missed_required,
        "missed_redactions": missed_redactions,
        "redacted_safe_values": redacted_safe,
        "safe_values_missing_from_ocr": safe_values_missing_from_ocr,
        "detected_types": sorted(detected_types),
        "missing_types": missing_types,
        "needs_review": needs_review,
        "review_ok": review_ok,
        "elapsed_ms": elapsed_ms,
        "artifacts": {
            **text_paths,
            "transcription_json_path": transcription_json,
            "redacted_docx_path": docx_path,
        },
    }
    with open(os.path.join(case_out, "evaluation.json"), "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    return result


def summarize(results: list[dict[str, Any]], out_root: str) -> dict[str, Any]:
    """Write and return aggregate handwriting report."""
    total = len(results)
    summary = {
        "case_count": total,
        "average_similarity": sum(r["similarity"] for r in results) / total if total else 0,
        "average_required_field_recall": sum(r["required_field_recall"] for r in results) / total if total else 0,
        "missed_redaction_count": sum(len(r["missed_redactions"]) for r in results),
        "false_positive_safe_redaction_count": sum(len(r["redacted_safe_values"]) for r in results),
        "missing_type_count": sum(len(r["missing_types"]) for r in results),
        "review_score": (
            sum(1 for r in results if r["review_ok"]) / total if total else 0
        ),
        "passed_demo_threshold": all(
            r["required_field_recall"] >= 0.85
            and not r["missed_redactions"]
            and not r["redacted_safe_values"]
            and r["review_ok"]
            for r in results
        )
        if results
        else False,
        "cases": results,
    }
    with open(os.path.join(out_root, "handwriting_report.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    return summary


def main() -> int:
    """Run handwriting product evaluation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", help="Optional image path to evaluate as housing/medical handwriting")
    parser.add_argument("--category", default="adult_social_care")
    parser.add_argument("--out", default=str(Path(__file__).parent / "data" / "processed" / "handwriting_eval"))
    parser.add_argument("--include-generated", action="store_true", help="Add 8 synthetic real-type handwriting benchmark cases")
    args = parser.parse_args()

    if args.image:
        cases = [
            HandwritingCase(
                id="custom_handwritten_document",
                image_path=args.image,
                category=args.category,
                expected_text=EXPECTED_HOUSING_LETTER,
                required_values=[],
                expected_redacted_values=[],
                expected_not_redacted_values=[],
                expected_types=[],
                expected_needs_review=True,
            )
        ]
    else:
        cases = discover_default_cases()
        if args.include_generated:
            cases.extend(generated_demo_cases(args.out))

    if not cases:
        print("No default handwriting images found. Pass --image /path/to/image.png.")
        return 0

    os.makedirs(args.out, exist_ok=True)
    ocr = OCREngine()
    transcriber = HandwritingTranscriptionEngine()
    redaction = RedactionEngine()
    results = [evaluate_case(case, args.out, ocr, transcriber, redaction) for case in cases]
    summary = summarize(results, args.out)

    print(json.dumps({
        "case_count": summary["case_count"],
        "average_similarity": summary["average_similarity"],
        "average_required_field_recall": summary["average_required_field_recall"],
        "missed_redaction_count": summary["missed_redaction_count"],
        "false_positive_safe_redaction_count": summary["false_positive_safe_redaction_count"],
        "missing_type_count": summary["missing_type_count"],
        "review_score": summary["review_score"],
        "passed_demo_threshold": summary["passed_demo_threshold"],
        "report_path": os.path.join(args.out, "handwriting_report.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
