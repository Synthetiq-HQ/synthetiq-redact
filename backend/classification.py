from config import CATEGORIES, DEPARTMENTS


class ClassificationEngine:
    def __init__(self):
        self.categories = CATEGORIES
        self.departments = DEPARTMENTS

    def classify_document(self, text: str) -> dict:
        """
        Keyword-based document classification.
        Returns {category, confidence}.
        """
        text_lower = text.lower()
        scores = {}
        for category, keywords in self.categories.items():
            score = 0
            for keyword in keywords:
                count = text_lower.count(keyword.lower())
                # Longer keyword matches get more weight
                weight = len(keyword.split())
                score += count * weight
            scores[category] = score

        if not scores or all(v == 0 for v in scores.values()):
            return {"category": "unknown", "confidence": 0.0}

        total = sum(scores.values())
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        if total == 0:
            confidence = 0.0
        else:
            confidence = round(best_score / total, 4)

        # If best score is 0, return unknown
        if best_score == 0:
            return {"category": "unknown", "confidence": 0.0}

        return {"category": best_category, "confidence": confidence}

    def recommend_department(self, category: str) -> str:
        """Map category to department name."""
        return self.departments.get(category, self.departments["unknown"])
