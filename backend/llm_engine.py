import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5-council"

CLASSIFY_PROMPT = """You are an AI assistant for Hillingdon Council (UK local government).
Analyse the following document text and return a JSON object with exactly these fields:

- "category": one of exactly these values:
    housing_repairs, council_tax, parking, complaint, waste,
    adult_social_care, children_safeguarding, foi_legal, translation, unknown
- "department": the recommended council department name (string)
- "urgency_score": a float from 0.0 (low) to 1.0 (critical)
- "sentiment": one of: neutral, negative, angry, distressed, positive
- "risk_flags": a JSON array containing zero or more of:
    safeguarding, distress, financial_hardship, angry, unsafe_housing, repeated_complaint
- "summary": one sentence (max 20 words) describing the document

Department mappings:
  housing_repairs -> Housing & Property Services
  council_tax -> Revenue & Benefits
  parking -> Parking Services
  complaint -> Customer Relations
  waste -> Environmental Services
  adult_social_care -> Adult Social Care
  children_safeguarding -> Children's Services / Safeguarding
  foi_legal -> Legal & Governance
  translation -> Customer Services / Translation Hub
  unknown -> General Enquiries

Urgency rules:
  children_safeguarding or safeguarding risk flag -> urgency >= 0.85
  distress or financial_hardship -> urgency >= 0.65
  repeated complaint -> urgency >= 0.55
  standard complaint -> urgency 0.3-0.5

Return ONLY valid JSON with no explanation, no markdown, no code fences.

Document text:
{text}"""

TRANSLATE_PROMPT = """Translate the following text into English.
Return ONLY the translated text with no explanation, no preamble, no notes.
Preserve the original formatting and line breaks.

Text to translate:
{text}"""

DETECT_LANG_PROMPT = """What language is the following text written in?
Reply with ONLY the ISO 639-1 two-letter language code (e.g. en, es, fr, de, ar, zh).
No explanation.

Text:
{text}"""

IDENTIFY_PII_PROMPT = """You are a UK council data protection officer. Your job is to identify Personal Identifiable Information (PII) in document text.

Given the following text, return a JSON array of PII items found. Each item must have:
- "type": one of: person_name, address, phone, email, dob, nin, vehicle_reg, bank_details
- "value": the exact substring from the text that is PII

Rules:
- ONLY flag actual PII — real names, real addresses, phone numbers, emails, dates of birth, national insurance numbers, vehicle registrations, bank details
- Do NOT flag common words, place names used generically, job titles, organisation names, or greetings like "Hello World"
- Do NOT flag things that are not personal data
- If there is NO PII, return an empty array: []
- Return ONLY valid JSON array, no explanation, no markdown

Text:
{text}"""


def _ollama_request(prompt: str, temperature: float = 0.1) -> str:
    """Send a request to the local Ollama API and return the response text."""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": 512},
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode())
        return body.get("response", "").strip()


def llm_available() -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            return any(MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False


class LLMEngine:
    """Qwen-backed engine for classification, sentiment, and translation via Ollama."""

    def __init__(self) -> None:
        self._available = llm_available()
        if self._available:
            logger.info("LLM engine ready — using %s via Ollama", MODEL)
        else:
            logger.warning("Ollama / %s not available — LLM features disabled", MODEL)

    @property
    def available(self) -> bool:
        return self._available

    def classify_and_analyse(self, text: str) -> dict[str, Any]:
        """
        Use Qwen to classify the document and extract sentiment/urgency/risk.
        Returns a dict with: category, department, urgency_score, sentiment,
        risk_flags, summary, confidence.
        Falls back to empty result on failure.
        """
        if not self._available:
            return {}
        try:
            prompt = CLASSIFY_PROMPT.format(text=text[:3000])
            raw = _ollama_request(prompt, temperature=0.1)
            # Strip any accidental markdown fences
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)
            # Validate and normalise
            result.setdefault("confidence", 0.82)
            result["risk_flags"] = result.get("risk_flags") or []
            result["urgency_score"] = float(result.get("urgency_score", 0.3))
            return result
        except Exception as exc:
            logger.warning("LLM classify failed: %s", exc)
            return {}

    def detect_language(self, text: str) -> str:
        """
        Ask Qwen what language a text is in.
        Returns ISO 639-1 code, defaults to 'en' on failure.
        """
        if not self._available:
            return "en"
        try:
            prompt = DETECT_LANG_PROMPT.format(text=text[:500])
            code = _ollama_request(prompt, temperature=0.0).lower().strip()
            # Keep only first 5 chars in case model returns more
            return code[:5].strip() if code else "en"
        except Exception as exc:
            logger.warning("LLM language detect failed: %s", exc)
            return "en"

    def identify_pii(self, text: str) -> list[dict]:
        """
        Ask Qwen to identify PII in text with document context awareness.
        Returns list of {type, value} dicts. Empty list if no PII or on failure.
        """
        if not self._available or not text.strip():
            return []
        try:
            prompt = IDENTIFY_PII_PROMPT.format(text=text[:3000])
            raw = _ollama_request(prompt, temperature=0.0)
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)
            if isinstance(result, list):
                return [r for r in result if isinstance(r, dict) and "type" in r and "value" in r]
            return []
        except Exception as exc:
            logger.warning("LLM PII identification failed: %s", exc)
            return []

    def translate(self, text: str) -> str:
        """
        Translate text to English using Qwen.
        Returns original text on failure.
        """
        if not self._available:
            return text
        try:
            prompt = TRANSLATE_PROMPT.format(text=text[:3000])
            result = _ollama_request(prompt, temperature=0.1)
            return result if result else text
        except Exception as exc:
            logger.warning("LLM translate failed: %s", exc)
            return text
