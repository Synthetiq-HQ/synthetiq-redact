from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


MODEL_FILES = [
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "special_tokens_map.json",
]

WEIGHT_PATTERNS = ["*.safetensors", "*.bin", "*.pt", "*.pth", "*.ckpt"]


def copy_matching(source: Path, output: Path, include_weights: bool) -> list[str]:
    copied = []
    for filename in MODEL_FILES:
        candidate = source / filename
        if candidate.exists():
            shutil.copy2(candidate, output / filename)
            copied.append(filename)

    if include_weights:
        for pattern in WEIGHT_PATTERNS:
            for candidate in source.glob(pattern):
                shutil.copy2(candidate, output / candidate.name)
                copied.append(candidate.name)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a TrOCR model folder for local backend integration.")
    parser.add_argument("--source", required=True, help="Trainer output/checkpoint folder.")
    parser.add_argument("--output", required=True, help="Local exported model folder.")
    parser.add_argument("--include-weights", action="store_true", help="Copy weight files. Do not commit them.")
    parser.add_argument("--backend-name", default="trocr_local")
    parser.add_argument("--base-model", default="microsoft/trocr-small-handwritten")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)
    if not source.exists():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)

    copied = copy_matching(source, output, args.include_weights)
    metadata = {
        "backend": args.backend_name,
        "base_model": args.base_model,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "weights_included": args.include_weights,
        "files": copied,
        "environment": {
            "HANDWRITING_OCR_BACKEND": args.backend_name,
            "HANDWRITING_OCR_MODEL_PATH": str(output.resolve()),
        },
        "safety": {
            "auto_release_handwriting": False,
            "low_confidence_forces_review": True,
        },
    }
    (output / "synthetiq_model_export.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
