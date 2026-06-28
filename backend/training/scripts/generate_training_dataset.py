"""
Generate a tight-label training dataset for the redaction detector.

Reads answer_key.json files from the document dataset, renders each document
programmatically as a handwritten-style letter with KNOWN-EXACT coordinates, and
writes YOLO-format label files with tight bounding boxes around each PII value.

Why this exists:
The original generative-AI images had no coordinate ground truth, so labels were
guessed by OCR on messy handwriting -> broad, fuzzy boxes -> the detector learned
"sensitive region" instead of "sensitive value". Here WE render the text, so we
know every box exactly. Boxes are tight by construction.

Geometric augmentation (rotation/scale/perspective/hsv) is intentionally left to
YOLO's training-time augmentation, which keeps these labels pixel-exact. We only
bake in photometric variety (fonts, ink colour, paper tint, light grain) plus
layout jitter, none of which move a labelled pixel after it is measured.

Usage:
    python backend/training/scripts/generate_training_dataset.py
Output:
    backend/training/datasets/synthetiq_redact_tight_labels/
      images/  labels/  classes.txt  data.yaml
"""

import json
import os
import random
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
except ImportError as e:
    print(f"Missing dependency: {e}. Install: pip install pillow numpy")
    raise

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATASET_ROOT = Path(__file__).parents[3] / "backend" / "training" / "datasets"
INPUT_DATASET = DATASET_ROOT / "synthetiq_redact_image_dataset"
OUTPUT_DATASET = DATASET_ROOT / "synthetiq_redact_tight_labels"
OUTPUT_IMAGES = OUTPUT_DATASET / "images"
OUTPUT_LABELS = OUTPUT_DATASET / "labels"

VARIATIONS_PER_DOC = 10
PAGE_W, PAGE_H = 1280, 1600

# ---------------------------------------------------------------------------
# Classes (index order is the YOLO class id)
# ---------------------------------------------------------------------------
CLASS_ORDER = ["person_name", "email", "phone", "address", "case_reference", "signature"]
PII_CLASSES = {name: i for i, name in enumerate(CLASS_ORDER)}

# ---------------------------------------------------------------------------
# Fonts (real Windows files). Handwriting fonts are randomised per image.
# ---------------------------------------------------------------------------
FONT_DIR = Path(r"C:\Windows\Fonts")
HANDWRITING_FONT_FILES = [
    "Inkfree.ttf", "segoepr.ttf", "segoesc.ttf", "MISTRAL.TTF",
    "LHANDW.TTF", "comic.ttf", "Gabriola.ttf", "FRSCRIPT.TTF",
]
PRINTED_FONT_FILES = ["arial.ttf", "times.ttf", "calibri.ttf", "verdana.ttf"]

INK_COLOURS = [
    (12, 12, 18),     # black
    (18, 28, 92),     # dark blue
    (28, 36, 70),     # blue-black
    (45, 45, 50),     # dark grey
    (10, 40, 80),     # navy
]
PAPER_TINTS = [
    (255, 255, 255), (252, 251, 246), (250, 249, 242),
    (248, 246, 240), (245, 245, 248),
]

FIELD_LABELS = {
    "case_reference": "Reference:",
    "person_name": "Requester name:",
    "email": "Email:",
    "phone": "Phone:",
    "address": "Postal address:",
}
BODY_PARAGRAPHS = [
    "Dear Information Governance Team,",
    "Please provide copies of policies, guidance, and meeting notes",
    "about parking enforcement grace periods and vulnerability markers",
    "between January 2025 and May 2026. I would also like any equality",
    "impact screening documents linked to this topic.",
    "Please send the response by email if possible.",
    "Signed,",
]


def _load_font(filename: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / filename
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def load_answer_keys(input_root: Path) -> Dict[str, Dict]:
    keys = {}
    for folder in sorted(input_root.iterdir()):
        if folder.is_dir() and folder.name.startswith("DOC-"):
            ak = folder / "answer_key.json"
            if ak.exists():
                keys[folder.name] = json.loads(ak.read_text(encoding="utf-8"))
    return keys


def extract_pii_fields(answer_key: Dict) -> List[Dict]:
    fields = []
    for item in answer_key.get("sensitive_items", []):
        t, v = item.get("type"), item.get("value", "")
        if t in PII_CLASSES and v:
            fields.append({"type": t, "value": v, "class_id": PII_CLASSES[t]})
    return fields


def render_document(answer_key: Dict, variation_id: int) -> Tuple[Image.Image, List[Dict]]:
    """Render one handwritten-style page and return (image, tight YOLO labels)."""
    rng = random.Random(f"{answer_key.get('document_id')}-{variation_id}")

    paper = rng.choice(PAPER_TINTS)
    image = Image.new("RGB", (PAGE_W, PAGE_H), paper)
    draw = ImageDraw.Draw(image)

    ink = rng.choice(INK_COLOURS)
    hand_file = rng.choice(HANDWRITING_FONT_FILES)
    printed_file = rng.choice(PRINTED_FONT_FILES)
    # Some forms have printed field labels; some are fully handwritten.
    labels_handwritten = rng.random() < 0.5

    hand_size = rng.randint(30, 40)
    header_size = rng.randint(24, 30)
    label_size = rng.randint(22, 27)

    hand_font = _load_font(hand_file, hand_size)
    header_font = _load_font(printed_file, header_size)
    label_font = hand_font if labels_handwritten else _load_font(printed_file, label_size)

    margin = rng.randint(50, 90)
    line_gap = rng.randint(54, 72)

    fields = extract_pii_fields(answer_key)
    by_type = {f["type"]: f for f in fields}
    labels: List[Dict] = []

    # --- Letterhead + title (printed headers, realistic) ---
    y = rng.randint(24, 44)
    draw.text((margin, y), "Eastmere District Council", fill=ink, font=header_font)
    y += header_size + 8
    draw.text((margin, y), "Information Governance Team", fill=ink, font=header_font)
    y += header_size + 8
    draw.text((margin, y), "Civic Offices, Eastmere", fill=ink, font=header_font)
    y += int(line_gap * 1.4)
    draw.text((margin, y), "Freedom of Information Request", fill=ink, font=header_font)
    y += int(line_gap * 1.2)

    # --- Date (non-PII, present for realism / negative region) ---
    if rng.random() < 0.85:
        draw.text((margin, y), "Date received: 11 June 2026", fill=ink, font=label_font)
        y += line_gap

    def place_field(ftype: str):
        nonlocal y
        f = by_type.get(ftype)
        if not f:
            return
        label_text = FIELD_LABELS[ftype]
        draw.text((margin, y), label_text, fill=ink, font=label_font)
        lbb = draw.textbbox((margin, y), label_text, font=label_font)
        value_x = lbb[2] + rng.randint(14, 30)
        value_y = y + rng.randint(-3, 3)
        draw.text((value_x, value_y), f["value"], fill=ink, font=hand_font)
        vbb = draw.textbbox((value_x, value_y), f["value"], font=hand_font)
        _add_label(labels, f["class_id"], vbb)
        y += line_gap

    # Structured PII fields in realistic form order
    for ftype in ["case_reference", "person_name", "email", "phone", "address"]:
        place_field(ftype)

    # --- Handwritten body paragraph (non-PII; fills page, gives negatives) ---
    y += rng.randint(20, 50)
    for line in BODY_PARAGRAPHS:
        draw.text((margin, y), line, fill=ink, font=hand_font)
        y += int(hand_size * 1.25)

    # --- Signature (PII) near the bottom of the letter ---
    sig = by_type.get("signature")
    if sig:
        sig_x = margin + rng.randint(0, 40)
        sig_y = y + rng.randint(6, 30)
        draw.text((sig_x, sig_y), sig["value"], fill=ink, font=hand_font)
        sbb = draw.textbbox((sig_x, sig_y), sig["value"], font=hand_font)
        _add_label(labels, sig["class_id"], sbb)

    # Light, label-safe photometric grain only (does not move pixels).
    image = _add_grain(image, rng)
    return image, labels


def _add_label(labels: List[Dict], class_id: int, bbox: Tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = bbox
    # Tiny padding so descenders/ink are fully covered, then clamp to page.
    pad = 3
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(PAGE_W, x1 + pad); y1 = min(PAGE_H, y1 + pad)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    labels.append({
        "class_id": class_id,
        "x": (x0 + x1) / 2 / PAGE_W,
        "y": (y0 + y1) / 2 / PAGE_H,
        "w": (x1 - x0) / PAGE_W,
        "h": (y1 - y0) / PAGE_H,
    })


def _add_grain(image: Image.Image, rng: random.Random) -> Image.Image:
    try:
        arr = np.array(image, dtype=np.float32)
        sigma = rng.uniform(1.5, 5.0)
        arr += np.random.normal(0, sigma, arr.shape)
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    except Exception:
        return image


def save_yolo_labels(labels: List[Dict], path: Path) -> None:
    lines = [
        f"{l['class_id']} {l['x']:.6f} {l['y']:.6f} {l['w']:.6f} {l['h']:.6f}"
        for l in labels
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_dataset_meta() -> None:
    (OUTPUT_DATASET / "classes.txt").write_text("\n".join(CLASS_ORDER) + "\n", encoding="utf-8")
    yaml = (
        f"path: {OUTPUT_DATASET.as_posix()}\n"
        f"train: images\n"
        f"val: images\n"
        f"names:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASS_ORDER))
    )
    (OUTPUT_DATASET / "data.yaml").write_text(yaml, encoding="utf-8")


def main() -> None:
    print("[Generator] Starting tight-label dataset generation...")
    OUTPUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUTPUT_LABELS.mkdir(parents=True, exist_ok=True)

    answer_keys = load_answer_keys(INPUT_DATASET)
    print(f"[Generator] Loaded {len(answer_keys)} answer keys")
    if not answer_keys:
        print("[ERROR] No answer_key.json files found. Check the dataset path.")
        return

    total = 0
    for doc_id, ak in sorted(answer_keys.items()):
        ak.setdefault("document_id", doc_id)
        for var in range(VARIATIONS_PER_DOC):
            try:
                image, labels = render_document(ak, var)
                image.save(OUTPUT_IMAGES / f"{doc_id}_{var:02d}.png", "PNG")
                save_yolo_labels(labels, OUTPUT_LABELS / f"{doc_id}_{var:02d}.txt")
                total += 1
                if total % 100 == 0:
                    print(f"[Generator] {total} images...")
            except Exception as e:
                print(f"[ERROR] {doc_id}_{var:02d}: {e}")

    write_dataset_meta()
    print(f"[Generator] Done. Generated {total} images + labels")
    print(f"[Generator] Images: {OUTPUT_IMAGES}")
    print(f"[Generator] Labels: {OUTPUT_LABELS}")
    print(f"[Generator] Wrote classes.txt and data.yaml")


if __name__ == "__main__":
    main()
