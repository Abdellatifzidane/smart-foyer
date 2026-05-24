"""
Test PaddleOCR on the SROIE2019 dataset
========================================
Runs OCR on a sample of receipts and compares the result
to the ground truth boxes (box/*.txt) to estimate accuracy.

Usage:
  python -m ocr.test_sroie --n 5
  python -m ocr.test_sroie --n 20 --split test
"""

import argparse
import json
import os
from pathlib import Path

from ocr.paddle_ocr import ReceiptOCR

DATASET_ROOT = Path(__file__).resolve().parent.parent / "SROIE2019"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "ocr_results"


def load_ground_truth_text(box_file: Path) -> set[str]:
    """Parse SROIE box file and return the set of ground-truth text lines."""
    lines = set()
    if not box_file.exists():
        return lines
    with open(box_file, "r", encoding="utf-8") as f:
        for row in f:
            row = row.strip()
            if not row:
                continue
            # Format: x1,y1,x2,y2,x3,y3,x4,y4,text
            parts = row.split(",", 8)
            if len(parts) == 9:
                lines.add(parts[8].strip().upper())
    return lines


def score(predicted_text: str, gt_lines: set[str]) -> dict:
    """Naive scoring: how many ground-truth lines appear in the predicted text."""
    if not gt_lines:
        return {"matched": 0, "total": 0, "recall": 0.0}
    predicted_upper = predicted_text.upper()
    matched = sum(1 for line in gt_lines if line and line in predicted_upper)
    return {
        "matched": matched,
        "total": len(gt_lines),
        "recall": matched / len(gt_lines),
    }


def main():
    parser = argparse.ArgumentParser(description="Test PaddleOCR on SROIE2019")
    parser.add_argument("--n", type=int, default=5, help="Number of images to process")
    parser.add_argument("--split", type=str, default="train", choices=["train", "test"])
    parser.add_argument("--lang", type=str, default="en")
    args = parser.parse_args()

    img_dir = DATASET_ROOT / args.split / "img"
    box_dir = DATASET_ROOT / args.split / "box"

    if not img_dir.exists():
        print(f"Dataset not found at: {img_dir}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    images = sorted(img_dir.glob("*.jpg"))[: args.n]
    print(f"Running OCR on {len(images)} images from {args.split}/img ...")

    ocr = ReceiptOCR(lang=args.lang)

    summary = []
    for i, img_path in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}] {img_path.name}")
        result = ocr.extract(str(img_path))

        gt_file = box_dir / f"{img_path.stem}.txt"
        gt_lines = load_ground_truth_text(gt_file)
        metrics = score(result.text, gt_lines)

        print(f"  lines extracted   : {len(result.lines)}")
        print(f"  avg confidence    : {result.avg_confidence:.3f}")
        print(f"  ground-truth lines: {metrics['total']}")
        print(f"  matched           : {metrics['matched']} ({metrics['recall']:.1%})")

        out_file = OUTPUT_DIR / f"{img_path.stem}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(
                {**result.to_dict(), "metrics": metrics},
                f,
                ensure_ascii=False,
                indent=2,
            )

        summary.append(
            {
                "image": img_path.name,
                "lines": len(result.lines),
                "avg_confidence": result.avg_confidence,
                **metrics,
            }
        )

    if summary:
        avg_recall = sum(s["recall"] for s in summary) / len(summary)
        avg_conf = sum(s["avg_confidence"] for s in summary) / len(summary)
        print("\n" + "=" * 60)
        print(f"Processed {len(summary)} images")
        print(f"Average recall    : {avg_recall:.1%}")
        print(f"Average confidence: {avg_conf:.3f}")
        print(f"Results saved to  : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
