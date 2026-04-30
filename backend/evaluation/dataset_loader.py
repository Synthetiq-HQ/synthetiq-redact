"""
Dataset loaders for acquiring real document images.
Supports downloading from public sources and loading local folders.
"""

import os
import zipfile
import requests
from pathlib import Path
from typing import List, Optional

DATASETS_DIR = Path(__file__).parent / "datasets"
DATASETS_DIR.mkdir(exist_ok=True)


def load_local_folder(folder_path: str | Path, extensions: tuple = (".png", ".jpg", ".jpeg", ".pdf")) -> List[Path]:
    """Load all image files from a local folder."""
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    files = sorted([f for f in folder.iterdir() if f.suffix.lower() in extensions])
    print(f"[Dataset] Loaded {len(files)} images from {folder}")
    return files


def download_iam_handwriting(sample_count: int = 100, out_dir: Optional[Path] = None) -> List[Path]:
    """
    Load IAM Handwriting Database form images.
    First checks for pre-downloaded HF images in iam_forms/,
    otherwise prints manual download instructions.
    """
    # Check for HuggingFace pre-downloaded images first
    hf_dir = DATASETS_DIR / "iam_forms"
    if hf_dir.exists() and any(hf_dir.glob("*.png")):
        images = sorted([f for f in hf_dir.iterdir() if f.suffix.lower() == ".png"])[:sample_count]
        print(f"[Dataset] Loaded {len(images)} IAM handwritten forms from HuggingFace mirror ({hf_dir})")
        return images

    out_dir = out_dir or DATASETS_DIR / "iam_handwriting"
    out_dir.mkdir(exist_ok=True)

    print("[Dataset] IAM Handwriting requires manual download from:")
    print("  https://fki.tic.heia-fr.ch/databases/iam-handwriting-database")
    print(f"[Dataset] Please download and extract to: {out_dir}")
    print("[Dataset] Or run: python evaluation/download_iam_hf.py 50")
    print("[Dataset] Then re-run with load_local_folder().")
    return []


def download_nist_forms(out_dir: Optional[Path] = None) -> List[Path]:
    """
    NIST Special Database 19 - handwritten forms and characters.
    Public US government dataset.
    """
    out_dir = out_dir or DATASETS_DIR / "nist_forms"
    out_dir.mkdir(exist_ok=True)
    print("[Dataset] NIST SD19 available at:")
    print("  https://www.nist.gov/srd/nist-special-database-19")
    print(f"[Dataset] Download and extract to: {out_dir}")
    return []


def download_rimes_dataset(out_dir: Optional[Path] = None) -> List[Path]:
    """
    RIMES dataset - French handwritten letters (good for form-like docs).
    Public competition dataset.
    """
    out_dir = out_dir or DATASETS_DIR / "rimes"
    out_dir.mkdir(exist_ok=True)
    print("[Dataset] RIMES available at:")
    print("  https://www.a2ialab.com/doku.php?id=rimes_database:start")
    print(f"[Dataset] Download and extract to: {out_dir}")
    return []


def download_cord_receipts(out_dir: Optional[Path] = None) -> List[Path]:
    """
    CORD dataset - real scanned receipts (great for PII redaction testing).
    Public dataset with annotated text.
    """
    out_dir = out_dir or DATASETS_DIR / "cord_receipts"
    out_dir.mkdir(exist_ok=True)

    # CORD has a public GitHub repo with sample images
    github_zip = "https://github.com/clovaai/cord/archive/refs/heads/master.zip"
    zip_path = out_dir / "cord.zip"

    if not zip_path.exists():
        print("[Dataset] Downloading CORD receipts...")
        r = requests.get(github_zip, timeout=120)
        r.raise_for_status()
        zip_path.write_bytes(r.content)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(out_dir)
        print(f"[Dataset] CORD extracted to {out_dir}")

    # Find receipt images
    images = list((out_dir / "cord-master").rglob("*.png"))
    images += list((out_dir / "cord-master").rglob("*.jpg"))
    print(f"[Dataset] Found {len(images)} receipt images")
    return images[:200]


def generate_synthetic_forms(count: int = 50, out_dir: Optional[Path] = None) -> List[Path]:
    """
    Generate realistic synthetic council-style forms with random PII.
    Uses Pillow to create handwritten-style forms.
    Good for controlled testing when real data is scarce.
    """
    out_dir = out_dir or DATASETS_DIR / "synthetic_forms"
    out_dir.mkdir(exist_ok=True)

    try:
        from PIL import Image, ImageDraw, ImageFont
        import random
    except ImportError:
        print("[Dataset] Pillow not available. Install with: pip install pillow")
        return []

    # Fake data pools
    first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth",
                   "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
    surnames = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
                "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
    streets = ["High Street", "Station Road", "Church Lane", "Victoria Road", "Park Avenue", "London Road",
               "Green Lane", "Manor Road", "The Avenue", "King Street"]
    cities = ["London", "Birmingham", "Manchester", "Leeds", "Glasgow", "Sheffield", "Bradford", "Liverpool",
              "Edinburgh", "Bristol", "Cardiff", "Belfast", "Leicester", "Coventry", "Nottingham"]

    images = []
    for i in range(count):
        # Create a white A4-ish form
        img = Image.new("RGB", (1240, 1754), color="white")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", 28)
            font_bold = ImageFont.truetype("arialbd.ttf", 32)
            font_small = ImageFont.truetype("arial.ttf", 22)
        except:
            font = ImageFont.load_default()
            font_bold = font
            font_small = font

        # Header
        draw.text((60, 40), "HILLINGDON COUNCIL", fill="black", font=font_bold)
        draw.text((60, 90), "Document Processing Form", fill="#333", font=font)
        draw.line((60, 130, 1180, 130), fill="black", width=2)

        # Random form data
        name = f"{random.choice(first_names)} {random.choice(surnames)}"
        dob = f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(1950,2005)}"
        address = f"{random.randint(1,150)} {random.choice(streets)}, {random.choice(cities)}, UB{random.randint(1,10)} {random.randint(1,9)}{random.choice('ABXY')}"
        phone = f"07{random.randint(100,999):03d} {random.randint(100,999):03d} {random.randint(100,999):03d}"
        email = f"{name.lower().replace(' ', '.')}{random.randint(1,99)}@email.com"
        nin = f"{random.choice('ABCEGHJKLMNPRSTWXYZ')}{random.choice('ABCEGHJKLMNPRSTWXYZ')}{random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.choice('ABCEGHJKLMNPRSTWXYZ')}"

        fields = [
            ("Full Name:", name),
            ("Date of Birth:", dob),
            ("Address:", address),
            ("Phone Number:", phone),
            ("Email:", email),
            ("National Insurance Number:", nin),
            ("Date:", f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/2024"),
        ]

        y = 180
        for label, value in fields:
            draw.text((60, y), label, fill="#444", font=font_small)
            draw.text((350, y), value, fill="black", font=font)
            y += 70

        # Add some noise/scribbles to make it look scanned
        for _ in range(30):
            x1, y1 = random.randint(50, 1190), random.randint(150, 1700)
            x2, y2 = x1 + random.randint(-20, 20), y1 + random.randint(-20, 20)
            draw.line((x1, y1, x2, y2), fill=(220, 220, 220), width=1)

        # Add a fake signature line
        y += 40
        draw.text((60, y), "Signature:", fill="#444", font=font_small)
        draw.line((350, y + 25, 700, y + 25), fill="black", width=2)
        # Fake signature squiggle
        points = [(350 + j * 3, y + 25 + random.randint(-8, 8)) for j in range(100)]
        for k in range(len(points) - 1):
            draw.line((points[k], points[k + 1]), fill="black", width=2)

        # Random category label at bottom
        categories = ["housing_repairs", "council_tax", "parking", "complaint", "waste",
                      "adult_social_care", "children_safeguarding"]
        cat = random.choice(categories)
        draw.text((60, 1650), f"Category: {cat.replace('_', ' ').title()}", fill="#666", font=font_small)

        path = out_dir / f"synthetic_form_{i:03d}_{cat}.png"
        img.save(path, quality=95)
        images.append(path)

    print(f"[Dataset] Generated {len(images)} synthetic forms in {out_dir}")
    return images


def get_dataset(name: str = "synthetic", **kwargs) -> List[Path]:
    """Convenience dispatcher."""
    if name == "local":
        return load_local_folder(kwargs.get("path", DATASETS_DIR / "local"))
    if name == "cord":
        return download_cord_receipts()
    if name == "iam":
        return download_iam_handwriting()
    if name == "handwritten":
        return load_local_folder(DATASETS_DIR / "synthetic_handwritten")
    if name == "nist":
        return download_nist_forms()
    if name == "rimes":
        return download_rimes_dataset()
    if name == "synthetic":
        return generate_synthetic_forms(count=kwargs.get("count", 50))
    raise ValueError(f"Unknown dataset: {name}")


if __name__ == "__main__":
    # Quick test
    imgs = generate_synthetic_forms(count=5)
    print("Sample:", imgs[:3])
