from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from training_utils import read_manifest


@dataclass
class OCRSample:
    image_path: str
    text: str


class ManifestTrocrDataset:
    def __init__(self, rows: list[dict[str, Any]], processor: Any, max_target_length: int, image_size: int):
        self.rows = rows
        self.processor = processor
        self.max_target_length = max_target_length
        self.image_size = image_size

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        image = Image.open(row["image_path"]).convert("RGB")
        bbox = row.get("line_bbox")
        if bbox:
            x0, y0, x1, y1 = [int(float(value)) for value in bbox]
            image = image.crop((max(0, x0 - 8), max(0, y0 - 6), min(image.width, x1 + 8), min(image.height, y1 + 6)))
        image.thumbnail((self.image_size, self.image_size))
        pixel_values = self.processor(images=image, return_tensors="pt").pixel_values.squeeze(0)
        labels = self.processor.tokenizer(
            row["text"],
            padding="max_length",
            max_length=self.max_target_length,
            truncation=True,
        ).input_ids
        labels = [label if label != self.processor.tokenizer.pad_token_id else -100 for label in labels]
        return {"pixel_values": pixel_values, "labels": labels}


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        path = "backend/training/configs/trocr_small_handwriting.json"
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune TrOCR on handwriting line crops.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--config", default="backend/training/configs/trocr_small_handwriting.json")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--resume-from-checkpoint", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.output_dir:
        config["output_dir"] = args.output_dir

    try:
        import torch
        from transformers import (
            EarlyStoppingCallback,
            Seq2SeqTrainer,
            Seq2SeqTrainingArguments,
            TrOCRProcessor,
            VisionEncoderDecoderModel,
        )
    except Exception as exc:
        raise RuntimeError("Install torch and transformers before training TrOCR.") from exc

    rows = read_manifest(args.manifest)
    random.Random(int(config.get("seed", 42))).shuffle(rows)
    train_rows = [row for row in rows if row.get("split") == "train"]
    eval_rows = [row for row in rows if row.get("split") in {"validation", "valid", "dev"}]
    if not train_rows:
        raise ValueError("Manifest has no train rows.")
    if not eval_rows:
        eval_rows = train_rows[: max(1, min(64, len(train_rows) // 10 or 1))]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "train_rows": len(train_rows),
                    "eval_rows": len(eval_rows),
                    "base_model": config["base_model"],
                    "output_dir": config["output_dir"],
                    "cuda_available": torch.cuda.is_available(),
                },
                indent=2,
            )
        )
        return 0

    processor = TrOCRProcessor.from_pretrained(config["base_model"])
    model = VisionEncoderDecoderModel.from_pretrained(config["base_model"])
    if config.get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable()

    model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
    model.config.pad_token_id = processor.tokenizer.pad_token_id
    model.config.vocab_size = model.config.decoder.vocab_size
    model.config.eos_token_id = processor.tokenizer.sep_token_id
    model.config.max_length = int(config.get("max_target_length", 128))
    model.config.early_stopping = True
    model.config.no_repeat_ngram_size = 3
    model.config.length_penalty = 2.0
    model.config.num_beams = 4

    train_dataset = ManifestTrocrDataset(
        train_rows,
        processor,
        int(config.get("max_target_length", 128)),
        int(config.get("image_size", 384)),
    )
    eval_dataset = ManifestTrocrDataset(
        eval_rows,
        processor,
        int(config.get("max_target_length", 128)),
        int(config.get("image_size", 384)),
    )

    training_args = Seq2SeqTrainingArguments(
        output_dir=config["output_dir"],
        per_device_train_batch_size=int(config.get("train_batch_size", 2)),
        per_device_eval_batch_size=int(config.get("eval_batch_size", 2)),
        gradient_accumulation_steps=int(config.get("gradient_accumulation_steps", 8)),
        learning_rate=float(config.get("learning_rate", 5e-5)),
        weight_decay=float(config.get("weight_decay", 0.01)),
        num_train_epochs=float(config.get("num_train_epochs", 6)),
        warmup_ratio=float(config.get("warmup_ratio", 0.05)),
        fp16=bool(config.get("fp16", True)) and torch.cuda.is_available(),
        predict_with_generate=True,
        evaluation_strategy="steps",
        save_strategy="steps",
        eval_steps=int(config.get("eval_steps", 250)),
        save_steps=int(config.get("save_steps", 250)),
        logging_steps=int(config.get("logging_steps", 25)),
        save_total_limit=int(config.get("save_total_limit", 3)),
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to=[],
        seed=int(config.get("seed", 42)),
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=processor.feature_extractor,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=int(config.get("early_stopping_patience", 3)))],
    )
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    trainer.save_model(config["output_dir"])
    processor.save_pretrained(config["output_dir"])
    print(json.dumps({"status": "complete", "output_dir": config["output_dir"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
