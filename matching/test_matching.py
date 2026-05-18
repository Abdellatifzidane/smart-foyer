"""
Test the FAISS catalog index with sample queries.

Usage:
  python -m matching.test_matching
  python -m matching.test_matching --query "LAIT 1/2 ECR 1L"
  python -m matching.test_matching --query "cafe arabica" --k 5
"""

import argparse
from pathlib import Path

from matching.embeddings import Embedder
from matching.index import ProductIndex


DEFAULT_INDEX = Path(__file__).resolve().parent.parent / "data" / "index" / "catalog"

SAMPLE_QUERIES = [
    "LAIT 1/2 ECR 1L",
    "CAFE GRAINS 250G",
    "PATES SPAGHETTI 500G",
    "YAOURT NATURE",
    "JUS ORANGE 1L",
]


def run_query(index: ProductIndex, query: str, k: int):
    print(f"\nQuery: {query!r}")
    print("-" * 60)
    hits = index.search(query, k=k)
    if not hits:
        print("  No match.")
        return
    for i, hit in enumerate(hits, 1):
        p = hit.product
        print(f"  [{i}] score={hit.score:.3f}  {p.get('enseigne', '?'):<10} "
              f"{p.get('price', 0):>6.2f} EUR  {p.get('name', '')[:60]}")


def main():
    parser = argparse.ArgumentParser(description="Test the FAISS catalog")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX,
                        help="Index prefix (without extension)")
    parser.add_argument("--query", type=str, default="",
                        help="Single query (default: run a set of samples)")
    parser.add_argument("--k", type=int, default=5, help="Top-K results")
    args = parser.parse_args()

    if not (args.index.parent / (args.index.name + ".faiss")).exists():
        print(f"Index not found at {args.index}.faiss")
        print("Build it first: python -m matching.build_index")
        return

    embedder = Embedder()
    index = ProductIndex.load(str(args.index), embedder)
    print(f"Loaded index with {index.index.ntotal} products")

    queries = [args.query] if args.query else SAMPLE_QUERIES
    for q in queries:
        run_query(index, q, args.k)


if __name__ == "__main__":
    main()
