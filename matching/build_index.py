"""
Build the FAISS catalog index from scraped product JSON files.

Usage:
  python -m matching.build_index
  python -m matching.build_index --input data --output data/index/catalog
"""

import argparse
import json
from pathlib import Path

from matching.embeddings import Embedder
from matching.index import ProductIndex


DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "data"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "index" / "catalog"


def load_products(input_dir: Path) -> list[dict]:
    """Load all *.json product files produced by the scrapers."""
    products = []
    seen = set()

    patterns = ["*_products.json", "all_products_*.json"]
    files = []
    for pat in patterns:
        files.extend(input_dir.glob(pat))

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, list):
            continue
        for p in data:
            key = (p.get("enseigne", ""), p.get("sku", "") or p.get("product_url", "") or p.get("name", ""))
            if key in seen:
                continue
            if not p.get("name"):
                continue
            # Skip products with no usable price (rupture de stock, mauvais scrape...)
            try:
                price = float(p.get("price", 0))
            except (TypeError, ValueError):
                price = 0.0
            if price <= 0:
                continue
            seen.add(key)
            products.append(p)

    return products


def main():
    parser = argparse.ArgumentParser(description="Build FAISS product index")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="Directory containing scraped *_products.json files")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output prefix for index files (.faiss + .jsonl)")
    args = parser.parse_args()

    products = load_products(args.input)
    if not products:
        print(f"No products found in {args.input}. Run the scrapers first.")
        print("  python scrapers/run_all.py --max-products 200")
        return

    print(f"Loaded {len(products)} unique products")
    by_enseigne = {}
    for p in products:
        by_enseigne[p.get("enseigne", "?")] = by_enseigne.get(p.get("enseigne", "?"), 0) + 1
    for ens, count in sorted(by_enseigne.items()):
        print(f"  {ens}: {count}")

    embedder = Embedder()
    index = ProductIndex.build(products, embedder)
    index.save(str(args.output))


if __name__ == "__main__":
    main()
