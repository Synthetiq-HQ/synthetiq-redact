"""
Vision API judge for evaluating redaction quality.
Supports Kimi (Moonshot), OpenAI, and local Ollama vision models.
"""

import base64
import json
import os
from typing import Optional
import requests


class VisionJudge:
    """Send images to a vision-capable LLM and get structured analysis."""

    def __init__(
        self,
        provider: str = "kimi",  # 'kimi', 'openai', 'ollama'
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.provider = provider.lower()
        if self.provider == "kimi":
            self.api_key = api_key or os.environ.get("KIMI_API_KEY") or ""
        elif self.provider == "openai":
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        else:
            self.api_key = api_key or ""

        # Provider defaults
        if self.provider == "kimi":
            self.base_url = base_url or "https://api.moonshot.cn/v1"
            self.model = model or "moonshot-v1-8k-vision-preview"
        elif self.provider == "openai":
            self.base_url = base_url or "https://api.openai.com/v1"
            self.model = model or "gpt-4o"
        elif self.provider == "ollama":
            self.base_url = base_url or "http://localhost:11434"
            self.model = model or "llava"
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _encode_image(self, image_bytes: bytes) -> str:
        return base64.b64encode(image_bytes).decode("utf-8")

    def _build_messages(self, original_b64: str, redacted_b64: str) -> list:
        prompt = (
            "You are an expert document analyst evaluating a council document redaction system.\n"
            "You will see TWO images of the same document:\n"
            "1. ORIGINAL (before redaction)\n"
            "2. REDACTED (after sensitive info was blacked out)\n\n"
            "Analyze both carefully and respond with ONLY a valid JSON object (no markdown, no explanation).\n\n"
            "The JSON must have exactly these fields:\n"
            '{\n'
            '  "category": "one of: housing_repairs, council_tax, parking, complaint, waste, adult_social_care, children_safeguarding, foi_legal, translation, unknown",\n'
            '  "department": "the council department this should route to",\n'
            '  "urgency_score": 0.0 to 1.0,\n'
            '  "sentiment": "neutral, negative, angry, distressed, or positive",\n'
            '  "risk_flags": ["safeguarding", "distress", "financial_hardship", "angry", "unsafe_housing", "repeated_complaint"], zero or more,\n'
            '  "pii_detected_original": [\n'
            '    {"type": "person_name|address|phone|email|dob|nin|vehicle_reg|bank_details", "value": "exact text found"}\n'
            '  ],\n'
            '  "pii_should_be_redacted": ["list of exact values that MUST be redacted"],\n'
            '  "pii_actually_redacted": ["list of exact values that appear to be blacked out in redacted image"],\n'
            '  "missed_redactions": ["values that SHOULD have been redacted but are still visible"],\n'
            '  "false_positives": ["values that were redacted but should NOT have been"],\n'
            '  "redaction_completeness": 0.0 to 1.0,\n'
            '  "redaction_accuracy": 0.0 to 1.0,\n'
            '  "category_correct_guess": true|false,\n'
            '  "notes": "brief observations"\n'
            '}'
        )

        if self.provider == "ollama":
            return [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [original_b64, redacted_b64],
                }
            ]

        # OpenAI / Kimi format
        return [
            {
                "role": "system",
                "content": "You are a document redaction evaluator. Always respond with valid JSON only.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{original_b64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{redacted_b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ]

    def judge(self, original_bytes: bytes, redacted_bytes: bytes) -> dict:
        """Send both images to the vision model and return parsed JSON."""
        original_b64 = self._encode_image(original_bytes)
        redacted_b64 = self._encode_image(redacted_bytes)
        messages = self._build_messages(original_b64, redacted_b64)

        if self.provider == "ollama":
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
        else:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 2048,
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]

        # Clean up markdown fences if any
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)


if __name__ == "__main__":
    # Quick smoke test
    judge = VisionJudge(provider="ollama")
    print("VisionJudge initialized:", judge.model)
