from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


CRITICAL_PII_TYPES = {
    "person_name",
    "child_name",
    "age",
    "child_age",
    "address",
    "phone",
    "email",
    "dob",
    "nhs_number",
    "nin",
    "case_reference",
    "council_ref",
    "medical_details",
    "safeguarding_context",
    "signature",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def training_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: str | Path, base: Path | None = None) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    search_base = base or repo_root()
    return (search_base / value).resolve()


def ensure_parent(path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    out = ensure_parent(path)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return out


def read_manifest(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError("Manifest must be .jsonl or .csv")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def levenshtein(first: str, second: str) -> int:
    if first == second:
        return 0
    if not first:
        return len(second)
    if not second:
        return len(first)

    previous = list(range(len(second) + 1))
    for i, char_a in enumerate(first, start=1):
        current = [i]
        for j, char_b in enumerate(second, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def levenshtein_sequence(first: list[str], second: list[str]) -> int:
    if first == second:
        return 0
    if not first:
        return len(second)
    if not second:
        return len(first)

    previous = list(range(len(second) + 1))
    for i, token_a in enumerate(first, start=1):
        current = [i]
        for j, token_b in enumerate(second, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (token_a != token_b),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(prediction: str, truth: str) -> float:
    truth_text = str(truth or "")
    if not truth_text:
        return 0.0 if not prediction else 1.0
    return levenshtein(str(prediction or ""), truth_text) / len(truth_text)


def word_error_rate(prediction: str, truth: str) -> float:
    truth_words = normalize_text(truth).split()
    pred_words = normalize_text(prediction).split()
    if not truth_words:
        return 0.0 if not pred_words else 1.0
    return levenshtein_sequence(pred_words, truth_words) / len(truth_words)


def token_recall(prediction: str, expected_values: Iterable[str]) -> dict[str, Any]:
    pred = normalize_text(prediction)
    expected = [str(item or "").strip() for item in expected_values if str(item or "").strip()]
    found = [item for item in expected if normalize_text(item) in pred]
    missed = [item for item in expected if item not in found]
    return {
        "expected": len(expected),
        "found": len(found),
        "missed": missed,
        "recall": (len(found) / len(expected)) if expected else 1.0,
    }


def bbox_iou(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 0.0
    ax0, ay0, ax1, ay1 = map(float, a)
    bx0, by0, bx1, by1 = map(float, b)
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    intersection = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def mean(values: Iterable[float]) -> float:
    items = [float(value) for value in values if math.isfinite(float(value))]
    return sum(items) / len(items) if items else 0.0


def manifest_key(row: dict[str, Any]) -> str:
    image = Path(str(row.get("image_path") or "")).as_posix()
    page = row.get("page_number", 1)
    bbox = row.get("line_bbox") or ""
    return f"{image}|{page}|{bbox}"
