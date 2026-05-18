"""
End-to-end test: OCR + NER on SROIE2019
========================================
Runs the full pipeline on a sample of receipts:
  image  ->  PaddleOCR  ->  Ollama LLM  ->  structured Receipt

Then compares the extracted fields to the ground-truth entities/*.txt
provided by SROIE2019 (company, date, total).

Usage:
  python -m ner.test_sroie --n 5
  python -m ner.test_sroie --n 10 --model llama3.1:8b
"""

import argparse
import json
from pathlib import Path

from ner.extractor import OllamaExtractor
from ner.models import Receipt
from ocr.paddle_ocr import ReceiptOCR

DATASET_ROOT = Path(__file__).resolve().parent.parent / "SROIE2019"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "ner_results"


def load_ground_truth(entities_file: Path) -> dict:
    if not entities_file.exists():
        return {}
    with open(entities_file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def compare(predicted: Receipt, gt: dict) -> dict:
    """Compare predicted Receipt vs SROIE ground truth (company, date, total)."""
    gt_company = (gt.get("company") or "").strip().upper()
    gt_total = _to_float(gt.get("total"))
    gt_date = (gt.get("date") or "").strip()

    pred_company = predicted.enseigne.strip().upper()
    pred_total = predicted.total

    return {
        "company_match": bool(gt_company) and (gt_company in pred_company or pred_company in gt_company),
        "total_match": abs(pred_total - gt_total) < 0.01 if gt_total else False,
        "date_present": bool(predicted.date),
        "items_extracted": len(predicted.items),
        "gt_company": gt.get("company", ""),
        "pred_company": predicted.enseigne,
        "gt_total": gt_total,
        "pred_total": pred_total,
        "gt_date": gt_date,
        "pred_date": predicted.date,
    }


def _to_float(v) -> float:
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return 0.0


def main():
    parser = argparse.ArgumentParser(description="OCR + NER pipeline test on SROIE2019")
    parser.add_argument("--n", type=int, default=5, help="Number of images")
    parser.add_argument("--split", type=str, default="train", choices=["train", "test"])
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Ollama model name")
    parser.add_argument("--lang", type=str, default="en", help="OCR language")
    args = parser.parse_args()

    img_dir = DATASET_ROOT / args.split / "img"
    ent_dir = DATASET_ROOT / args.split / "entities"

    if not img_dir.exists():
        print(f"Dataset not found at: {img_dir}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(img_dir.glob("*.jpg"))[: args.n]
    print(f"Running OCR + NER on {len(images)} images using {args.model} ...")

    ocr = ReceiptOCR(lang=args.lang)
    extractor = OllamaExtractor(model=args.model)

    scores = {"company": 0, "total": 0, "date": 0}
    for i, img_path in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}] {img_path.name}")
        ocr_result = ocr.extract(str(img_path))
        receipt = extractor.extract(ocr_result.text)

        gt = load_ground_truth(ent_dir / f"{img_path.stem}.txt")
        cmp = compare(receipt, gt)

        print(f"  enseigne : {cmp['pred_company']!r}  (GT: {cmp['gt_company']!r})  -> {'OK' if cmp['company_match'] else 'NO'}")
        print(f"  total    : {cmp['pred_total']}  (GT: {cmp['gt_total']})  -> {'OK' if cmp['total_match'] else 'NO'}")
        print(f"  date     : {cmp['pred_date']!r}  (GT: {cmp['gt_date']!r})  -> {'present' if cmp['date_present'] else 'missing'}")
        print(f"  items    : {cmp['items_extracted']}")

        scores["company"] += int(cmp["company_match"])
        scores["total"] += int(cmp["total_match"])
        scores["date"] += int(cmp["date_present"])

        out = OUTPUT_DIR / f"{img_path.stem}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "image": img_path.name,
                    "ocr_text": ocr_result.text,
                    "receipt": receipt.to_dict(),
                    "ground_truth": gt,
                    "comparison": cmp,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    n = len(images)
    if n:
        print("\n" + "=" * 60)
        print(f"Processed {n} images")
        print(f"  enseigne match : {scores['company']}/{n} ({scores['company']/n:.0%})")
        print(f"  total match    : {scores['total']}/{n} ({scores['total']/n:.0%})")
        print(f"  date present   : {scores['date']}/{n} ({scores['date']/n:.0%})")
        print(f"Results saved to : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
