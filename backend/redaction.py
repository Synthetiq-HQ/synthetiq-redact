import os
import re
import shutil
from typing import List, Optional, Dict, Any

import cv2
import numpy as np

import spacy
from config import REDACTION_PATTERNS, PROCESSED_DIR, CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Field-label patterns
# Each pattern matches the label + delimiter only.  The value span begins at
# match.end() so the label text is never included in a redaction span.
# ---------------------------------------------------------------------------
FIELD_LABEL_PATTERNS: Dict[str, re.Pattern] = {
    "person_name": re.compile(
        r"(?<!\w)(?:Full\s+Name|Patient\s+Name|Child(?:'?s)?\s+Name|Applicant(?:\s+Name)?|"
        r"Nombre|"
        r"Reported\s+by|Emergency\s+Contact|Carer(?:\s+Name)?|Parent|Name)\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "dob": re.compile(
        r"(?<!\w)(?:D\.?O\.?B\.?|Date\s+of\s+Birth|Born)\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "address": re.compile(
        r"(?<!\w)(?<!Email\s)(?:(?:Home\s+|Property\s+|Contact\s+)?Address|Direcci[oó]n)\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "phone": re.compile(
        r"(?<!\w)(?:Emergency\s+Phone|Emergency\s+Tel(?:ephone)?|Mobile|Telephone|"
        r"Tel[eé]fono|"
        r"Contact\s+Number|Phone\s*Number|Phone)\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "email": re.compile(
        r"(?<!\w)Email(?:\s+Address)?\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "nin": re.compile(
        r"(?<!\w)(?:N\.?I\.?\s*(?:Number)?|NIN|National\s+Insurance(?:\s+Number)?|"
        r"National\s+ID)\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "nhs_number": re.compile(
        r"(?<!\w)(?:NHS|N\.?H\.?S\.?|N\s*[HM]\s*S|NMS)\s*(?:Number)?\b(?:\s*[:\-=]\s*|\s+)",
        re.IGNORECASE,
    ),
    "bank_details": re.compile(
        r"(?:Bank\s+Account|Account\s+Number|Sort\s+Code)\s*[:\-]?\s+",
        re.IGNORECASE,
    ),
    "pcn": re.compile(
        r"PCN\s*[:\-]?\s+",
        re.IGNORECASE,
    ),
    "vehicle_reg": re.compile(
        r"(?:Vehicle\s+Reg(?:istration)?|VRM|Registration)\s*[:\-]?\s+",
        re.IGNORECASE,
    ),
    "school": re.compile(
        r"(?:^|\n)\s*School\s*[:\-]?\s+",
        re.IGNORECASE,
    ),
    "signature": re.compile(
        r"Signature\s*[:\-]?\s+",
        re.IGNORECASE,
    ),
    # Notes redacted only when category profile includes "notes"
    "notes": re.compile(
        r"Notes\s*[:\-]?\s+",
        re.IGNORECASE,
    ),
}

# Max chars to read as value after a label (wider for multi-line fields)
_FIELD_VALUE_MAX: Dict[str, int] = {
    "address": 200,
    "notes":   300,
    "signature": 80,
    "nin": 25,        # NI numbers are short; don't let value bleed into next field
    "phone": 20,      # Phone numbers are short; prevents bleeding into next line
    "vehicle_reg": 10,
    "pcn": 22,
    "school": 90,
    "nhs_number": 20,
}
_FIELD_VALUE_DEFAULT_MAX = 60

# Boundary-only labels: terminate a value region but are NOT themselves redacted
_BOUNDARY_ONLY_PATTERNS = [
    r"Date\s*[:\-]?\s+",          # standalone "Date:" — form date, not DOB
    r"Reference\s*[:\-]?\s+",
    r"Ref(?:erence)?\s*No\s*[:\-]?\s+",
    r"Request\s*[:\-]?\s+",
    r"Solicitud\s*[:\-]?\s+",
    r"Fecha\s*[:\-]?\s+",
    r"Nom\s*[:\-]?\s+",
    r"Adresse\s*[:\-]?\s+",
    r"Location\s*[:\-]?\s+",
    r"Issue\s*[:\-]?\s+",
    r"Repair\s+type\s*[:\-]?\s+",
    r"Appeal\s+reason\s*[:\-]?\s+",
    r"Complaint\s*[:\-]?\s+",
    r"Comments\s*[:\-]?\s+",
    r"Description\s*[:\-]?\s+",
    r"Medication\s+list\s*[:\-]?\s+",
    r"Payment\s+date\s*[:\-]?\s+",
    r"Deadline\s+date\s*[:\-]?\s+",
    r"Public\s+authority\s*[:\-]?\s+",
    r"Occupation\s*[:\-]?\s+",
    r"Job\s+Title\s*[:\-]?\s+",
    r"Employer\s*[:\-]?\s+",
    r"Gender\s*[:\-]?\s+",
    r"Case\s+Worker\s*[:\-]?\s+",
    r"Case\s+(?:No|Number|Ref)\s*[:\-]?\s+",
    r"GP\s+(?:Name|Doctor)?\s*[:\-]?\s+",
    r"Doctor\s*[:\-]?\s+",
    r"Status\s*[:\-]?\s+",
    r"Type\s*[:\-]?\s+",
    r"Fax\s*[:\-]?\s+",       # Hospital fax — not patient PII
    r"Tel\s*[:\-]?\s+",        # Org tel line
    r"Re\s*[:\-]?\s+",         # Letter subject line "Re: Patient Medical Summary"
    r"Department\s*[:\-]?\s+",
    r"Sincerely\s*[,\s]+",
    r"Dear\s+",
]

# Combined pattern used ONLY for boundary detection (not for typing spans)
_ANY_LABEL_PATTERN = re.compile(
    "|".join(
        [p.pattern for p in FIELD_LABEL_PATTERNS.values()] + _BOUNDARY_ONLY_PATTERNS
    ),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Medical / safeguarding content detection
# Detects full sentences that describe a patient's health or case details
# ---------------------------------------------------------------------------
_MEDICAL_TERMS_RE = re.compile(
    r"\b(?:"
    # Diagnoses
    r"asthma|an[ae]mia|migraine|diabetes|hypertension|arthritis|depression|anxiety|"
    r"cancer|tumou?r|fracture|infection|disorder|syndrome|condition|disability|"
    r"COPD|epilepsy|dementia|schizophrenia|bipolar|stroke|fibrosis|"
    # Symptoms
    r"shortness\s+of\s+breath|fatigue|nausea|dizziness|headache|insomnia|"
    r"sleep\s+disruption|intermittent|symptomatic|pain|vomiting|vertigo|"
    r"palpitation|seizure|tremor|swelling|inflammation|"
    # Medications / treatments
    r"corticosteroid|supplementation|medication|prescription|inhaler|tablet|"
    r"dose|dosage|prescribed|treatment|therapy|surgery|procedure|injection|"
    r"antibiotic|antidepressant|analgesic|painkiller|chemotherapy|"
    # Clinical context
    r"diagnosis|prognosis|medical\s+history|documented|under\s+our\s+care|"
    r"follow.?up|periodic|appointment|lifestyle\s+recommendation|"
    r"clinical|hospital(?:ised|ized)|admitted|discharge|referral|"
    # Safeguarding / social care
    r"safeguarding|abuse|neglect|vulnerable|concern|at\s+risk|self.harm|"
    r"domestic\s+violence|care\s+plan|social\s+worker|case\s+note"
    r")\b",
    re.IGNORECASE,
)

_PATIENT_REF_RE = re.compile(
    r"\b(?:"
    r"the\s+patient|patient\s+(?:has|had|is|was|reported|may|requires?|needs?)|"
    r"she\s+(?:has|had|is|was|reported|requires?)|"
    r"he\s+(?:has|had|is|was|reported|requires?)|"
    r"her\s+(?:condition|medical|health|symptoms?|diagnos)|"
    r"his\s+(?:condition|medical|health|symptoms?|diagnos)|"
    r"confirms?\s+that\s+(?:the\s+)?(?:Ms|Mr|Mrs)\.?\s+\w+|"
    r"(?:Ms|Mr|Mrs)\.?\s+\w+\s+(?:has|is|was|had|reported)|"
    r"this\s+letter\s+confirms"
    r")\b",
    re.IGNORECASE,
)

_ADDRESS_LINE_RE = re.compile(
    r"\b(?:flat|room|house|road|rd|street|st|avenue|ave|lane|ln|drive|close|"
    r"court|crescent|gardens|way|place|terrace|demo)\b",
    re.IGNORECASE,
)

_HARDSHIP_NOTE_RE = re.compile(
    r"\b(?:cannot\s+afford|can't\s+afford|no\s+money|food\s+bank|homeless|"
    r"eviction|starving|desperate|unsafe\s+at\s+home|feels\s+unsafe)\b",
    re.IGNORECASE,
)


class RedactionEngine:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")

    # ------------------------------------------------------------------
    # Medical / safeguarding content detection
    # ------------------------------------------------------------------
    def detect_medical_content(self, text: str) -> List[Dict[str, Any]]:
        """
        Detect free-text sentences describing a patient's medical condition,
        symptoms, diagnoses, or treatments. Returns spans for the whole sentence.

        Only sentences that BOTH reference the patient AND contain medical
        terminology are flagged — hospital headers, greetings, sign-offs kept.
        """
        if not text:
            return []

        spans: List[Dict[str, Any]] = []
        # Split into sentence-like chunks on period+space or newline
        sentence_ends = [0]
        for m in re.finditer(r'(?<=[.!?])\s+|\n', text):
            sentence_ends.append(m.end())
        sentence_ends.append(len(text))

        for i in range(len(sentence_ends) - 1):
            s = sentence_ends[i]
            e = sentence_ends[i + 1]
            sentence = text[s:e]
            stripped = sentence.strip()
            if len(stripped) < 20:
                continue
            has_medical = bool(_MEDICAL_TERMS_RE.search(stripped))
            has_patient_ref = bool(_PATIENT_REF_RE.search(stripped))
            if has_medical and has_patient_ref:
                # Trim to the actual content (skip leading whitespace)
                leading = len(sentence) - len(sentence.lstrip())
                actual_start = s + leading
                actual_end = e - (len(sentence) - len(sentence.rstrip()))
                if actual_end > actual_start:
                    spans.append({
                        "type": "medical_details",
                        "start": actual_start,
                        "end": actual_end,
                        "value": text[actual_start:actual_end],
                        "confidence": 0.88,
                        "method": "medical_content",
                    })
        return spans

    def detect_context_notes(self, text: str) -> List[Dict[str, Any]]:
        """Detect sensitive hardship/safeguarding sentences when strict profiles allow notes."""
        spans: List[Dict[str, Any]] = []
        if not text:
            return spans

        starts = [0]
        for match in re.finditer(r"(?<=[.!?])\s+|\n", text):
            starts.append(match.end())
        starts.append(len(text))

        for index in range(len(starts) - 1):
            start = starts[index]
            end = starts[index + 1]
            sentence = text[start:end].strip()
            if len(sentence) < 10 or not _HARDSHIP_NOTE_RE.search(sentence):
                continue
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            actual_start = start + leading
            actual_end = end - (len(text[start:end]) - len(text[start:end].rstrip()))
            spans.append({
                "type": "notes",
                "start": actual_start,
                "end": actual_end,
                "value": text[actual_start:actual_end],
                "confidence": 0.82,
                "method": "context_notes",
            })
        return spans

    def detect_contact_header(self, text: str) -> List[Dict[str, Any]]:
        """Detect unlabeled name/address blocks at the top of handwritten letters."""
        if not text:
            return []

        lines: list[tuple[int, int, str]] = []
        offset = 0
        for raw_line in text.splitlines(keepends=True):
            line_start = offset
            line_end = offset + len(raw_line.rstrip("\n\r"))
            line_text = raw_line.strip()
            offset += len(raw_line)
            if line_text:
                lines.append((line_start, line_end, line_text))

        header: list[tuple[int, int, str]] = []
        for line in lines[:8]:
            line_text = line[2]
            if re.match(r"^(?:date|dear|to\s+the|parking\s+appeal|safeguarding|council\s+tax)\b", line_text, re.IGNORECASE):
                break
            header.append(line)

        if len(header) < 2:
            return self.detect_address_phrases(text)

        has_contact_signal = any(
            REDACTION_PATTERNS["email"].search(line[2])
            or REDACTION_PATTERNS["phone"].search(line[2])
            or REDACTION_PATTERNS["postcode"].search(line[2])
            or _ADDRESS_LINE_RE.search(line[2])
            for line in header
        )
        if not has_contact_signal:
            return self.detect_address_phrases(text)

        spans: list[dict[str, Any]] = []
        first_start, first_end, first_text = header[0]
        if (
            2 <= len(first_text.split()) <= 4
            and not any(char.isdigit() for char in first_text)
            and ":" not in first_text
            and not _ANY_LABEL_PATTERN.search(first_text)
        ):
            spans.append({
                "type": "person_name",
                "start": first_start,
                "end": first_end,
                "value": text[first_start:first_end],
                "confidence": 0.78,
                "method": "contact_header",
            })

        for start, end, line_text in header[1:]:
            if _ANY_LABEL_PATTERN.search(line_text):
                continue
            if re.search(r"^(?:email|phone|mobile|tel|telephone)\b", line_text, re.IGNORECASE):
                continue
            if _ADDRESS_LINE_RE.search(line_text) or REDACTION_PATTERNS["postcode"].search(line_text):
                spans.append({
                    "type": "address",
                    "start": start,
                    "end": end,
                    "value": text[start:end],
                    "confidence": 0.80,
                    "method": "contact_header",
                })

        spans.extend(self.detect_address_phrases(text))
        return spans

    def detect_address_phrases(self, text: str) -> list[dict[str, Any]]:
        """Detect address values in simple free-text phrases such as 'I live at ...'."""
        spans: list[dict[str, Any]] = []
        for match in re.finditer(r"\bI\s+live\s+at\s+(.+?)(?:\.|\n|$)", text, re.IGNORECASE):
            value_start = match.start(1)
            value_end = match.end(1)
            value = text[value_start:value_end].strip()
            if len(value) >= 6:
                spans.append({
                    "type": "address",
                    "start": value_start,
                    "end": value_end,
                    "value": value,
                    "confidence": 0.82,
                    "method": "address_phrase",
                })

        return spans

    # ------------------------------------------------------------------
    # Field-label detection — returns VALUE spans only, labels excluded
    # ------------------------------------------------------------------
    def detect_field_labels(self, text: str) -> List[Dict[str, Any]]:
        """
        Scan for structured field labels (e.g. "Full Name:", "DOB:") and return
        spans that cover ONLY the value following each label.
        The label text itself is NOT included, so redaction boxes never cover labels.
        """
        if not text:
            return []

        # All label/boundary positions for value-end clipping (finditer is L→R)
        all_label_starts = [m.start() for m in _ANY_LABEL_PATTERN.finditer(text)]

        spans: List[Dict[str, Any]] = []
        for field_type, pattern in FIELD_LABEL_PATTERNS.items():
            for match in pattern.finditer(text):
                value_start = match.end()
                max_len = _FIELD_VALUE_MAX.get(field_type, _FIELD_VALUE_DEFAULT_MAX)

                # Clip value at the next label boundary or max_len
                next_label = next((s for s in all_label_starts if s > value_start), None)
                raw_end = min(
                    value_start + max_len,
                    next_label if next_label is not None else len(text),
                )
                if field_type not in {"address", "notes"}:
                    next_newline = text.find("\n", value_start)
                    if next_newline != -1:
                        raw_end = min(raw_end, next_newline)

                raw = text[value_start:raw_end]

                # Compute actual start/end after stripping leading/trailing noise
                leading_spaces = len(raw) - len(raw.lstrip())
                trailing_spaces = len(raw) - len(raw.rstrip(" \t\n\r,;|"))
                actual_start = value_start + leading_spaces
                actual_end = raw_end - trailing_spaces
                actual_value = text[actual_start:actual_end]

                if not actual_value or len(actual_value.strip()) < 2:
                    continue

                spans.append({
                    "type": field_type,
                    "start": actual_start,
                    "end": actual_end,
                    "value": actual_value,
                    "confidence": 0.95,
                    "method": "field_label",
                })
        return spans

    # ------------------------------------------------------------------
    # Main PII detection
    # ------------------------------------------------------------------
    def detect_sensitive_text(
        self,
        text: str,
        llm_engine=None,
        allowed_types: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """
        Tiered PII detection (highest to lowest priority):
          0. Field-label detection  — value-only spans, label preserved  [0.95]
          1. LLM (Qwen)             — context-aware free text             [0.82]
          2. Regex                  — structured patterns                 [0.85-0.90]
          3. spaCy NER              — fallback only, requires LLM absent  [0.65-0.70]

        allowed_types: if provided, only spans of those types are returned
                       (enables profile-based filtering).
        """
        spans: List[Dict[str, Any]] = []

        # --- 0. Field-label detection ---
        spans.extend(self.detect_field_labels(text))
        spans.extend(self.detect_contact_header(text))

        # --- 0b. Medical/safeguarding content detection (sentence-level) ---
        if allowed_types is None or "medical_details" in allowed_types:
            medical_spans = self.detect_medical_content(text)
            for ms in medical_spans:
                if not any(s["start"] < ms["end"] and s["end"] > ms["start"] for s in spans):
                    spans.append(ms)

        if allowed_types is None or "notes" in allowed_types:
            note_spans = self.detect_context_notes(text)
            for ns in note_spans:
                if not any(s["start"] < ns["end"] and s["end"] > ns["start"] for s in spans):
                    spans.append(ns)

        # --- 1. LLM-based PII detection ---
        if llm_engine is not None and llm_engine.available:
            pii_items = llm_engine.identify_pii(text)
            for item in pii_items:
                value = item.get("value", "")
                if not value or len(value) < 2:
                    continue
                # Strip any label prefix the LLM may have included
                value = self._strip_label_prefix(value)
                if not value or len(value) < 2:
                    continue
                idx = text.find(value)
                if idx == -1:
                    idx = text.lower().find(value.lower())
                if idx == -1:
                    continue
                end = idx + len(value)
                if not any(s["start"] < end and s["end"] > idx for s in spans):
                    spans.append({
                        "type": item["type"],
                        "start": idx,
                        "end": end,
                        "value": value,
                        "confidence": 0.82,
                        "method": "llm",
                    })

        # --- 2. Regex patterns ---
        dob_label_ends = [m.end() for m in FIELD_LABEL_PATTERNS["dob"].finditer(text)]

        REGEX_CONFIDENCE = {
            "email": 0.90, "nin": 0.90, "bank_account": 0.90,
            "phone": 0.88, "postcode": 0.88, "dob": 0.88,
            "vehicle_reg": 0.85, "council_ref": 0.80,
        }
        _MONTH_RE = re.compile(
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b",
            re.IGNORECASE,
        )
        for rtype, pattern in REDACTION_PATTERNS.items():
            for match in pattern.finditer(text):
                match_text = match.group()
                if rtype == "dob" and not self._is_near_dob_label(
                    match.start(), dob_label_ends, text
                ):
                    continue
                # Skip vehicle_reg matches that look like dates (contain a month name)
                if rtype == "vehicle_reg" and _MONTH_RE.search(match_text):
                    continue
                if rtype == "phone":
                    digits = re.sub(r"\D", "", match_text)
                    if len(digits) < 10:
                        continue
                if rtype == "council_ref":
                    digits = re.sub(r"\D", "", match_text)
                    if len(digits) < 4:
                        continue
                s, e = match.start(), match.end()
                if not any(sp["start"] < e and sp["end"] > s for sp in spans):
                    spans.append({
                        "type": rtype,
                        "start": s,
                        "end": e,
                        "value": match_text,
                        "confidence": REGEX_CONFIDENCE.get(rtype, 0.85),
                        "method": "regex",
                    })

        # --- 3. spaCy NER (fallback) ---
        if (llm_engine is None or not llm_engine.available) and len(text) > 100:
            doc = self.nlp(text)
            for ent in doc.ents:
                if len(ent.text.strip()) < 4:
                    continue
                if ent.label_ not in ("PERSON", "GPE", "ORG", "LOC"):
                    continue
                s, e = ent.start_char, ent.end_char
                if not any(sp["start"] < e and sp["end"] > s for sp in spans):
                    conf = 0.70 if ent.label_ == "PERSON" else 0.65
                    spans.append({
                        "type": ent.label_.lower(),
                        "start": s,
                        "end": e,
                        "value": ent.text,
                        "confidence": conf,
                        "method": "ner",
                    })

        # --- Profile filter ---
        if allowed_types:
            spans = [s for s in spans if s["type"] in allowed_types]

        spans.sort(key=lambda s: s["start"])
        return spans

    # ------------------------------------------------------------------
    # Bbox mapping with proportional sub-block slicing
    # ------------------------------------------------------------------
    def map_to_bboxes(
        self,
        sensitive_spans: List[Dict[str, Any]],
        ocr_words: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Map character-level text spans to OCR bounding boxes.

        KEY FIX: When a span covers only PART of an OCR block (e.g. the value
        portion of "Full Name: Daniel Mercer"), compute a proportional sub-bbox
        so the label region is NOT covered by the redaction box.
        """
        if not ocr_words:
            return []

        # Build char-to-word index AND record each word's start position in flat text
        flat_text = ""
        char_to_word: List[Optional[int]] = []
        word_char_start: Dict[int, int] = {}

        for i, word in enumerate(ocr_words):
            word_char_start[i] = len(flat_text)
            for _ in word["text"]:
                char_to_word.append(i)
            char_to_word.append(None)   # inter-word space
            flat_text += word["text"] + " "

        # Remove the trailing space entry
        if char_to_word and char_to_word[-1] is None:
            char_to_word.pop()
            flat_text = flat_text.rstrip()

        redactions = []
        for span in sensitive_spans:
            start = span["start"]
            end = span["end"]
            if start >= len(char_to_word) or end > len(char_to_word):
                continue

            # Collect word indices touched by this span
            word_indices: set = set()
            for idx in range(start, min(end, len(char_to_word))):
                wi = char_to_word[idx]
                if wi is not None:
                    word_indices.add(wi)

            if not word_indices:
                continue

            bboxes = []
            for wi in sorted(word_indices):
                word = ocr_words[wi]
                w_start = word_char_start[wi]
                w_len = len(word["text"])
                if w_len == 0:
                    continue

                # Characters within this word that overlap with the span
                char_in_word_start = max(start, w_start) - w_start
                char_in_word_end = min(end, w_start + w_len) - w_start

                # Proportional sub-bbox: covers only the value portion
                sub_bbox = self._proportional_bbox(
                    word["bbox"],
                    char_in_word_start,
                    char_in_word_end,
                    w_len,
                )
                bboxes.append({"bbox": sub_bbox, "confidence": word["confidence"]})

            if not bboxes:
                continue

            merged = self._merge_bboxes(bboxes)
            confidence = min(
                span["confidence"],
                min(b["confidence"] for b in bboxes),
            )
            redactions.append({
                "type": span["type"],
                "bboxes": merged,
                "confidence": round(confidence, 4),
                "method": span.get("method", "ocr_bboxes"),
                "value": span.get("value", ""),
            })

        return redactions

    def _proportional_bbox(
        self,
        bbox: List[List[int]],
        char_start: int,
        char_end: int,
        total_chars: int,
    ) -> List[List[int]]:
        """
        Return a sub-bbox covering chars [char_start, char_end) within a block
        of total_chars characters, using linear x-interpolation.

        For a line like "Full Name: Daniel Mercer" where the block covers x=10..200:
          char_start=11, char_end=24, total=24
          → x_start = 10 + (11/24)*(190) ≈ 97
          → x_end   = 10 + (24/24)*(190) = 200
        Only "Daniel Mercer" is covered; "Full Name: " is not.
        """
        if total_chars == 0 or char_start >= char_end:
            return bbox

        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        width = x_max - x_min

        t_start = char_start / total_chars
        t_end = char_end / total_chars

        x_s = int(x_min + t_start * width)
        x_e = int(x_min + t_end * width)

        return [[x_s, y_min], [x_e, y_min], [x_e, y_max], [x_s, y_max]]

    def _merge_bboxes(self, bboxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge horizontally-adjacent bboxes on the same line."""
        if not bboxes:
            return []
        if len(bboxes) == 1:
            return bboxes

        sorted_boxes = sorted(bboxes, key=lambda b: (b["bbox"][0][1], b["bbox"][0][0]))
        merged = []
        current = sorted_boxes[0]

        for nxt in sorted_boxes[1:]:
            cy = [p[1] for p in current["bbox"]]
            ny = [p[1] for p in nxt["bbox"]]
            y_overlap = max(0, min(max(cy), max(ny)) - max(min(cy), min(ny)))
            height = max(max(cy) - min(cy), max(ny) - min(ny)) or 1
            if y_overlap / height > 0.5:
                all_pts = current["bbox"] + nxt["bbox"]
                xs = [p[0] for p in all_pts]
                ys = [p[1] for p in all_pts]
                current = {
                    "bbox": [
                        [min(xs), min(ys)], [max(xs), min(ys)],
                        [max(xs), max(ys)], [min(xs), max(ys)],
                    ],
                    "confidence": min(current["confidence"], nxt["confidence"]),
                }
            else:
                merged.append(current)
                current = nxt
        merged.append(current)
        return merged

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _strip_label_prefix(self, value: str) -> str:
        """Remove leading label text (e.g. 'Full Name: ') from LLM results."""
        stripped = _ANY_LABEL_PATTERN.sub("", value, count=1).strip()
        return stripped if stripped else value

    def _is_near_dob_label(
        self,
        match_start: int,
        dob_label_ends: List[int],
        text: str,
    ) -> bool:
        """
        True if a numeric date match is:
        - directly after a DOB label (within 5 chars), OR
        - free-text (not preceded by a generic "Date:" label)
        False if preceded by standalone "Date:" — those should NOT be redacted.
        """
        for label_end in dob_label_ends:
            if 0 <= match_start - label_end <= 5:
                return True
        before = text[max(0, match_start - 35): match_start]
        if re.search(r"(?<!\w)Date\s*[:\-]?\s+$", before, re.IGNORECASE):
            return False
        return True

    # ------------------------------------------------------------------
    # Image / text redaction
    # ------------------------------------------------------------------
    def redact_image(
        self,
        image_path: str,
        redactions: List[Dict[str, Any]],
        out_dir: Optional[str] = None,
    ) -> str:
        """Draw opaque black rectangles over redaction regions."""
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")

        h, w = image.shape[:2]
        for red in redactions:
            for box in red["bboxes"]:
                bbox = box["bbox"]
                xs = [int(p[0]) for p in bbox]
                ys = [int(p[1]) for p in bbox]
                x1 = max(0, min(xs) - 4)
                x2 = min(w, max(xs) + 4)
                y1 = max(0, min(ys) - 4)
                y2 = min(h, max(ys) + 4)
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 0), -1)

        dest_dir = out_dir or PROCESSED_DIR
        os.makedirs(dest_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(image_path))[0]
        out_path = os.path.join(dest_dir, "redacted.png")
        cv2.imwrite(out_path, image)
        return out_path

    def redact_text(self, text: str, sensitive_spans: List[Dict[str, Any]]) -> str:
        """Replace sensitive spans with [REDACTED-{type}]."""
        spans = sorted(sensitive_spans, key=lambda s: s["start"], reverse=True)
        result = text
        for span in spans:
            s, e, rtype = span["start"], span["end"], span["type"]
            if 0 <= s < len(result) and s < e <= len(result):
                result = result[:s] + f"[REDACTED-{rtype}]" + result[e:]
        return result

    def generate_mask_overlay(
        self,
        image_path: str,
        redactions: List[Dict[str, Any]],
        out_dir: Optional[str] = None,
    ) -> str:
        """Generate semi-transparent red overlay preview."""
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")

        overlay = image.copy()
        h, w = image.shape[:2]
        for red in redactions:
            for box in red["bboxes"]:
                bbox = box["bbox"]
                xs = [int(p[0]) for p in bbox]
                ys = [int(p[1]) for p in bbox]
                x1 = max(0, min(xs) - 4)
                x2 = min(w, max(xs) + 4)
                y1 = max(0, min(ys) - 4)
                y2 = min(h, max(ys) + 4)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)

        result = cv2.addWeighted(overlay, 0.4, image, 0.6, 0)

        dest_dir = out_dir or PROCESSED_DIR
        os.makedirs(dest_dir, exist_ok=True)
        out_path = os.path.join(dest_dir, "redaction_preview.png")
        cv2.imwrite(out_path, result)
        return out_path

    # ------------------------------------------------------------------
    # Handwriting safety pass
    # ------------------------------------------------------------------
    def handwriting_safety_pass(
        self,
        redacted_image_path: str,
        ocr_blocks: List[Dict[str, Any]],
        avg_confidence: float,
        allowed_types: Optional[set] = None,
    ) -> bool:
        """
        Safety redaction pass for handwritten / low-confidence documents.

        When avg OCR confidence < 0.75, text-span mapping is unreliable.
        This pass works directly on image coordinates:

        1. Header block  — everything above the "Date:" line is sender PII
                           (name, address, email, phone written before the date)
        2. Label-triggered line redaction — detects label keywords in OCR
                           block text; redacts the rest of that line
        3. Closing / signature region — detects "Yours faithfully / sincerely /
                           regards" and blacks out from there to image bottom
        4. Sensitive content lines — lines containing medical/vulnerability
                           keywords are fully redacted (when medical profile active)

        Modifies redacted_image_path in-place.
        Returns True if any extra redactions were applied.
        """
        if avg_confidence >= 0.90:
            return False  # High-confidence typed document — normal pass is sufficient

        image = cv2.imread(redacted_image_path)
        if image is None:
            return False
        h, w = image.shape[:2]

        if not ocr_blocks:
            return False

        # ---- bbox helpers ----
        def _coords(block):
            xs = [p[0] for p in block["bbox"]]
            ys = [p[1] for p in block["bbox"]]
            return min(xs), max(xs), min(ys), max(ys)

        def _yc(block):
            _, _, y0, y1 = _coords(block)
            return (y0 + y1) / 2

        avg_height = sum((_coords(b)[3] - _coords(b)[2]) for b in ocr_blocks) / len(ocr_blocks)
        line_tol = max(avg_height * 0.7, 8)

        def _line_blocks(ref_block):
            return [b for b in ocr_blocks if abs(_yc(b) - _yc(ref_block)) <= line_tol]

        def _line_groups():
            groups: List[List[Dict[str, Any]]] = []
            for block in sorted(ocr_blocks, key=lambda b: (_yc(b), _coords(b)[0])):
                for group in groups:
                    group_y = sum(_yc(gb) for gb in group) / len(group)
                    if abs(_yc(block) - group_y) <= line_tol:
                        group.append(block)
                        break
                else:
                    groups.append([block])
            for group in groups:
                group.sort(key=lambda b: _coords(b)[0])
            return groups

        def _group_rect(group):
            coords = [_coords(b) for b in group]
            x0 = min(c[0] for c in coords)
            x1 = max(c[1] for c in coords)
            y0 = min(c[2] for c in coords)
            y1 = max(c[3] for c in coords)
            return x0, x1, y0, y1

        def _group_text(group):
            return " ".join(str(b.get("text", "")) for b in group)

        modified = False

        # ----------------------------------------------------------------
        # 1. Header block — redact everything above the "Date:" line
        # ----------------------------------------------------------------
        _DATE_LABEL_RE = re.compile(r"\bDate\b", re.IGNORECASE)
        date_block = next((b for b in ocr_blocks if _DATE_LABEL_RE.search(b["text"])), None)
        if date_block:
            _, _, date_y0, _ = _coords(date_block)
            header_bottom = max(0, int(date_y0) - 4)
            if header_bottom > 10:
                cv2.rectangle(image, (0, 0), (w, header_bottom), (0, 0, 0), -1)
                modified = True

        # ----------------------------------------------------------------
        # 2. Label-triggered line redaction
        # ----------------------------------------------------------------
        LABEL_TRIGGERS = {
            "name": "person_name",
            "email": "email",
            "phone": "phone", "mobile": "phone", "tel": "phone", "number": "phone",
            "address": "address", "postcode": "postcode",
            "dob": "dob", "born": "dob", "birth": "dob",
            "nin": "nin", "national": "nin", "nhs": "nhs_number", "id": "nin",
            "ref": "council_ref", "reference": "council_ref",
            "signature": "signature",
        }
        for block in ocr_blocks:
            tokens = re.split(r"[\s:,=]+", block["text"].lower())
            triggered = next((LABEL_TRIGGERS[t] for t in tokens if t in LABEL_TRIGGERS), None)
            if not triggered:
                continue
            if allowed_types and triggered not in allowed_types:
                continue

            line = _line_blocks(block)
            x0_label, x1_label, _, _ = _coords(block)
            x_line_end = max(_coords(b)[1] for b in line)
            y_top = max(0, int(min(_coords(b)[2] for b in line)) - 3)
            y_bot = min(h, int(max(_coords(b)[3] for b in line)) + 3)

            if x_line_end > x1_label + 5:
                # Value is in a SEPARATE block to the right of the label block
                cv2.rectangle(image, (int(x1_label), y_top), (min(w, int(x_line_end) + 5), y_bot), (0, 0, 0), -1)
                modified = True
            else:
                # Label and value are in the SAME block (e.g. "phone number=07000000000")
                # Estimate label width as the position of the separator char
                block_text = block["text"]
                sep_match = re.search(r"[=:\-]", block_text)
                if sep_match:
                    sep_ratio = sep_match.end() / max(len(block_text), 1)
                    x0_blk, x1_blk, y0_blk, y1_blk = _coords(block)
                    x_val_start = int(x0_blk + sep_ratio * (x1_blk - x0_blk))
                    if x1_blk > x_val_start + 4:
                        cv2.rectangle(image, (x_val_start, y_top), (min(w, x1_blk + 5), y_bot), (0, 0, 0), -1)
                        modified = True

        # ----------------------------------------------------------------
        # 2a. Visual low-confidence form fallback.
        #
        # If handwriting OCR has mangled labels ("phone number" -> "Aamle
        # Auynker"), text rules will miss the value. For low-confidence
        # handwritten forms, mask the value side of the first structured
        # field lines and the lines under an address-like section heading.
        # This is intentionally conservative: it may over-redact, but it
        # prevents obvious handwritten PII from being left visible.
        # ----------------------------------------------------------------
        if avg_confidence < 0.50:
            groups = _line_groups()
            address_heading_index: Optional[int] = None

            for idx, group in enumerate(groups[:8]):
                x0, x1, y0, y1 = _group_rect(group)
                text_line = _group_text(group)
                compact = re.sub(r"\W+", "", text_line.lower())
                has_digit = any(ch.isdigit() for ch in text_line)
                has_email_hint = bool(REDACTION_PATTERNS["email"].search(text_line))
                has_separator = any(str(b.get("text", "")).strip() in {"=", ":", "-"} for b in group)

                # A short left-side line after the main labelled fields is
                # usually a section heading like "address" in handwritten
                # notes, even if OCR reads it as "@dlyesS".
                if (
                    idx >= 3
                    and not has_digit
                    and not has_email_hint
                    and x0 < w * 0.28
                    and (x1 - x0) < w * 0.35
                    and y0 < h * 0.70
                ):
                    if address_heading_index is None:
                        address_heading_index = idx
                    continue

                looks_like_sensitive_field = (
                    idx < 4
                    and y0 < h * 0.55
                    and (has_digit or has_email_hint or has_separator or len(compact) > 8)
                )
                if not looks_like_sensitive_field:
                    continue

                sep_blocks = [
                    b for b in group
                    if str(b.get("text", "")).strip() in {"=", ":", "-"}
                ]
                if sep_blocks:
                    value_start = max(_coords(b)[1] for b in sep_blocks) + 3
                else:
                    value_start = int(x0 + 0.45 * (x1 - x0))

                y_top = max(0, int(y0) - 5)
                y_bot = min(h, int(y1) + 5)
                x_left = max(0, min(w, int(value_start)))
                x_right = min(w, int(x1) + 8)
                if x_right > x_left + 10:
                    cv2.rectangle(image, (x_left, y_top), (x_right, y_bot), (0, 0, 0), -1)
                    modified = True

            if address_heading_index is not None:
                for group in groups[address_heading_index + 1: address_heading_index + 4]:
                    x0, x1, y0, y1 = _group_rect(group)
                    if y0 > h * 0.78:
                        break
                    y_top = max(0, int(y0) - 5)
                    y_bot = min(h, int(y1) + 5)
                    x_left = max(0, int(x0) - 8)
                    x_right = min(w, int(x1) + 8)
                    if x_right > x_left + 10:
                        cv2.rectangle(image, (x_left, y_top), (x_right, y_bot), (0, 0, 0), -1)
                        modified = True

        # ----------------------------------------------------------------
        # 2b. Value-pattern sweep — catch phone/email/postcode/NIN/NHS by
        #     value regex directly in each OCR block, regardless of label quality.
        #     This is the nuclear fallback for mangled OCR labels.
        # ----------------------------------------------------------------
        _PHONE_VAL_RE = re.compile(r"\b0[\d\s]{9,12}\b|\+44[\d\s]{9,12}")
        _EMAIL_VAL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
        _POST_VAL_RE  = re.compile(r"\b[A-Z]{1,2}\d[\dA-Z]?\s?\d[A-Z]{2}\b", re.IGNORECASE)
        _NIN_VAL_RE   = re.compile(r"\b[A-Z]{2}\s*\d{6}\s*[A-D]\b", re.IGNORECASE)
        _NHS_VAL_RE   = re.compile(r"\b\d{3}\s*[-\s]?\d{3}\s*[-\s]?\d{4}\b|\b\d{5,}[-\s]\d{2,}\b")
        VALUE_PATTERNS = [
            (_PHONE_VAL_RE,  "phone"),
            (_EMAIL_VAL_RE,  "email"),
            (_POST_VAL_RE,   "postcode"),
            (_NIN_VAL_RE,    "nin"),
            (_NHS_VAL_RE,    "nhs_number"),
        ]
        for block in ocr_blocks:
            btext = block["text"]
            x0_blk, x1_blk, y0_blk, y1_blk = _coords(block)
            block_w = max(x1_blk - x0_blk, 1)
            block_len = max(len(btext), 1)
            for val_re, vtype in VALUE_PATTERNS:
                if allowed_types and vtype not in allowed_types:
                    continue
                m = val_re.search(btext)
                if not m:
                    continue
                # Proportional sub-bbox covering matched value only
                x_start = int(x0_blk + (m.start() / block_len) * block_w)
                x_end   = int(x0_blk + (m.end()   / block_len) * block_w)
                if x_end > x_start + 2:
                    cv2.rectangle(image,
                                  (max(0, x_start - 2), max(0, y0_blk - 2)),
                                  (min(w, x_end + 4),   min(h, y1_blk + 2)),
                                  (0, 0, 0), -1)
                    modified = True

        # ----------------------------------------------------------------
        # 3. Closing / signature region — redact from closing line to bottom
        # ----------------------------------------------------------------
        _CLOSING_RE = re.compile(
            r"\b(?:yours|faithfully|sincerely|regards|signed)\b", re.IGNORECASE
        )
        closing_y = None
        for block in ocr_blocks:
            if _CLOSING_RE.search(block["text"]):
                _, _, y0, _ = _coords(block)
                if closing_y is None or y0 < closing_y:
                    closing_y = y0
        if closing_y is not None:
            cv2.rectangle(image, (0, max(0, int(closing_y) - 4)), (w, h), (0, 0, 0), -1)
            modified = True

        # ----------------------------------------------------------------
        # 4. Sensitive content lines (medical / vulnerability keywords)
        # ----------------------------------------------------------------
        _SENSITIVE_LINE_RE = re.compile(
            r"\b(?:medically?|diagnosed?|allerg(?:y|ic)|symptom|breathing|"
            r"health|illness|medication|prescribed|condition|disability|"
            r"abuse|vulnerable|neglect|unsafe|self.harm|violence|concern)\b",
            re.IGNORECASE,
        )
        if allowed_types is None or "medical_details" in allowed_types:
            for block in ocr_blocks:
                if _SENSITIVE_LINE_RE.search(block["text"]):
                    line = _line_blocks(block)
                    y0 = max(0, int(min(_coords(b)[2] for b in line)) - 3)
                    y1 = min(h, int(max(_coords(b)[3] for b in line)) + 3)
                    cv2.rectangle(image, (0, y0), (w, y1), (0, 0, 0), -1)
                    modified = True

        if modified:
            cv2.imwrite(redacted_image_path, image)
        return modified
