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

from dataclasses import dataclass, field, asdict
from pathlib import Path

from paddleocr import PaddleOCR


@dataclass
class OCRLine:
    text: str
    confidence: float
    box: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OCRResult:
    image_path: str
    lines: list[OCRLine] = field(default_factory=list)

    @property
    def text(self) -> str:
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
        )

    def extract(self, image_path: str) -> OCRResult:
        """Run OCR on a single image and return structured result."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        raw = self.engine.predict(str(path))
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
                box = boxes[i].tolist() if i < len(boxes) and hasattr(boxes[i], "tolist") else (
                    boxes[i] if i < len(boxes) else []
                )
                result.lines.append(OCRLine(text=text, confidence=conf, box=box))

        return result
