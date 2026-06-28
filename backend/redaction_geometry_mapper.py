"""
Geometry-based value-to-pixel mapper for hybrid (GLM + layout-OCR) redaction.

The problem this solves
-----------------------
On handwriting we have two half-blind sources:
  * GLM-OCR  -> excellent transcription, but NO pixel coordinates.
  * EasyOCR  -> word boxes in the right places, but garbled text on handwriting.

The existing RedactionEngine.map_to_bboxes assumes detection text and box text
come from the SAME source (shared character offsets). That assumption breaks here,
because the sensitive spans are detected on GLM text while the boxes come from
EasyOCR. So we map by POSITION instead of by shared offsets:

  1. GLM gives the canonical text, split into lines (reading order) and the
     character span of each sensitive value within its line.
  2. EasyOCR word boxes are clustered into visual lines (text ignored).
  3. Each value is matched to a line cluster by reading-order position, refined by
     a fuzzy text match for distinctive tokens (reference/email/phone/postcode).
  4. The value's sub-box is sliced from the line by label-anchored character
     fraction ("Email: <value>" -> only the value), or taken whole when the
     cluster IS the value (signature, fuzzy-matched reference).
  5. A confidence + needs_review flag is attached. Low-confidence or implausibly
     large matches are flagged for human review, never silently applied as a
     broad blackout.

Output boxes use the app's canonical bbox format:
    {"bbox": [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]}
"""

from __future__ import annotations

import re
import difflib
from typing import Any, Dict, List, Optional, Tuple

GEOMETRY_METHOD = "glm_geometry"

# Types specific/distinctive enough that a whole-page fuzzy match is safe.
DISTINCTIVE_TYPES = {"reference", "case_reference", "email", "phone", "postcode"}
# A low-confidence box bigger than this fraction of the page is suppressed to a
# page review flag instead of being drawn (prevents paragraph blackouts).
MAX_LOWCONF_AREA_FRAC = 0.06


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


class RedactionGeometryMapper:
    def __init__(self, pad: int = 6, line_merge_factor: float = 0.7):
        self.pad = pad
        self.line_merge_factor = line_merge_factor

    # -- line clustering ----------------------------------------------------

    def _cluster_lines(self, ocr_words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group EasyOCR word boxes into visual lines by vertical position."""
        toks = []
        for w in ocr_words:
            pts = w.get("bbox") or []
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            toks.append({
                "text": w.get("text", ""),
                "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
                "yc": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys),
            })
        if not toks:
            return []
        toks.sort(key=lambda d: d["yc"])
        med_h = sorted(t["h"] for t in toks)[len(toks) // 2] or 20

        clusters: List[Dict[str, Any]] = []
        for tk in toks:
            if clusters and abs(tk["yc"] - clusters[-1]["yc"]) < self.line_merge_factor * med_h:
                c = clusters[-1]
                c["toks"].append(tk)
                c["x0"] = min(c["x0"], tk["x0"]); c["y0"] = min(c["y0"], tk["y0"])
                c["x1"] = max(c["x1"], tk["x1"]); c["y1"] = max(c["y1"], tk["y1"])
                c["yc"] = sum(t["yc"] for t in c["toks"]) / len(c["toks"])
            else:
                clusters.append({"toks": [tk], "x0": tk["x0"], "y0": tk["y0"],
                                 "x1": tk["x1"], "y1": tk["y1"], "yc": tk["yc"]})
        for c in clusters:
            ordered = sorted(c["toks"], key=lambda d: d["x0"])
            c["norm"] = _norm("".join(t["text"] for t in ordered))
        clusters.sort(key=lambda c: c["y0"])
        return clusters

    # -- GLM line/offset helpers -------------------------------------------

    @staticmethod
    def _line_index(line_starts: List[int], offset: int) -> int:
        for i in range(len(line_starts) - 1, -1, -1):
            if offset >= line_starts[i]:
                return i
        return 0

    # -- cluster selection --------------------------------------------------

    def _select(self, span_type: str, value: str, ordinal: Optional[int],
                total_nonempty: int, is_last_occurrence: bool, is_signature: bool,
                clusters: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str, float, bool]:
        """Return (cluster, mode, confidence, needs_review)."""
        M = len(clusters)
        nv = _norm(value)

        # Signature -> the last line of the page.
        if is_signature or (is_last_occurrence and ordinal is not None and ordinal >= total_nonempty - 3):
            return clusters[-1], "whole", 0.70, False

        # Header/contact block: the first non-empty lines (letterhead + labelled
        # fields) are
        # not wrapped, so they map 1:1 to the first visual clusters. Use a DIRECT
        # index here - proportional scaling drifts because body wrapping inflates M.
        if ordinal is not None and ordinal <= 10 and ordinal < M:
            return clusters[ordinal], "fraction", 0.80, False

        exp = None if ordinal is None or total_nonempty <= 1 else ordinal / (total_nonempty - 1) * (M - 1)

        # Distinctive tokens: whole-page fuzzy (handles values buried in body text).
        if span_type in DISTINCTIVE_TYPES:
            best, best_r = self._best_fuzzy(nv, clusters)
            if best and best_r >= 0.55:
                return best, "whole", 0.72, False

        # Header / labeled-field lines map by reading order; refine within a band.
        if exp is not None:
            lo, hi = max(0, int(exp) - 3), min(M - 1, int(exp) + 3)
            band = clusters[lo:hi + 1]
            best, best_r = self._best_fuzzy(nv, band)
            if best and best_r >= 0.45:
                return best, "fraction", 0.80, False
            # No text confirmation: fall back to nearest by position, flag review.
            return clusters[min(M - 1, max(0, round(exp)))], "fraction", 0.40, True

        # Last resort: best fuzzy anywhere, flagged.
        best, best_r = self._best_fuzzy(nv, clusters)
        if best:
            return best, "whole", 0.35, True
        return None, "none", 0.0, True

    @staticmethod
    def _best_fuzzy(nv: str, clusters: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
        best, best_r = None, 0.0
        for c in clusters:
            cn = c.get("norm", "")
            if not cn:
                continue
            r = difflib.SequenceMatcher(None, nv, cn).ratio()
            if nv and (nv in cn or cn in nv):
                r = max(r, 0.8)
            if r > best_r:
                best, best_r = c, r
        return best, best_r

    def map_selected_text(
        self,
        value: str,
        ocr_words: List[Dict[str, Any]],
        image_w: int,
        image_h: int,
        redaction_type: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        """
        Map an explicit user text selection to the best visual line.

        This is stricter than map(): the reviewer has selected an exact value in
        the clean transcription, so we search the OCR visual lines for that value
        first instead of trusting reading-order position. It avoids body text like
        "(Ref: HILL-REQ-48392)" being placed on an earlier, unrelated line.
        """
        clusters = self._cluster_lines(ocr_words)
        nv = _norm(value)
        if not clusters or len(nv) < 2:
            return None

        best, best_r, best_idx = None, 0.0, -1
        for cluster in clusters:
            cn = cluster.get("norm", "")
            if not cn:
                continue
            idx = cn.find(nv)
            if idx >= 0:
                score = 0.95
                window_idx = idx
            else:
                score = difflib.SequenceMatcher(None, nv, cn).ratio()
                window_idx = -1
                if len(cn) > len(nv):
                    for start in range(0, len(cn) - len(nv) + 1):
                        candidate = cn[start:start + len(nv)]
                        candidate_score = difflib.SequenceMatcher(None, nv, candidate).ratio()
                        if candidate_score > score:
                            score = candidate_score
                            window_idx = start
            if score > best_r:
                best, best_r, best_idx = cluster, score, window_idx

        if best is None or best_r < 0.45:
            return None

        cn = best.get("norm", "")
        if best_idx >= 0 and len(cn) > 0:
            f0 = max(0.0, best_idx / len(cn))
            f1 = min(1.0, (best_idx + len(nv)) / len(cn))
        else:
            # Fuzzy-but-not-substring match: take the full matching line and mark
            # it lower confidence rather than placing the box by page position.
            f0, f1 = 0.0, 1.0
            best_r = min(best_r, 0.50)

        lw = best["x1"] - best["x0"]
        x0 = max(0.0, best["x0"] + f0 * lw - self.pad)
        x1 = min(float(image_w), best["x0"] + f1 * lw + self.pad)
        y0 = max(0.0, best["y0"] - self.pad)
        y1 = min(float(image_h), best["y1"] + self.pad)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None

        return {
            "type": redaction_type,
            "original_value": value[:255],
            "bbox": {
                "bbox": [
                    [round(x0, 2), round(y0, 2)],
                    [round(x1, 2), round(y0, 2)],
                    [round(x1, 2), round(y1, 2)],
                    [round(x0, 2), round(y1, 2)],
                ]
            },
            "confidence": round(max(0.45, min(0.95, best_r)), 3),
            "method": "text_selection",
            "needs_review": best_r < 0.55,
        }

    # -- public API ---------------------------------------------------------

    def map(self, glm_text: str, sensitive_spans: List[Dict[str, Any]],
            ocr_words: List[Dict[str, Any]], image_w: int, image_h: int) -> List[Dict[str, Any]]:
        clusters = self._cluster_lines(ocr_words)
        if not clusters or not glm_text:
            return []

        raw_lines = glm_text.split("\n")
        line_starts, acc = [], 0
        for ln in raw_lines:
            line_starts.append(acc)
            acc += len(ln) + 1
        nonempty_ord: Dict[int, int] = {}
        o = 0
        for i, ln in enumerate(raw_lines):
            if ln.strip():
                nonempty_ord[i] = o
                o += 1
        total_nonempty = max(o, 1)
        page_area = max(1, image_w * image_h)

        redactions: List[Dict[str, Any]] = []
        for span in sensitive_spans:
            start = int(span.get("start", -1))
            value = span.get("value", "") or ""
            stype = span.get("type", "redaction")
            if start < 0 or not value:
                continue
            li = self._line_index(line_starts, start)
            line = raw_lines[li]
            if not line.strip():
                continue
            off = start - line_starts[li]
            f0 = max(0.0, off / len(line))
            f1 = min(1.0, (off + len(value)) / len(line))
            ordinal = nonempty_ord.get(li)

            is_signature = stype in {"signature"} or (
                stype.startswith("name") and ordinal is not None and ordinal >= total_nonempty - 3
            )
            is_last = ordinal is not None and ordinal >= total_nonempty - 3

            cluster, mode, conf, needs_review = self._select(
                stype, value, ordinal, total_nonempty, is_last, is_signature, clusters
            )
            if cluster is None:
                continue

            if mode == "fraction":
                # Slice the value out of its line by character fraction. Full-line
                # values (name/address) have f0~0,f1~1 so this is a no-op for them;
                # labelled lines ("Email: x", "Uxbridge, UB8 2PL") get value-only.
                lw = cluster["x1"] - cluster["x0"]
                vx0 = cluster["x0"] + f0 * lw
                vx1 = cluster["x0"] + f1 * lw
            else:
                vx0, vx1 = cluster["x0"], cluster["x1"]

            x0 = max(0.0, vx0 - self.pad)
            y0 = max(0.0, cluster["y0"] - self.pad)
            x1 = min(float(image_w), vx1 + self.pad)
            y1 = min(float(image_h), cluster["y1"] + self.pad)
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue

            # Suppress implausibly large low-confidence boxes to a review flag only.
            area_frac = ((x1 - x0) * (y1 - y0)) / page_area
            suppress_box = needs_review and area_frac > MAX_LOWCONF_AREA_FRAC

            redactions.append({
                "type": stype,
                "original_value": value[:255],
                "bbox": None if suppress_box else {
                    "bbox": [
                        [round(x0, 2), round(y0, 2)],
                        [round(x1, 2), round(y0, 2)],
                        [round(x1, 2), round(y1, 2)],
                        [round(x0, 2), round(y1, 2)],
                    ]
                },
                "confidence": round(conf, 3),
                "method": GEOMETRY_METHOD,
                "needs_review": bool(needs_review),
            })
        return redactions
