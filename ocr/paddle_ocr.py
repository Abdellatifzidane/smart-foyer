"""
PaddleOCR wrapper for SmartFoyer
================================
Extracts text from receipt images using PaddleOCR.

Usage:
  from ocr.paddle_ocr import ReceiptOCR
  ocr = ReceiptOCR(lang="en")
  result = ocr.extract("path/to/ticket.jpg")
  print(result["text"])
"""

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Disable oneDNN/MKL-DNN: incompatible with PaddlePaddle 3.x PIR backend
# (ConvertPirAttribute2RuntimeAttribute crash on ArrayAttribute<DoubleAttribute>).
# Must be set BEFORE importing paddleocr.
os.environ.setdefault("FLAGS_use_mkldnn", "0")

from paddleocr import PaddleOCR


@dataclass
class OCRLine:
    text: str
    confidence: float
    box: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def y_center(self) -> float:
        if not self.box:
            return 0.0
        ys = [pt[1] for pt in self.box]
        return sum(ys) / len(ys)

    @property
    def x_left(self) -> float:
        if not self.box:
            return 0.0
        xs = [pt[0] for pt in self.box]
        return min(xs)

    @property
    def height(self) -> float:
        if not self.box:
            return 0.0
        ys = [pt[1] for pt in self.box]
        return max(ys) - min(ys)


@dataclass
class OCRResult:
    image_path: str
    lines: list[OCRLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Layout-aware text: lines on the same horizontal band are merged
        left-to-right so receipt columns (product name | price) stay together.
        """
        return _layout_aware_text(self.lines)

    @property
    def raw_text(self) -> str:
        """Raw text in PaddleOCR detection order (useful for debugging)."""
        return "\n".join(line.text for line in self.lines)

    @property
    def avg_confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "text": self.text,
            "avg_confidence": self.avg_confidence,
            "lines": [line.to_dict() for line in self.lines],
        }


def _layout_aware_text(lines: list[OCRLine]) -> str:
    """Group OCR boxes by horizontal band (y-axis), then concat them left-to-right.

    Why: receipts are printed in two columns (product | price). PaddleOCR
    returns each text fragment as its own "line", so "Pain complet" and "0,35"
    arrive as two separate lines and the NER LLM can't match them. By
    clustering boxes whose y-centers are within ~half a text height, we
    rebuild a single readable line per row.
    """
    if not lines:
        return ""

    sorted_lines = sorted(
        [l for l in lines if l.box], key=lambda l: (l.y_center, l.x_left)
    )
    # Lines without box info → keep at the end in original order
    no_box = [l for l in lines if not l.box]

    if not sorted_lines:
        return "\n".join(l.text for l in no_box)

    # Estimate a typical text height to pick a clustering tolerance
    heights = [l.height for l in sorted_lines if l.height > 0]
    median_h = sorted(heights)[len(heights) // 2] if heights else 15.0
    tol = max(median_h * 0.6, 8.0)  # half a text-height, with a floor

    rows: list[list[OCRLine]] = []
    current: list[OCRLine] = []
    current_y: float | None = None

    for ln in sorted_lines:
        if current_y is None or abs(ln.y_center - current_y) <= tol:
            current.append(ln)
            # Running average y, weighted by lines so far
            current_y = (
                ln.y_center
                if current_y is None
                else (current_y * (len(current) - 1) + ln.y_center) / len(current)
            )
        else:
            rows.append(current)
            current = [ln]
            current_y = ln.y_center
    if current:
        rows.append(current)

    out: list[str] = []
    for row in rows:
        row_sorted = sorted(row, key=lambda l: l.x_left)
        # Use "   " (3 spaces) as a stand-in for the column gap so the LLM sees
        # the name and the price as part of the SAME line.
        out.append("   ".join(l.text for l in row_sorted))

    if no_box:
        out.extend(l.text for l in no_box)
    return "\n".join(out)


class ReceiptOCR:
    """Wrapper around PaddleOCR (3.x API) for receipt processing."""

    def __init__(self, lang: str = "en"):
        """
        Args:
            lang: 'en' for English (SROIE2019), 'fr' for French receipts.
        """
        self.lang = lang
        self.engine = PaddleOCR(
            lang=lang,
            use_textline_orientation=True,
            use_doc_orientation_classify=True,  # detect 90/180/270 rotated receipts
            use_doc_unwarping=True,             # straighten curved/wrinkled tickets
            enable_mkldnn=False,                # oneDNN crashes on Paddle 3.x PIR
        )

    def extract(
        self,
        image_path: str,
        preprocess: bool = True,
        min_confidence: float = 0.3,
    ) -> OCRResult:
        """Run OCR on a single image and return structured result.

        Args:
            preprocess: applique un prétraitement conservateur (EXIF, upscale
                des petites images, contraste + accentuation). Améliore les
                vraies photos de tickets sans dégrader les images nettes.
            min_confidence: on ignore les fragments sous ce seuil (bruit OCR)
                pour ne pas polluer l'étape NER.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        ocr_input = str(path)
        tmp_pre: str | None = None
        if preprocess:
            try:
                import tempfile
                from ocr.preprocess import preprocess_file
                fd, tmp_pre = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                ocr_input = preprocess_file(str(path), tmp_pre)
            except Exception:
                # En cas d'échec, on retombe sur l'image d'origine (jamais bloquant)
                ocr_input = str(path)

        try:
            raw = self.engine.predict(ocr_input)
        finally:
            if tmp_pre:
                try:
                    Path(tmp_pre).unlink(missing_ok=True)
                except OSError:
                    pass

        result = OCRResult(image_path=str(path))

        if not raw:
            return result

        # PaddleOCR 3.x returns a list of result objects; each exposes a
        # dict-like payload via .json or attribute access.
        for page in raw:
            data = page.json if hasattr(page, "json") else page
            if isinstance(data, dict) and "res" in data:
                data = data["res"]

            texts = data.get("rec_texts", []) or []
            scores = data.get("rec_scores", []) or []
            boxes = data.get("rec_polys") or data.get("dt_polys") or []

            for i, text in enumerate(texts):
                conf = float(scores[i]) if i < len(scores) else 0.0
                # Ignore les fragments trop incertains (bruit) et vides
                if conf < min_confidence or not (text or "").strip():
                    continue
                box = boxes[i].tolist() if i < len(boxes) and hasattr(boxes[i], "tolist") else (
                    boxes[i] if i < len(boxes) else []
                )
                result.lines.append(OCRLine(text=text, confidence=conf, box=box))

        return result
