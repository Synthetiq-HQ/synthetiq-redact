import logging
import re
from typing import Optional

from transformers import MarianMTModel, MarianTokenizer

from redaction import RedactionEngine

logger = logging.getLogger(__name__)

# Map langdetect codes to Helsinki-NLP model names (source->en direction)
# Uses multi-language "ROMANCE" model as fallback for many Romance languages
LANG_TO_MODEL: dict[str, str] = {
    "de": "Helsinki-NLP/opus-mt-de-en",
    "es": "Helsinki-NLP/opus-mt-es-en",
    "fr": "Helsinki-NLP/opus-mt-fr-en",
    "it": "Helsinki-NLP/opus-mt-it-en",
    "pt": "Helsinki-NLP/opus-mt-ROMANCE-en",
    "nl": "Helsinki-NLP/opus-mt-nl-en",
    "pl": "Helsinki-NLP/opus-mt-pl-en",
    "ro": "Helsinki-NLP/opus-mt-ROMANCE-en",
    "ru": "Helsinki-NLP/opus-mt-ru-en",
    "zh-cn": "Helsinki-NLP/opus-mt-zh-en",
    "zh-tw": "Helsinki-NLP/opus-mt-zh-en",
    "ar": "Helsinki-NLP/opus-mt-ar-en",
    "tr": "Helsinki-NLP/opus-mt-tr-en",
    "uk": "Helsinki-NLP/opus-mt-uk-en",
}


class TranslationEngine:
    def __init__(self) -> None:
        # Lazy-load: models are cached here on first use per language pair
        self._model_cache: dict[str, tuple[MarianTokenizer, MarianMTModel]] = {}
        self._redaction_engine = RedactionEngine()

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        """
        Detect the language of text using langdetect.
        Returns an ISO 639-1 code (e.g. 'en', 'es', 'de').
        Falls back to 'en' if detection fails or text is too short.
        """
        try:
            from langdetect import detect, LangDetectException
            if len(text.strip()) < 20:
                return "en"
            code = detect(text)
            return code
        except Exception as exc:
            logger.warning("Language detection failed: %s", exc)
            return "en"

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def translate(self, text: str, source_lang: str, target_lang: str = "en") -> str:
        """
        Translate text from source_lang to target_lang using Helsinki-NLP Marian models.
        Re-redacts the translated output to catch any PII that survived translation.
        Returns original text unchanged if the language pair is unsupported.
        """
        if source_lang == target_lang:
            return text

        model_name = LANG_TO_MODEL.get(source_lang)
        if model_name is None:
            logger.warning("No translation model for '%s' -> '%s'; skipping.", source_lang, target_lang)
            return text

        tokenizer, model = self._get_model(model_name)

        chunks = self._chunk_text(text, max_chars=400)
        translated_chunks: list[str] = []
        for chunk in chunks:
            inputs = tokenizer(chunk, return_tensors="pt", padding=True, truncation=True, max_length=512)
            outputs = model.generate(**inputs)
            translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
            translated_chunks.append(translated)

        translated_text = " ".join(translated_chunks)

        # Re-redact: translation may expose new PII patterns
        spans = self._redaction_engine.detect_sensitive_text(translated_text)
        return self._redaction_engine.redact_text(translated_text, spans)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_model(self, model_name: str) -> tuple[MarianTokenizer, MarianMTModel]:
        """Lazy-load and cache a MarianMT model by HuggingFace model name."""
        if model_name not in self._model_cache:
            logger.info("Loading translation model: %s", model_name)
            tokenizer = MarianTokenizer.from_pretrained(model_name)
            model = MarianMTModel.from_pretrained(model_name)
            self._model_cache[model_name] = (tokenizer, model)
            logger.info("Translation model loaded: %s", model_name)
        return self._model_cache[model_name]

    def _chunk_text(self, text: str, max_chars: int = 400) -> list[str]:
        """Split text into sentence-level chunks under max_chars characters."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks: list[str] = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) + 1 <= max_chars:
                current = (current + " " + sent).strip()
            else:
                if current:
                    chunks.append(current)
                current = sent
        if current:
            chunks.append(current)
        return chunks if chunks else [text[:max_chars]]
