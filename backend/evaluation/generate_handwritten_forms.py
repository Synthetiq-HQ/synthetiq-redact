"""
Generate synthetic council forms rendered with handwriting fonts.
Ground-truth PII is embedded in JSON sidecars for evaluation.
"""

import json
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DATASETS_DIR = Path(__file__).parent / "datasets"
HANDWRITING_FONTS = [
    "Segoe Script",
    "Bradley Hand ITC",
    "Lucida Handwriting",
    "Comic Sans MS",
    "Freestyle Script",
    "Brush Script MT",
    "Kunstler Script",
    "Segoe Print",
]

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
    "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra",
]
SURNAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White",
]
STREETS = [
    "High Street", "Station Road", "Church Lane", "Victoria Road", "Park Avenue",
    "London Road", "Green Lane", "Manor Road", "The Avenue", "King Street",
    "Queen Street", "Bridge Road", "Mill Lane", "School Lane", "Chestnut Drive",
]
CITIES = [
    "London", "Birmingham", "Manchester", "Leeds", "Glasgow", "Sheffield",
    "Bradford", "Liverpool", "Edinburgh", "Bristol", "Cardiff", "Belfast",
    "Leicester", "Coventry", "Nottingham", "Newcastle", "Southampton", "Portsmouth",
]
CATEGORIES = [
    "housing_repairs", "council_tax", "parking", "complaint", "waste",
    "adult_social_care", "children_safeguarding",
]


def _jitter(val: int, max_jitter: int = 3) -> int:
    return val + random.randint(-max_jitter, max_jitter)


def _pick_font(size: int) -> ImageFont.FreeTypeFont:
    """Pick a random handwriting font, falling back to default if unavailable."""
    font_name = random.choice(HANDWRITING_FONTS)
    try:
        return ImageFont.truetype(font_name + ".ttf", size)
    except Exception:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            return ImageFont.load_default()


def generate_handwritten_forms(count: int = 50, out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or DATASETS_DIR / "synthetic_handwritten"
    out_dir.mkdir(parents=True, exist_ok=True)

    images = []
    for i in range(count):
        # White A4-ish background with slight texture
        img = Image.new("RGB", (1240, 1754), color="white")
        draw = ImageDraw.Draw(img)

        # Subtle paper texture (light grey noise)
        for _ in range(3000):
            x, y = random.randint(0, 1239), random.randint(0, 1753)
            draw.point((x, y), fill=(245, 245, 245))

        # Fonts
        font_label = _pick_font(26)
        font_value = _pick_font(28)
        font_header = _pick_font(36)
        font_small = _pick_font(22)

        # Random PII
        first = random.choice(FIRST_NAMES)
        last = random.choice(SURNAMES)
        name = f"{first} {last}"
        dob = f"{random.randint(1, 28):02d}/{random.randint(1, 12):02d}/{random.randint(1950, 2005)}"
        address = f"{random.randint(1, 150)} {random.choice(STREETS)}, {random.choice(CITIES)}, UB{random.randint(1, 10)} {random.randint(1, 9)}{random.choice('ABXY')}"
        phone = f"07{random.randint(100, 999):03d} {random.randint(100, 999):03d} {random.randint(100, 999):03d}"
        email = f"{first.lower()}.{last.lower()}{random.randint(1, 99)}@email.com"
        nin = f"{random.choice('ABCEGHJKLMNPRSTWXYZ')}{random.choice('ABCEGHJKLMNPRSTWXYZ')}{random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)} {random.choice('ABCEGHJKLMNPRSTWXYZ')}"
        cat = random.choice(CATEGORIES)

        ground_truth = {
            "name": name,
            "dob": dob,
            "address": address,
            "phone": phone,
            "email": email,
            "nin": nin,
            "category": cat,
        }

        # Header
        y = 50
        draw.text((_jitter(60), _jitter(y)), "HILLINGDON COUNCIL", fill="black", font=font_header)
        y += 50
        draw.text((_jitter(60), _jitter(y)), "Document Processing Form", fill="#333", font=font_label)
        y += 40
        draw.line((60, y, 1180, y), fill="black", width=2)
        y += 40

        fields = [
            ("Full Name:", name),
            ("Date of Birth:", dob),
            ("Address:", address),
            ("Phone Number:", phone),
            ("Email:", email),
            ("National Insurance Number:", nin),
            ("Date:", f"{random.randint(1, 28):02d}/{random.randint(1, 12):02d}/2024"),
        ]

        for label, value in fields:
            lx = _jitter(60)
            ly = _jitter(y)
            draw.text((lx, ly), label, fill="#444", font=font_small)

            vx = _jitter(380)
            vy = _jitter(y, 4)
            draw.text((vx, vy), value, fill="black", font=font_value)
            y += 80

        # Fake signature
        y += 30
        draw.text((_jitter(60), _jitter(y)), "Signature:", fill="#444", font=font_small)
        # Squiggle line
        sx = 380
        sy = y + 25
        points = [(sx + j * 3, _jitter(sy, 6)) for j in range(80)]
        for k in range(len(points) - 1):
            draw.line((points[k], points[k + 1]), fill="black", width=2)

        # Category at bottom
        draw.text((_jitter(60), _jitter(1650, 3)), f"Category: {cat.replace('_', ' ').title()}", fill="#666", font=font_small)

        # Add random ink blots / noise
        for _ in range(20):
            bx, by = random.randint(50, 1190), random.randint(150, 1700)
            draw.ellipse((bx, by, bx + 2, by + 2), fill=(30, 30, 30))

        path = out_dir / f"handwritten_form_{i:03d}_{cat}.png"
        img.save(path, quality=95)

        meta_path = out_dir / f"{path.stem}.json"
        meta_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

        images.append(path)

    print(f"[Dataset] Generated {len(images)} handwritten forms in {out_dir}")
    return images


if __name__ == "__main__":
    import sys
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    generate_handwritten_forms(count=count)
