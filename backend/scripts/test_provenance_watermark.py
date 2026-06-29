"""Local end-to-end check for the provenance watermark.

Creates a fake page, registers an export, burns in the watermark, decodes it back
from both an image and a PDF, and confirms it maps to the right document.

Run:  python backend/scripts/test_provenance_watermark.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from PIL import Image, ImageDraw  # noqa: E402

# Use an isolated data dir so the test never touches real provenance data.
_tmp = tempfile.mkdtemp(prefix="sr_prov_test_")
os.environ["SYNTHETIQ_DATA_DIR"] = _tmp

from provenance import get_provenance_store, bytes_sha256  # noqa: E402
import watermark  # noqa: E402

FAILS = []
def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILS.append(name)


def make_page():
    img = Image.new("RGB", (1000, 1400), "white")
    d = ImageDraw.Draw(img)
    d.text((80, 120), "Eastmere District Council", fill="black")
    for i in range(8):
        d.text((80, 220 + i * 40), "Body line with some content " * 2, fill=(40, 40, 60))
    return img


def main():
    store = get_provenance_store()
    print("instance:", store.instance_info()["short_id"])

    page = make_page()
    rec = store.create_export(
        document_id=42, filename="DOC-TEST.pdf", user_id=7,
        original_hash=bytes_sha256(b"original-bytes"),
        engine_used="synthetiq_redact_v3_glm_geometry", page_count=1,
    )
    export_id = rec["export_id"]
    print("export id:", export_id)
    check("export id format SRD-", export_id.startswith("SRD-") and len(export_id.split("-")) == 4)
    check("verify_format == ours", store.verify_format(export_id) == "ours")

    # Embed + decode from image
    marked, pos = watermark.embed_watermark(page, export_id)
    check("watermark placed in a corner", pos["corner"] in watermark.CORNERS)
    img_path = Path(_tmp) / "marked.png"
    marked.save(img_path)
    decoded_img = watermark.decode_any(str(img_path))
    check("decode from PNG matches", decoded_img == export_id)

    # Embed + decode from PDF (all pages watermarked)
    pages = [make_page(), make_page()]
    marked_pages, positions = watermark.embed_in_images(pages, export_id)
    pdf_path = Path(_tmp) / "marked.pdf"
    marked_pages[0].save(pdf_path, "PDF", save_all=True, append_images=marked_pages[1:], resolution=200.0)
    watermark.set_pdf_metadata_id(str(pdf_path), export_id)
    decoded_pdf = watermark.decode_any(str(pdf_path))
    check("decode from PDF matches", decoded_pdf == export_id)

    # Lookup maps to the right document
    result = store.decode_result(decoded_img or "")
    check("decode_result found", result["status"] == "found")
    check("maps to document 42", result.get("record", {}).get("document_id") == 42)

    # Foreign / invalid ids are rejected (not silently trusted)
    check("foreign id rejected", store.decode_result("SRD-ZZZZZZ-AAAAAAAA-BBBB")["status"] in ("foreign", "invalid"))
    check("garbage id invalid", store.decode_result("hello-world")["status"] == "invalid")

    print("\nRESULT:", "ALL PASS" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
