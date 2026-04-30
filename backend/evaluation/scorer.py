"""
Scoring logic for redaction evaluation results.
Computes aggregate metrics and per-document scores.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class DocumentScore:
    filename: str
    doc_id: int
    category_guess: str
    category_actual: str
    category_correct: bool
    department_guess: str
    redaction_completeness: float
    redaction_accuracy: float
    missed_count: int
    false_positive_count: int
    pii_recall: float
    pii_precision: float
    urgency_score: float
    risk_flags_matched: float
    overall_score: float
    judge_notes: str


class EvaluationScorer:
    """Score a batch of evaluated documents."""

    def score_document(self, judge_result: dict, backend_result: dict, filename: str, doc_id: int) -> DocumentScore:
        """Compute scores from vision judge output + backend metadata."""
        jr = judge_result
        br = backend_result or {}

        cat_correct = jr.get("category_correct_guess", False)
        if not cat_correct:
            # Fallback: compare strings loosely
            cat_correct = jr.get("category", "").lower().replace(" ", "_") == (br.get("category") or "").lower()

        should_redact = set(jr.get("pii_should_be_redacted", []))
        actually_redacted = set(jr.get("pii_actually_redacted", []))
        missed = set(jr.get("missed_redactions", []))
        false_pos = set(jr.get("false_positives", []))

        # PII metrics
        total_should = len(should_redact) or 1
        total_actually = len(actually_redacted) or 1
        recall = len(should_redact & actually_redacted) / total_should
        precision = len(should_redact & actually_redacted) / total_actually

        # Weighted overall score
        completeness = float(jr.get("redaction_completeness", 0))
        accuracy = float(jr.get("redaction_accuracy", 0))

        overall = (
            completeness * 0.30 +
            accuracy * 0.30 +
            recall * 0.20 +
            precision * 0.10 +
            (1.0 if cat_correct else 0.0) * 0.10
        )

        return DocumentScore(
            filename=filename,
            doc_id=doc_id,
            category_guess=jr.get("category", ""),
            category_actual=br.get("category", ""),
            category_correct=cat_correct,
            department_guess=jr.get("department", ""),
            redaction_completeness=completeness,
            redaction_accuracy=accuracy,
            missed_count=len(missed),
            false_positive_count=len(false_pos),
            pii_recall=recall,
            pii_precision=precision,
            urgency_score=float(jr.get("urgency_score", 0)),
            risk_flags_matched=1.0 if jr.get("risk_flags") else 0.0,
            overall_score=round(overall, 3),
            judge_notes=jr.get("notes", "")[:200],
        )

    def summarize(self, scores: List[DocumentScore]) -> dict:
        """Aggregate stats across all evaluated documents."""
        if not scores:
            return {}
        n = len(scores)
        return {
            "documents_evaluated": n,
            "avg_overall_score": round(sum(s.overall_score for s in scores) / n, 3),
            "avg_completeness": round(sum(s.redaction_completeness for s in scores) / n, 3),
            "avg_accuracy": round(sum(s.redaction_accuracy for s in scores) / n, 3),
            "avg_recall": round(sum(s.pii_recall for s in scores) / n, 3),
            "avg_precision": round(sum(s.pii_precision for s in scores) / n, 3),
            "category_accuracy": round(sum(1 for s in scores if s.category_correct) / n, 3),
            "total_missed": sum(s.missed_count for s in scores),
            "total_false_positives": sum(s.false_positive_count for s in scores),
        }

    def save_report(self, scores: List[DocumentScore], out_path: str | Path):
        """Save full evaluation report to JSON."""
        out_path = Path(out_path)
        report = {
            "summary": self.summarize(scores),
            "documents": [asdict(s) for s in scores],
        }
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[Scorer] Report saved to {out_path}")
