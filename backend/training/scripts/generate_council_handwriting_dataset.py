from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from training_utils import write_jsonl


FAKE_NAMES = [
    "Avery Demo",
    "Morgan Sample",
    "Taylor Fiction",
    "Jordan Example",
    "Riley Test",
]
FAKE_CHILDREN = ["Sam Demo", "Jamie Sample", "Casey Fiction", "Robin Example"]
FAKE_STREETS = [
    "12 Example Road, Testford TF1 2AA",
    "Flat 4, 99 Sample Street, Demo Town DT4 8ZZ",
    "20 Fiction Avenue, Placeholder PE2 5XX",
]
DOCUMENT_TYPES = [
    "foi_letter",
    "sar_request",
    "housing_repair",
    "parking_appeal",
    "social_care_note",
    "safeguarding_note",
    "mixed_form",
]


@dataclass
class TextItem:
    text: str
    pii_type: str | None = None
    expected_action: str | None = None
    review_reason: str | None = None


def load_font(size: int, handwritten: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoepr.ttf" if handwritten else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/comic.ttf" if handwritten else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def fake_values(rng: random.Random) -> dict[str, str]:
    name = rng.choice(FAKE_NAMES)
    child = rng.choice(FAKE_CHILDREN)
    return {
        "person_name": name,
        "child_name": child,
        "address": rng.choice(FAKE_STREETS),
        "phone": "07123 456789",
        "email": f"{name.split()[0].lower()}.demo@example.invalid",
        "dob": "12/04/1986",
        "nhs_number": "485 777 3456",
        "nin": "QQ 12 34 56 C",
        "case_reference": f"SYN-{rng.randint(100000, 999999)}",
        "council_ref": f"COU-{rng.randint(1000, 9999)}-FAKE",
        "medical_details": "asthma symptoms and anxiety were discussed",
        "safeguarding_context": f"{child}, age {rng.randint(7, 15)}, may be at risk after missed school visits",
        "signature": name,
    }


def build_document(doc_type: str, values: dict[str, str]) -> list[TextItem]:
    header = [
        TextItem("Synthetiq Training Council"),
        TextItem("Synthetic document - no real personal data"),
        TextItem(f"Council ref: {values['council_ref']}", "council_ref", "redact_value", "council reference"),
    ]
    if doc_type == "foi_letter":
        body = [
            TextItem("Freedom of Information request"),
            TextItem(f"Requester name: {values['person_name']}", "person_name", "redact_value", "requester name"),
            TextItem(f"Email: {values['email']}", "email", "redact_value", "email"),
            TextItem("Please provide parking enforcement policy documents for 2025."),
        ]
    elif doc_type == "sar_request":
        body = [
            TextItem("Subject Access Request"),
            TextItem(f"Full name: {values['person_name']}", "person_name", "redact_value", "data subject name"),
            TextItem(f"Date of birth: {values['dob']}", "dob", "redact_value", "date of birth"),
            TextItem(f"Address: {values['address']}", "address", "redact_value", "home address"),
        ]
    elif doc_type == "housing_repair":
        body = [
            TextItem("Housing repair complaint"),
            TextItem(f"Tenant: {values['person_name']}", "person_name", "redact_value", "tenant name"),
            TextItem(f"Phone: {values['phone']}", "phone", "redact_value", "phone number"),
            TextItem(f"Property: {values['address']}", "address", "redact_value", "property address"),
            TextItem("Repair issue: damp wall in bedroom and leaking window frame."),
        ]
    elif doc_type == "parking_appeal":
        body = [
            TextItem("Parking appeal handwritten note"),
            TextItem(f"Applicant: {values['person_name']}", "person_name", "redact_value", "applicant name"),
            TextItem(f"Case reference: {values['case_reference']}", "case_reference", "redact_value", "case reference"),
            TextItem("I believe the ticket was issued while the bay sign was covered."),
        ]
    elif doc_type == "social_care_note":
        body = [
            TextItem("Social care visit note"),
            TextItem(f"Resident: {values['person_name']}", "person_name", "redact_value", "resident name"),
            TextItem(f"NHS number: {values['nhs_number']}", "nhs_number", "redact_value", "NHS number"),
            TextItem(f"Medical note: {values['medical_details']}", "medical_details", "review", "medical details"),
        ]
    elif doc_type == "safeguarding_note":
        body = [
            TextItem("Safeguarding style note"),
            TextItem(f"Child: {values['child_name']}", "child_name", "redact_value", "child name"),
            TextItem(f"Concern: {values['safeguarding_context']}", "safeguarding_context", "review", "safeguarding context"),
            TextItem(f"Parent contact: {values['phone']}", "phone", "redact_value", "phone number"),
        ]
    else:
        body = [
            TextItem("Mixed typed and handwritten form"),
            TextItem(f"Name: {values['person_name']}", "person_name", "redact_value", "name"),
            TextItem(f"NI number: {values['nin']}", "nin", "redact_value", "NI number"),
            TextItem(f"Signature: {values['signature']}", "signature", "review", "signature"),
        ]
    return header + [TextItem("")] + body


def draw_noisy_page(
    items: list[TextItem],
    out_path: Path,
    answer_key_path: Path,
    doc_type: str,
    rng: random.Random,
    page_number: int,
) -> dict[str, Any]:
    width, height = 1654, 2339
    image = Image.new("RGB", (width, height), (248, 247, 242))
    draw = ImageDraw.Draw(image)
    typed_font = load_font(38, handwritten=False)
    handwritten_font = load_font(42, handwritten=True)
    small_font = load_font(28, handwritten=False)

    draw.rectangle((80, 80, width - 80, height - 80), outline=(210, 210, 205), width=2)
    draw.text((110, 110), "LOCAL COUNCIL CASEWORK", fill=(20, 30, 40), font=small_font)

    y = 210
    pii_items: list[dict[str, Any]] = []
    line_rows: list[dict[str, Any]] = []
    full_text_parts: list[str] = []

    for index, item in enumerate(items):
        text = item.text
        font = handwritten_font if index > 3 and rng.random() < 0.72 else typed_font
        x = 135 + rng.randint(-12, 16)
        if not text:
            y += 36
            continue
        bbox = draw.textbbox((x, y), text, font=font)
        draw.text((x, y), text, fill=(24, 28, 35), font=font)
        full_text_parts.append(text)

        line_bbox = [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
        if item.pii_type:
            value = text.split(":", 1)[-1].strip() if ":" in text else text
            value_prefix = text[: max(0, text.find(value))]
            prefix_bbox = draw.textbbox((x, y), value_prefix, font=font) if value_prefix else (x, y, x, y)
            value_bbox = [int(prefix_bbox[2]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
            pii_items.append(
                {
                    "value": value,
                    "type": item.pii_type,
                    "page_number": page_number,
                    "bbox": value_bbox,
                    "expected_redaction_action": item.expected_action,
                    "expected_review_reason": item.review_reason,
                }
            )
        line_rows.append(
            {
                "image_path": str(out_path.resolve()),
                "text": text,
                "split": "test",
                "source": "synthetic_council",
                "licence": "synthetic_generated_by_synthetiq_no_real_personal_data",
                "document_type": doc_type,
                "page_number": page_number,
                "line_bbox": line_bbox,
                "word_bboxes": [],
                "pii_items": [],
                "synthetic": True,
            }
        )
        y += rng.randint(64, 88)

    if rng.random() < 0.9:
        angle = rng.uniform(-2.2, 2.2)
        image = image.rotate(angle, expand=False, fillcolor=(248, 247, 242))
    if rng.random() < 0.55:
        image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.25, 0.8)))
    if rng.random() < 0.55:
        shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rectangle((0, 0, width, height), fill=(0, 0, 0, rng.randint(8, 22)))
        image = Image.alpha_composite(image.convert("RGBA"), shadow).convert("RGB")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)

    answer_key = {
        "image_path": str(out_path.resolve()),
        "document_type": doc_type,
        "page_number": page_number,
        "correct_full_text": "\n".join(full_text_parts),
        "pii_items": pii_items,
        "synthetic": True,
    }
    answer_key_path.parent.mkdir(parents=True, exist_ok=True)
    answer_key_path.write_text(json.dumps(answer_key, indent=2), encoding="utf-8")

    for row in line_rows:
        line_pii = []
        line_bbox = row["line_bbox"]
        for pii in pii_items:
            px0, py0, px1, py1 = pii["bbox"]
            lx0, ly0, lx1, ly1 = line_bbox
            if py0 >= ly0 - 4 and py1 <= ly1 + 4 and px1 >= lx0 and px0 <= lx1:
                line_pii.append(pii)
        row["pii_items"] = line_pii
    return {"answer_key": answer_key, "manifest_rows": line_rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fake council-style handwriting OCR pages and answer keys.")
    parser.add_argument("--output-dir", default="backend/training/datasets/synthetic_council")
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split", default="test", choices=["train", "validation", "test"])
    args = parser.parse_args()

    rng = random.Random(args.seed)
    output_dir = Path(args.output_dir)
    image_dir = output_dir / "images"
    answer_dir = output_dir / "answer_keys"
    manifest_rows: list[dict[str, Any]] = []
    answer_keys: list[dict[str, Any]] = []

    for index in range(args.count):
        doc_type = DOCUMENT_TYPES[index % len(DOCUMENT_TYPES)]
        values = fake_values(rng)
        items = build_document(doc_type, values)
        image_path = image_dir / f"synthetic_{index:04d}_{doc_type}.png"
        answer_path = answer_dir / f"synthetic_{index:04d}_{doc_type}.json"
        generated = draw_noisy_page(items, image_path, answer_path, doc_type, rng, page_number=1)
        for row in generated["manifest_rows"]:
            row["split"] = args.split
        manifest_rows.extend(generated["manifest_rows"])
        answer_keys.append(generated["answer_key"])

    manifest_path = output_dir / "manifest.jsonl"
    write_jsonl(manifest_path, manifest_rows)
    summary_path = output_dir / "summary.json"
    summary = {
        "dataset": "synthetic_council",
        "documents": args.count,
        "manifest_rows": len(manifest_rows),
        "manifest_path": str(manifest_path.resolve()),
        "answer_keys": len(answer_keys),
        "document_types": DOCUMENT_TYPES,
        "no_real_personal_data": True,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
