import easyocr
import numpy as np
from PIL import Image


class OCREngine:
    def __init__(self):
        self.reader = easyocr.Reader(["en"], gpu=False)

    def extract_text(self, image_path: str) -> dict:
        """
        Run EasyOCR on an image.
        Returns dict with:
            - full_text: str
            - words: list of {text, bbox, confidence}
            - average_confidence: float
        """
        results = self.reader.readtext(image_path, detail=1)

        words = []
        confidences = []
        text_parts = []

        for (bbox, text, confidence) in results:
            # bbox from EasyOCR is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] with numpy int32
            # Convert to native Python ints so SQLAlchemy JSON serializer handles them
            clean_bbox = [[int(x), int(y)] for x, y in bbox]
            words.append({
                "text": text,
                "bbox": clean_bbox,
                "confidence": round(float(confidence), 4),
            })
            confidences.append(float(confidence))
            text_parts.append(text)

        avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        return {
            "full_text": " ".join(text_parts),
            "words": words,
            "average_confidence": avg_confidence,
        }
