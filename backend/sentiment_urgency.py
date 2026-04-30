from config import SENSITIVE_KEYWORDS, CATEGORY_URGENCY_BASE, CONFIDENCE_THRESHOLD


class SentimentUrgencyEngine:
    def __init__(self):
        self.keywords = SENSITIVE_KEYWORDS
        self.urgency_bases = CATEGORY_URGENCY_BASE

    def analyze(self, text: str, category: str = "unknown") -> dict:
        """
        Analyze sentiment, urgency, and risk flags.
        Returns {urgency_score, sentiment, risk_flags, confidence}.
        """
        text_lower = text.lower()

        risk_flags = {}
        for flag_name, keywords in self.keywords.items():
            matched = any(kw.lower() in text_lower for kw in keywords)
            if matched:
                risk_flags[flag_name] = True

        # Sentiment classification
        negative_words = ["unhappy", "dissatisfied", "terrible", "awful", "bad", "poor", "disgusting", "useless", "furious", "angry", "worried", "scared", "desperate"]
        positive_words = ["happy", "satisfied", "good", "excellent", "thank", "grateful", "pleased"]
        distress_words = ["suicide", "self-harm", "depression", "desperate", "nowhere", "hopeless"]
        angry_words = ["disgusting", "unacceptable", "useless", "terrible", "furious", "angry", "outrage"]

        neg_count = sum(1 for w in negative_words if w in text_lower)
        pos_count = sum(1 for w in positive_words if w in text_lower)
        distress_count = sum(1 for w in distress_words if w in text_lower)
        angry_count = sum(1 for w in angry_words if w in text_lower)

        if distress_count > 0:
            sentiment = "distressed"
        elif angry_count > 0:
            sentiment = "angry"
        elif neg_count > pos_count and neg_count > 0:
            sentiment = "negative"
        elif pos_count > neg_count and pos_count > 0:
            sentiment = "positive"
        else:
            sentiment = "neutral"

        # Urgency score
        base = self.urgency_bases.get(category, 0.2)
        urgency = base
        urgency += 0.2 * len(risk_flags)
        if sentiment in ("angry", "distressed"):
            urgency += 0.1
        urgency = min(1.0, urgency)

        confidence = 0.75 if len(risk_flags) > 0 else 0.60

        return {
            "urgency_score": round(urgency, 4),
            "sentiment": sentiment,
            "risk_flags": list(risk_flags.keys()),
            "confidence": round(confidence, 4),
        }
