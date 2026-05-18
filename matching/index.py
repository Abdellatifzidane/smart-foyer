"""
FAISS product index
===================
Stores scraped product vectors and provides nearest-neighbor search.

Two files are persisted on disk:
  - {prefix}.faiss  : the FAISS index (vectors)
  - {prefix}.jsonl  : the product metadata (one product per line)

Usage:
  index = ProductIndex.build(products, embedder)
  index.save("data/index/catalog")

  index = ProductIndex.load("data/index/catalog", embedder)
  results = index.search("LAIT 1/2 ECR 1L", k=5)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from matching.embeddings import Embedder


@dataclass
class MatchResult:
    """A single search hit."""
    score: float          # cosine similarity in [0, 1]
    product: dict         # original product metadata (name, price, enseigne, ...)

    def to_dict(self) -> dict:
        return {"score": self.score, "product": self.product}


class ProductIndex:
    """A FAISS index over scraped product names + their metadata."""

    def __init__(self, index: faiss.Index, products: list[dict], embedder: Embedder):
        self.index = index
        self.products = products
        self.embedder = embedder

    # ─── Construction ──────────────────────────────────────────────

    @classmethod
    def build(cls, products: list[dict], embedder: Embedder) -> "ProductIndex":
        """Build an index from a list of product dicts (must have a 'name' key)."""
        if not products:
            raise ValueError("Cannot build index from empty product list")

        names = [_product_text(p) for p in products]
        print(f"Encoding {len(names)} products...")
        vectors = embedder.encode(names)

        # Inner product with normalized vectors == cosine similarity
        index = faiss.IndexFlatIP(embedder.dim)
        index.add(vectors)
        print(f"Index built: {index.ntotal} vectors, dim={embedder.dim}")

        return cls(index=index, products=products, embedder=embedder)

    # ─── Persistence ───────────────────────────────────────────────

    def save(self, prefix: str) -> None:
        """Save index + metadata under {prefix}.faiss and {prefix}.jsonl."""
        prefix_path = Path(prefix)
        prefix_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(prefix_path) + ".faiss")
        with open(str(prefix_path) + ".jsonl", "w", encoding="utf-8") as f:
            for p in self.products:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

        print(f"Saved index to {prefix}.faiss / {prefix}.jsonl")

    @classmethod
    def load(cls, prefix: str, embedder: Embedder) -> "ProductIndex":
        """Load a previously saved index."""
        index = faiss.read_index(str(prefix) + ".faiss")
        products = []
        with open(str(prefix) + ".jsonl", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    products.append(json.loads(line))
        return cls(index=index, products=products, embedder=embedder)

    # ─── Search ────────────────────────────────────────────────────

    def search(self, query: str, k: int = 5, min_score: float = 0.0) -> list[MatchResult]:
        """Return the top-k catalog products most similar to `query`."""
        if not query.strip():
            return []

        vector = self.embedder.encode_one(query)
        scores, indices = self.index.search(vector, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            score = float(score)
            if score < min_score:
                continue
            results.append(MatchResult(score=score, product=self.products[idx]))
        return results


def _product_text(product: dict) -> str:
    """Build the embedding input from a product dict.

    We combine name + brand to give the model more context.
    """
    parts = [product.get("name", "")]
    brand = product.get("brand", "")
    if brand and brand.lower() not in (parts[0] or "").lower():
        parts.append(brand)
    return " ".join(p for p in parts if p).strip()
