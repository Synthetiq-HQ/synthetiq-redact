"""Diagnose OCR and redaction on a single image."""

import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, str(__file__).replace('evaluation/diagnose_image.py', ''))

from ocr_engine_v2 import OCREngineManager
from redaction import RedactionEngine

IMG_PATH = "C:/Users/INTERPOL/Downloads/image.png"

print("=== OCR OUTPUT ===")
mgr = OCREngineManager()
ocr = mgr.extract_text(IMG_PATH)
print(f"Engine: {ocr.get('engine_used')}")
print(f"Words: {len(ocr.get('words', []))}")
print()
for w in ocr.get("words", []):
    print(repr(w["text"]))

print()
print("=== FULL TEXT ===")
print(ocr.get("full_text", ""))

print()
print("=== PII DETECTED ===")
eng = RedactionEngine()
spans = eng.detect_sensitive_text(ocr.get("full_text", ""))
for s in spans:
    print(f"  {s['type']:20s} {s['method']:18s} {repr(s['value'])}")
