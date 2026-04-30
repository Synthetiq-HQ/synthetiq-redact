"""
Mass evaluation runner for Synthetiq Redact.

Usage:
    # Run on 50 synthetic forms using local Ollama vision judge
    python -m evaluation.run_evaluation --dataset synthetic --count 50 --judge ollama

    # Run on local folder using Kimi API
    python -m evaluation.run_evaluation --dataset local --path ./my_docs --judge kimi --api-key $KIMI_API_KEY

    # Run on CORD receipts with OpenAI
    python -m evaluation.run_evaluation --dataset cord --judge openai --api-key $OPENAI_API_KEY
"""

import argparse
import json
import os
import time
import sys
from pathlib import Path
from typing import Optional

# Load .env if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
except Exception:
    pass

# Add parent to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.eval_client import process_image, get_image_bytes
from evaluation.vision_judge import VisionJudge
from evaluation.scorer import EvaluationScorer, DocumentScore
from evaluation.dataset_loader import get_dataset


def run_evaluation(
    dataset_name: str = "synthetic",
    dataset_path: Optional[str] = None,
    count: int = 50,
    judge_provider: str = "ollama",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    output_dir: str = "./evaluation_results",
    skip_judge: bool = False,
) -> None:
    """Run full evaluation pipeline."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SYNTHETIQ REDACT - MASS EVALUATION HARNESS")
    print("=" * 60)
    print(f"Dataset:    {dataset_name}")
    print(f"Count:      {count}")
    print(f"Judge:      {judge_provider}")
    print(f"Output:     {out_dir.absolute()}")
    print("=" * 60)

    # 1. Load dataset
    print("\n[1/4] Loading dataset...")
    kwargs = {"count": count}
    if dataset_path:
        kwargs["path"] = dataset_path
    image_paths = get_dataset(dataset_name, **kwargs)[:count]
    print(f"      -> {len(image_paths)} images ready")

    if not image_paths:
        print("[ERROR] No images found. Exiting.")
        return

    # 2. Initialize judge
    judge = None if skip_judge else VisionJudge(
        provider=judge_provider,
        api_key=api_key,
        model=model,
    )

    scorer = EvaluationScorer()
    scores: list[DocumentScore] = []

    # 3. Process each image
    print("\n[2/4] Running redaction pipeline + vision judge...")
    for idx, img_path in enumerate(image_paths, 1):
        print(f"\n  [{idx}/{len(image_paths)}] {img_path.name}")

        # Run local pipeline
        backend_result = process_image(img_path)
        if not backend_result:
            print(f"      [FAIL] Pipeline failed for {img_path.name}")
            continue

        doc_id = backend_result.get("id")
        print(f"      [OK] Pipeline complete (doc_id={doc_id})")

        # Vision judge
        judge_result = None
        if judge and doc_id:
            try:
                print(f"      -> Sending to {judge_provider} vision judge...")
                original_bytes = get_image_bytes(doc_id, "original")
                redacted_bytes = get_image_bytes(doc_id, "redacted")
                judge_result = judge.judge(original_bytes, redacted_bytes)

                # Save raw judge response
                raw_path = out_dir / f"{img_path.stem}_judge.json"
                raw_path.write_text(json.dumps(judge_result, indent=2), encoding="utf-8")
                print(f"      [OK] Judge scored: completeness={judge_result.get('redaction_completeness', 0):.2f}")
            except Exception as e:
                print(f"      [FAIL] Judge failed: {e}")
                judge_result = None

        # Score
        if judge_result:
            score = scorer.score_document(
                judge_result=judge_result,
                backend_result=backend_result,
                filename=img_path.name,
                doc_id=doc_id,
            )
            scores.append(score)
            print(f"      -> Overall score: {score.overall_score:.2f}")

            # Save per-doc report
            doc_report = {
                "filename": img_path.name,
                "doc_id": doc_id,
                "backend": backend_result,
                "judge": judge_result,
                "score": {
                    "overall": score.overall_score,
                    "completeness": score.redaction_completeness,
                    "accuracy": score.redaction_accuracy,
                    "recall": score.pii_recall,
                    "precision": score.pii_precision,
                    "category_correct": score.category_correct,
                },
            }
            (out_dir / f"{img_path.stem}_report.json").write_text(
                json.dumps(doc_report, indent=2, default=str), encoding="utf-8"
            )

        time.sleep(0.5)  # Be nice to local APIs

    # 4. Summarize
    print("\n[3/4] Generating summary report...")
    if scores:
        summary = scorer.summarize(scores)
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        for k, v in summary.items():
            print(f"  {k:30s}: {v}")
        print("=" * 60)

        scorer.save_report(scores, out_dir / "evaluation_report.json")
    else:
        print("  No scores to report.")

    print("\n[4/4] Done.")
    print(f"Results saved to: {out_dir.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Synthetiq Redact Mass Evaluation")
    parser.add_argument("--dataset", default="synthetic", choices=["synthetic", "local", "cord", "iam", "handwritten", "nist", "rimes"])
    parser.add_argument("--path", default=None, help="Path for local dataset")
    parser.add_argument("--count", type=int, default=50, help="Max images to evaluate")
    parser.add_argument("--judge", default="ollama", choices=["kimi", "openai", "ollama"])
    parser.add_argument("--api-key", default=None, help="API key for Kimi/OpenAI")
    parser.add_argument("--model", default=None, help="Model name override")
    parser.add_argument("--output", default="./evaluation_results", help="Output directory")
    parser.add_argument("--skip-judge", action="store_true", help="Only run pipeline, skip vision judging")
    args = parser.parse_args()

    run_evaluation(
        dataset_name=args.dataset,
        dataset_path=args.path,
        count=args.count,
        judge_provider=args.judge,
        api_key=args.api_key,
        model=args.model,
        output_dir=args.output,
        skip_judge=args.skip_judge,
    )


if __name__ == "__main__":
    main()
