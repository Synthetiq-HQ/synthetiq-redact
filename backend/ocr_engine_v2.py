import os
import logging
import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Try to import PaddleOCR
try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False
    logger.warning("[OCR] PaddleOCR not available. Install with: pip install paddlepaddle paddleocr")

# Try to import EasyOCR as fallback
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("[OCR] EasyOCR not available.")


@dataclass
class OCRWord:
    text: str
    bbox: List[List[float]]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    confidence: float


@dataclass
class OCRResult:
    full_text: str
    words: List[OCRWord]
    average_confidence: float
    engine_used: str
    regions: Dict[str, Any] = None  # Layout regions


@dataclass
class DocumentRegion:
    """Detected region of document (header, body, footer, etc.)"""
    region_type: str  # "header", "body", "footer", "sidebar", "signature"
    bbox: List[float]  # [x, y, w, h]
    confidence: float


class LayoutAnalyzer:
    """
    Analyzes document layout to detect regions like header, body, footer, signature.
    Uses simple heuristics based on text positions.
    """
    
    def __init__(self):
        pass
    
    def analyze(self, image_path: str, words: List[OCRWord]) -> List[DocumentRegion]:
        """
        Detect document regions based on word positions.
        """
        if not words:
            return []
        
        img = cv2.imread(image_path)
        if img is None:
            return []
        
        h, w = img.shape[:2]
        regions = []
        
        # Get all word Y positions
        word_ys = []
        for word in words:
            ys = [p[1] for p in word.bbox]
            avg_y = sum(ys) / len(ys)
            word_ys.append(avg_y)
        
        if not word_ys:
            return []
        
        min_y = min(word_ys)
        max_y = max(word_ys)
        text_height = max_y - min_y
        
        # Header: top 15% of text area
        header_threshold = min_y + text_height * 0.15
        header_words = [w for w, y in zip(words, word_ys) if y < header_threshold]
        
        # Footer: bottom 15% of text area  
        footer_threshold = max_y - text_height * 0.15
        footer_words = [w for w, y in zip(words, word_ys) if y > footer_threshold]
        
        # Signature region: bottom right quadrant
        sig_words = []
        for word in words:
            bbox = word.bbox
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            avg_x = sum(xs) / len(xs)
            avg_y = sum(ys) / len(ys)
            
            if avg_x > w * 0.5 and avg_y > h * 0.75:
                # Check if text looks like a closing
                text_lower = word.text.lower()
                if any(t in text_lower for t in ["sign", "signed", "regards", "faithfully", "sincerely"]):
                    sig_words.append(word)
        
        # Build regions
        if header_words:
            all_x = []
            all_y = []
            for word in header_words:
                for p in word.bbox:
                    all_x.append(p[0])
                    all_y.append(p[1])
            regions.append(DocumentRegion(
                region_type="header",
                bbox=[min(all_x), min(all_y), max(all_x) - min(all_x), max(all_y) - min(all_y)],
                confidence=0.70
            ))
        
        if footer_words:
            all_x = []
            all_y = []
            for word in footer_words:
                for p in word.bbox:
                    all_x.append(p[0])
                    all_y.append(p[1])
            regions.append(DocumentRegion(
                region_type="footer",
                bbox=[min(all_x), min(all_y), max(all_x) - min(all_x), max(all_y) - min(all_y)],
                confidence=0.65
            ))
        
        if sig_words:
            all_x = []
            all_y = []
            for word in sig_words:
                for p in word.bbox:
                    all_x.append(p[0])
                    all_y.append(p[1])
            regions.append(DocumentRegion(
                region_type="signature",
                bbox=[min(all_x), min(all_y), max(all_x) - min(all_x), max(all_y) - min(all_y)],
                confidence=0.75
            ))
        
        # Body is everything else
        body_words = [w for w in words if w not in header_words and w not in footer_words and w not in sig_words]
        if body_words:
            all_x = []
            all_y = []
            for word in body_words:
                for p in word.bbox:
                    all_x.append(p[0])
                    all_y.append(p[1])
            regions.append(DocumentRegion(
                region_type="body",
                bbox=[min(all_x), min(all_y), max(all_x) - min(all_x), max(all_y) - min(all_y)],
                confidence=0.80
            ))
        
        return regions


class PaddleOCREngine:
    """PaddleOCR-based OCR engine."""
    
    def __init__(self):
        self.ocr = None
        self._initialized = False
        
    def _init(self):
        if self._initialized:
            return
            
        if not PADDLE_AVAILABLE:
            raise RuntimeError("PaddleOCR not available")
        
        logger.info("[OCR] Initializing PaddleOCR...")
        self.ocr = PaddleOCR(
            use_angle_cls=True,  # Detect rotated text
            lang='en',
        )
        self._initialized = True
        logger.info("[OCR] PaddleOCR initialized")
    
    def extract_text(self, image_path: str) -> OCRResult:
        """Extract text using PaddleOCR."""
        self._init()
        
        result = self.ocr.ocr(image_path)
        
        if not result or not result[0]:
            return OCRResult(
                full_text="",
                words=[],
                average_confidence=0.0,
                engine_used="paddleocr",
                regions={}
            )
        
        words = []
        texts = []
        confidences = []
        
        for line in result[0]:
            if line is None:
                continue
            bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text = line[1][0]
            conf = line[1][1]
            
            words.append(OCRWord(
                text=text,
                bbox=bbox,
                confidence=conf
            ))
            texts.append(text)
            confidences.append(conf)
        
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        full_text = " ".join(texts)
        
        return OCRResult(
            full_text=full_text,
            words=words,
            average_confidence=avg_conf,
            engine_used="paddleocr",
            regions={}
        )


class HandwritingOCREngine:
    """
    Handwriting-specific OCR engine.
    Uses EasyOCR for text region detection, then TrOCR for transcription.
    Fully local — no cloud APIs required.
    """

    def __init__(self, easyocr_reader=None):
        self.reader = easyocr_reader
        self.processor = None
        self.model = None
        self._initialized = False

    def _init(self):
        if self._initialized:
            return
        logger.info("[Handwriting OCR] Initializing TrOCR...")
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
            self.processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
            self.model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
            logger.info("[Handwriting OCR] TrOCR loaded (334M params)")
        except Exception as e:
            logger.error(f"[Handwriting OCR] Failed to load TrOCR: {e}")
            raise
        if self.reader is None:
            logger.info("[Handwriting OCR] Initializing EasyOCR detector...")
            self.reader = easyocr.Reader(["en"], gpu=False)
            logger.info("[Handwriting OCR] EasyOCR detector ready")
        self._initialized = True

    def extract_text(self, image_path: str) -> OCRResult:
        """Extract handwritten text using EasyOCR + TrOCR pipeline."""
        self._init()
        img = Image.open(image_path).convert("RGB")

        # Step 1: EasyOCR detects text regions
        detections = self.reader.readtext(image_path)
        if not detections:
            return OCRResult(
                full_text="",
                words=[],
                average_confidence=0.0,
                engine_used="handwriting_trocr",
                regions={},
            )

        # Step 2: Run TrOCR on each detected region
        words = []
        texts = []
        confidences = []

        for det in detections:
            bbox = det[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            det_conf = float(det[2])  # EasyOCR detection confidence

            # Crop bounding box
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            x1, y1 = max(0, x1), max(0, y1)
            crop = img.crop((x1, y1, x2, y2))

            if crop.width < 8 or crop.height < 8:
                continue

            # TrOCR transcription
            pixel_values = self.processor(images=crop, return_tensors="pt").pixel_values
            generated_ids = self.model.generate(pixel_values, max_new_tokens=50)
            text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            text = text.strip()

            if text:
                words.append(OCRWord(
                    text=text,
                    bbox=bbox,
                    confidence=det_conf,  # Use detection confidence as proxy
                ))
                texts.append(text)
                confidences.append(det_conf)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        full_text = " ".join(texts)

        return OCRResult(
            full_text=full_text,
            words=words,
            average_confidence=avg_conf,
            engine_used="handwriting_trocr",
            regions={},
        )


class OCREngineManager:
    """
    Multi-engine OCR manager.
    Primary: PaddleOCR
    Fallback: EasyOCR
    Includes layout analysis.
    """
    
    def __init__(self):
        self.paddle_engine = None
        self.easyocr_engine = None
        self.handwriting_engine = None
        self.layout_analyzer = LayoutAnalyzer()
        
        # Try to initialize PaddleOCR
        if PADDLE_AVAILABLE:
            try:
                self.paddle_engine = PaddleOCREngine()
                logger.info("[OCR Manager] PaddleOCR primary engine ready")
            except Exception as e:
                logger.error(f"[OCR Manager] Failed to init PaddleOCR: {e}")
        
        # Initialize EasyOCR as fallback
        if EASYOCR_AVAILABLE:
            try:
                logger.info("[OCR Manager] Initializing EasyOCR fallback...")
                self.easyocr_engine = easyocr.Reader(['en'])
                logger.info("[OCR Manager] EasyOCR fallback ready")
            except Exception as e:
                logger.error(f"[OCR Manager] Failed to init EasyOCR: {e}")
        
        # Initialize handwriting engine (lazy load TrOCR on first use)
        if EASYOCR_AVAILABLE:
            try:
                logger.info("[OCR Manager] Handwriting engine ready (TrOCR lazy load)")
                self.handwriting_engine = HandwritingOCREngine(easyocr_reader=self.easyocr_engine)
            except Exception as e:
                logger.error(f"[OCR Manager] Failed to init handwriting engine: {e}")
    
    def extract_text(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text using best available engine.
        Returns legacy dict format for backwards compatibility.
        """
        # Try PaddleOCR first
        if self.paddle_engine:
            try:
                result = self.paddle_engine.extract_text(image_path)
                
                # Run layout analysis
                layout_regions = self.layout_analyzer.analyze(image_path, result.words)
                result.regions = {
                    r.region_type: {
                        "bbox": r.bbox,
                        "confidence": r.confidence
                    }
                    for r in layout_regions
                }
                
                # If confidence is too low, try EasyOCR
                if result.average_confidence < 0.7 and self.easyocr_engine:
                    logger.info("[OCR Manager] PaddleOCR confidence low, trying EasyOCR...")
                    easy_result = self._extract_with_easyocr(image_path)
                    
                    # Use EasyOCR if it has better confidence
                    if easy_result["average_confidence"] > result.average_confidence:
                        logger.info("[OCR Manager] Using EasyOCR result (better confidence)")
                        easy_result["engine_used"] = "easyocr_fallback"
                        easy_result["layout_regions"] = result.regions
                        return easy_result
                
                return self._to_legacy_format(result)
                
            except Exception as e:
                logger.error(f"[OCR Manager] PaddleOCR failed: {e}")
        
        # Fallback to EasyOCR
        if self.easyocr_engine:
            try:
                easy_result = self._extract_with_easyocr(image_path)
                # If EasyOCR confidence is low, handwriting might be the issue
                if easy_result["average_confidence"] < 0.5 and self.handwriting_engine:
                    logger.info("[OCR Manager] EasyOCR confidence very low, trying TrOCR handwriting...")
                    hw_result = self.handwriting_engine.extract_text(image_path)
                    if hw_result.words:
                        logger.info(f"[OCR Manager] TrOCR found {len(hw_result.words)} handwriting words")
                        return self._to_legacy_format(hw_result)
                return easy_result
            except Exception as e:
                logger.error(f"[OCR Manager] EasyOCR also failed: {e}")
        
        # Last resort: handwriting engine directly
        if self.handwriting_engine:
            try:
                hw_result = self.handwriting_engine.extract_text(image_path)
                return self._to_legacy_format(hw_result)
            except Exception as e:
                logger.error(f"[OCR Manager] Handwriting engine failed: {e}")
        
        # Complete failure
        raise RuntimeError("No OCR engine available")
    
    @staticmethod
    def _sanitize(value):
        """Recursively convert numpy types to native Python types for JSON serialization."""
        import numpy as np
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, (list, tuple)):
            return [OCREngineManager._sanitize(v) for v in value]
        if isinstance(value, dict):
            return {k: OCREngineManager._sanitize(v) for k, v in value.items()}
        return value

    def _extract_with_easyocr(self, image_path: str) -> Dict[str, Any]:
        """Extract text using EasyOCR."""
        raw = self.easyocr_engine.readtext(image_path)
        
        words = []
        texts = []
        confidences = []
        
        for item in raw:
            bbox = item[0]
            text = item[1]
            conf = item[2]
            
            words.append({
                "text": text,
                "bbox": self._sanitize(bbox),
                "confidence": float(conf)
            })
            texts.append(text)
            confidences.append(float(conf))
        
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        
        return {
            "full_text": " ".join(texts),
            "words": words,
            "average_confidence": avg_conf,
            "engine_used": "easyocr",
        }
    
    def _to_legacy_format(self, result: OCRResult) -> Dict[str, Any]:
        """Convert OCRResult to legacy dict format."""
        return {
            "full_text": result.full_text,
            "words": [
                {
                    "text": w.text,
                    "bbox": self._sanitize(w.bbox),
                    "confidence": float(w.confidence)
                }
                for w in result.words
            ],
            "average_confidence": float(result.average_confidence),
            "engine_used": result.engine_used,
            "layout_regions": self._sanitize(result.regions) or {},
        }


# Legacy compatibility - keep existing class name
class OCREngine:
    """Legacy wrapper that delegates to OCREngineManager."""
    
    def __init__(self):
        self.manager = OCREngineManager()
    
    def extract_text(self, image_path: str) -> Dict[str, Any]:
        return self.manager.extract_text(image_path)
