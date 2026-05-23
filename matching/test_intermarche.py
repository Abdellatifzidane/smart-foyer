"""
Test the FAISS catalog with the products from a real Intermarche receipt.
========================================================================
Helps visualize exactly which receipt items have a meaningful match in the
current catalog, without having to re-scan the photo each time.

Usage:
  python -m matching.test_intermarche
  python -m matching.test_intermarche --top 5 --min-score 0.5
"""

import argparse
from pathlib import Path

from matching.embeddings import Embedder
from matching.index import ProductIndex


DEFAULT_INDEX = Path(__file__).resolve().parent.parent / "data" / "index" / "catalog"


# Products from the Intermarche receipt (Asnieres sur Seine, total 22.03 EUR).
# We provide two forms for each line:
#   - the raw OCR-style label as it appears on the receipt
#   - a cleaner, more natural rewrite to help the embedding model
RECEIPT_ITEMS = [
    {"raw": "CHAB GRAND MIE CEREA",   "clean": "Pain de mie cereales Chabrior",         "price": 1.46},
    {"raw": "PANZANI PULPLE FINE",    "clean": "Panzani Pulpe de tomate fine",          "price": 4.22},
    {"raw": "PANZANI PENNE RIGATE",   "clean": "Panzani Penne Rigate pates",            "price": 1.24},
    {"raw": "PANZANI SPAGHETI C.R",   "clean": "Panzani Spaghetti pates",               "price": 1.49},
    {"raw": "FIOR DBL CONC TOMAT",    "clean": "Concentre de tomate double",            "price": 1.01},
    {"raw": "VOLAE 4 OEUFS BIO G/",   "clean": "Oeufs bio gros calibre x4",             "price": 2.35},
    {"raw": "SANYTOL GEL MAINS PS",   "clean": "Sanytol gel hydroalcoolique mains",     "price": 3.12},
    {"raw": "SIGN.DENT CHARBON DE",   "clean": "Dentifrice charbon Signal",             "price": 2.07},
    {"raw": "TOP BUDGET PT 6=12 R",   "clean": "Top Budget papier toilette",            "price": 1.38},
    {"raw": "OIGNON BLANC VRAC",      "clean": "Oignon blanc en vrac",                  "price": 1.22},
    {"raw": "TOMATE GRAPPE VRAC",     "clean": "Tomate grappe en vrac",                 "price": 1.32},
    {"raw": "AVOCAT AFFINE PIECE",    "clean": "Avocat affine a la piece",              "price": 1.16},
]


def search_and_print(index: ProductIndex, label: str, query: str, top: int) -> None:
    print(f"\n{label}")
    print(f"  -> query: {query!r}")
    hits = index.search(query, k=top)
    if not hits:
        print("     (no hit)")
        return
    for i, hit in enumerate(hits, 1):
        p = hit.product
        marker = "  OK" if hit.score >= 0.7 else "  ~ " if hit.score >= 0.55 else "  -- "
        print(f"{marker}[{i}] score={hit.score:.3f}  {p.get('enseigne','?'):<10} "
              f"{p.get('price', 0):>6.2f} EUR  {p.get('name','')[:60]}")


def main():
    parser = argparse.ArgumentParser(description="Test matching on a real Intermarche receipt")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--top", type=int, default=3, help="Top-K results per query")
    args = parser.parse_args()

    if not (args.index.parent / (args.index.name + ".faiss")).exists():
        print(f"Index not found at {args.index}.faiss")
        print("Build it first: python -m matching.build_index --input scrapers/data")
        return

    embedder = Embedder()
    index = ProductIndex.load(str(args.index), embedder)
    print(f"Catalog loaded: {index.index.ntotal} products")
    print("Legend: OK = good match (>=0.70)  ~ = weak match (0.55-0.70)  -- = poor match (<0.55)")

    good = 0
    weak = 0
    total = len(RECEIPT_ITEMS)
    for item in RECEIPT_ITEMS:
        label = f"--- {item['raw']:<24}  receipt price: {item['price']:.2f} EUR"
        # We try the cleaner version (gives better semantic results),
        # which is the kind of normalization we will eventually do in the LLM step.
        search_and_print(index, label, item["clean"], top=args.top)

        # Score the best hit
        best = index.search(item["clean"], k=1)
        if best:
            if best[0].score >= 0.7:
                good += 1
            elif best[0].score >= 0.55:
                weak += 1

    print("\n" + "=" * 60)
    print(f"Receipt items   : {total}")
    print(f"Good matches    : {good}/{total} ({good/total:.0%})")
    print(f"Weak matches    : {weak}/{total} ({weak/total:.0%})")
    print(f"No useful match : {total - good - weak}/{total}")


if __name__ == "__main__":
    main()
