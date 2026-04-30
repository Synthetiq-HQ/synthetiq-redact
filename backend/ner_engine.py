import os
import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import cv2
import numpy as np
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import torch

logger = logging.getLogger(__name__)

# UK-specific entity patterns
UK_PII_PATTERNS = {
    "nhs_number": re.compile(r"\b(\d{3}\s*[-\s]?\d{3}\s*[-\s]?\d{4})\b|\b(\d{10})\b"),
    "nin": re.compile(r"\b([A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}\s?\d{6}\s?[A-DFM]{1})\b", re.IGNORECASE),
    "utr": re.compile(r"\b(\d{10})\b"),  # Simplified - needs context
    "driving_licence": re.compile(r"\b([A-Z9]{5}\d{6}[A-Z9]{2}\d[A-Z]{2})\b", re.IGNORECASE),
    "council_tax_ref": re.compile(r"\b(CT\d{6,10})\b", re.IGNORECASE),
    "pcn_number": re.compile(r"\b(PCN\s?\d{6,10})\b", re.IGNORECASE),
    "passport_number": re.compile(r"\b(\d{9})\b"),  # Simplified
}

# UK postcode regex (comprehensive)
UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2})\b", 
    re.IGNORECASE
)

@dataclass
class DetectedEntity:
    type: str
    text: str
    start: int
    end: int
    confidence: float
    source: str  # "bert", "regex", "pattern"


class UKPIIDetectionEngine:
    """
    Advanced UK-specific PII detection using:
    1. Fine-tuned BERT for general NER
    2. Regex patterns for structured UK identifiers
    3. Context-aware validation (checksums, format validation)
    """
    
    def __init__(self):
        self.tokenizer = None
        self.model = None
        self.nlp_pipeline = None
        self._load_model()
        
    def _load_model(self):
        """Load BERT model for NER. Falls back to regex-only if model unavailable."""
        try:
            # Use a general NER model - in production, this would be fine-tuned on UK docs
            model_name = "dslim/bert-base-NER"
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForTokenClassification.from_pretrained(model_name)
            self.nlp_pipeline = pipeline(
                "ner", 
                model=self.model, 
                tokenizer=self.tokenizer,
                aggregation_strategy="simple",
                device=0 if torch.cuda.is_available() else -1
            )
            logger.info("[UKPII] BERT NER model loaded successfully")
        except Exception as e:
            logger.warning(f"[UKPII] Could not load BERT model: {e}. Falling back to regex-only.")
            self.nlp_pipeline = None
    
    def detect(self, text: str) -> List[DetectedEntity]:
        """
        Main detection pipeline.
        Returns list of DetectedEntity objects sorted by position.
        """
        entities = []
        
        # 1. BERT NER detection (highest confidence for general entities)
        if self.nlp_pipeline:
            bert_entities = self._detect_with_bert(text)
            entities.extend(bert_entities)
        
        # 2. Regex patterns for UK-specific identifiers
        regex_entities = self._detect_with_regex(text)
        entities.extend(regex_entities)
        
        # 3. Validate and deduplicate
        entities = self._deduplicate_entities(entities)
        entities = self._validate_entities(entities)
        
        # Sort by start position
        entities.sort(key=lambda e: e.start)
        
        return entities
    
    def _detect_with_bert(self, text: str) -> List[DetectedEntity]:
        """Run BERT NER on text."""
        if not self.nlp_pipeline:
            return []
        
        entities = []
        try:
            results = self.nlp_pipeline(text)
            for r in results:
                # Map BERT labels to our types
                label = r["entity_group"]
                type_map = {
                    "PER": "person_name",
                    "ORG": "organization",
                    "LOC": "location",
                    "MISC": "misc",
                }
                entity_type = type_map.get(label, label.lower())
                
                entities.append(DetectedEntity(
                    type=entity_type,
                    text=r["word"],
                    start=r["start"],
                    end=r["end"],
                    confidence=r["score"],
                    source="bert"
                ))
        except Exception as e:
            logger.error(f"[UKPII] BERT detection error: {e}")
        
        return entities
    
    def _detect_with_regex(self, text: str) -> List[DetectedEntity]:
        """Run regex patterns for UK-specific identifiers."""
        entities = []
        
        for entity_type, pattern in UK_PII_PATTERNS.items():
            for match in pattern.finditer(text):
                value = match.group()
                
                # Validate NHS number checksum if applicable
                if entity_type == "nhs_number" and not self._validate_nhs_checksum(value):
                    continue
                    
                # Validate NIN format
                if entity_type == "nin" and not self._validate_nin(value):
                    continue
                
                entities.append(DetectedEntity(
                    type=entity_type,
                    text=value,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.90,
                    source="regex"
                ))
        
        # UK Postcodes
        for match in UK_POSTCODE_RE.finditer(text):
            # Check it's not already covered by address detection
            if not any(e.start <= match.start() and e.end >= match.end() and e.type == "address" for e in entities):
                entities.append(DetectedEntity(
                    type="postcode",
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95,
                    source="regex"
                ))
        
        return entities
    
    def _validate_nhs_checksum(self, nhs_number: str) -> bool:
        """
        Validate NHS number using Modulus 11 check.
        NHS numbers are 10 digits with the last digit being a check digit.
        """
        digits = re.sub(r"\D", "", nhs_number)
        if len(digits) != 10:
            return False
        
        # Modulus 11 check
        weights = [10, 9, 8, 7, 6, 5, 4, 3, 2]
        try:
            total = sum(int(digits[i]) * weights[i] for i in range(9))
            remainder = total % 11
            check_digit = 11 - remainder
            if check_digit == 11:
                check_digit = 0
            return check_digit == int(digits[9])
        except (ValueError, IndexError):
            return False
    
    def _validate_nin(self, nin: str) -> bool:
        """
        Basic National Insurance number validation.
        Format: AB123456C (or A 123456 B)
        """
        nin = nin.upper().replace(" ", "")
        if len(nin) != 9:
            return False
        
        # First two chars must be valid prefix letters
        prefix = nin[:2]
        valid_prefixes = set(
            "ABCDEFGHJKLMNOPRSTWXYZ"  # Valid first chars
        )
        if prefix[0] not in valid_prefixes:
            return False
        
        # Second char
        valid_second = set("ABCEGHJKLMNOPRSTWXYZ")
        if prefix[1] not in valid_second:
            return False
        
        # Invalid combinations
        invalid_prefixes = {"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"}
        if prefix in invalid_prefixes:
            return False
        
        # Middle 6 must be digits
        if not nin[2:8].isdigit():
            return False
        
        # Last char must be valid suffix
        valid_suffixes = set("ABCD")
        if nin[8] not in valid_suffixes:
            return False
        
        return True
    
    def _deduplicate_entities(self, entities: List[DetectedEntity]) -> List[DetectedEntity]:
        """Remove overlapping entities, preferring higher confidence."""
        if not entities:
            return []
        
        # Sort by confidence descending
        sorted_entities = sorted(entities, key=lambda e: e.confidence, reverse=True)
        
        kept = []
        for entity in sorted_entities:
            # Check if this overlaps with any kept entity
            overlaps = False
            for kept_entity in kept:
                if (entity.start < kept_entity.end and entity.end > kept_entity.start):
                    overlaps = True
                    break
            if not overlaps:
                kept.append(entity)
        
        return kept
    
    def _validate_entities(self, entities: List[DetectedEntity]) -> List[DetectedEntity]:
        """Additional validation on detected entities."""
        validated = []
        for e in entities:
            # Skip entities that are too short
            if len(e.text.strip()) < 2:
                continue
            # Skip entities with very low confidence
            if e.confidence < 0.3:
                continue
            validated.append(e)
        return validated
    
    def detect_with_context(self, text: str, document_type: str = None) -> List[DetectedEntity]:
        """
        Context-aware detection that adjusts based on document type.
        E.g., in a safeguarding document, be more aggressive with medical details.
        """
        entities = self.detect(text)
        
        # Boost confidence for certain types based on document context
        if document_type in ["children_safeguarding", "adult_social_care"]:
            for e in entities:
                if e.type in ["person_name", "address", "phone", "email"]:
                    e.confidence = min(1.0, e.confidence + 0.05)
        
        return entities


# Legacy compatibility - keep existing interface
class NEREngine:
    """Wrapper for backwards compatibility."""
    
    def __init__(self):
        self.engine = UKPIIDetectionEngine()
    
    def detect_entities(self, text: str) -> List[Dict[str, Any]]:
        """Legacy interface returning dict format."""
        entities = self.engine.detect(text)
        return [
            {
                "type": e.type,
                "text": e.text,
                "start": e.start,
                "end": e.end,
                "confidence": e.confidence,
                "source": e.source,
            }
            for e in entities
        ]
