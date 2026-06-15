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

  # Incremental mutations (admin)
  pid = index.add_product({"name": "PAIN COMPLET", "price": 2.40, "enseigne": "Lidl"})
  index.update_product(pid, {"price": 2.20})
  index.remove_product(pid)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from matching.embeddings import Embedder
from matching.normalize import embed_text as _embed_text


@dataclass
class MatchResult:
    """A single search hit."""
    score: float          # cosine similarity in [0, 1]
    product: dict         # original product metadata (name, price, enseigne, ...)

    def to_dict(self) -> dict:
        return {"score": self.score, "product": self.product}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class ProductIndex:
    """A FAISS index over scraped product names + their metadata.

    Supports incremental add/update/remove. Removed products use a
    "mask-and-skip" strategy: the FAISS row is left in place but the
    id is dropped from `id_to_row`, and `search()` filters out any hit
    whose row is no longer mapped.
    """

    def __init__(
        self,
        index: faiss.Index,
        products: list[dict],
        embedder: Embedder,
        prefix: str | None = None,
    ):
        self.index = index
        self.products = products
        self.embedder = embedder
        self.prefix = prefix
        # id -> row position in the FAISS index
        self.id_to_row: dict[str, int] = {}
        for row, p in enumerate(products):
            pid = p.get("id")
            if not pid:
                pid = _new_id()
                p["id"] = pid
            self.id_to_row[pid] = row

    # ─── Construction ──────────────────────────────────────────────

    @classmethod
    def build(cls, products: list[dict], embedder: Embedder, prefix: str | None = None) -> "ProductIndex":
        """Build an index from a list of product dicts (must have a 'name' key)."""
        if not products:
            raise ValueError("Cannot build index from empty product list. Use ProductIndex.empty() instead.")

        for p in products:
            if not p.get("id"):
                p["id"] = _new_id()

        names = [_product_text(p) for p in products]
        print(f"Encoding {len(names)} products...")
        vectors = embedder.encode(names, kind="passage")

        # Inner product with normalized vectors == cosine similarity
        index = faiss.IndexFlatIP(embedder.dim)
        index.add(vectors)
        print(f"Index built: {index.ntotal} vectors, dim={embedder.dim}")

        return cls(index=index, products=products, embedder=embedder, prefix=prefix)

    @classmethod
    def empty(cls, embedder: Embedder, prefix: str | None = None) -> "ProductIndex":
        """Create an empty index ready to receive products via add_product()."""
        index = faiss.IndexFlatIP(embedder.dim)
        return cls(index=index, products=[], embedder=embedder, prefix=prefix)

    # ─── Persistence ───────────────────────────────────────────────

    def save(self, prefix: str | None = None) -> None:
        """Save index + metadata under {prefix}.faiss and {prefix}.jsonl."""
        prefix = prefix or self.prefix
        if not prefix:
            raise ValueError("No prefix set; pass one or build/load with prefix.")
        self.prefix = prefix

        prefix_path = Path(prefix)
        prefix_path.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(prefix_path) + ".faiss")
        with open(str(prefix_path) + ".jsonl", "w", encoding="utf-8") as f:
            for p in self.products:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

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
        return cls(index=index, products=products, embedder=embedder, prefix=str(prefix))

    # ─── Mutations ─────────────────────────────────────────────────

    def add_product(self, product: dict) -> str:
        """Add a product to the index. Returns its assigned id.

        The in-memory FAISS index, the products list, and the on-disk
        files are all updated atomically.
        """
        if not product.get("name"):
            raise ValueError("Product must have a 'name' field")

        pid = product.get("id") or _new_id()
        product["id"] = pid

        # ProductIndex is the live source of truth; appended row = current ntotal
        row = self.index.ntotal
        vec = self.embedder.encode_one(_product_text(product), kind="passage")
        self.index.add(vec)
        self.products.append(product)
        self.id_to_row[pid] = row

        if self.prefix:
            self.save()
        return pid

    def update_product(self, pid: str, patch: dict) -> dict:
        """Update an existing product. Returns the updated dict.

        If `name` or `brand` changes, the embedding is rebuilt by
        appending a new FAISS row and tombstoning the old one (FAISS
        IndexFlat doesn't support in-place vector replacement).
        """
        if pid not in self.id_to_row:
            raise KeyError(f"Unknown product id: {pid}")

        # Find the product in the list (linear; fine for POC sizes)
        idx = None
        for i, p in enumerate(self.products):
            if p.get("id") == pid:
                idx = i
                break
        if idx is None:
            raise KeyError(f"Product id {pid} in id_to_row but missing in products list")

        product = self.products[idx]
        old_text = _product_text(product)

        # Apply patch (whitelist common writable fields; never overwrite id)
        for k, v in patch.items():
            if k == "id":
                continue
            product[k] = v

        new_text = _product_text(product)
        if new_text != old_text:
            # Embedding changed → append a new FAISS row, drop the old mapping
            new_row = self.index.ntotal
            vec = self.embedder.encode_one(new_text, kind="passage")
            self.index.add(vec)
            self.id_to_row[pid] = new_row

        if self.prefix:
            self.save()
        return product

    def remove_product(self, pid: str) -> None:
        """Remove a product. The FAISS row is tombstoned (mask-and-skip)."""
        if pid not in self.id_to_row:
            raise KeyError(f"Unknown product id: {pid}")

        del self.id_to_row[pid]
        self.products = [p for p in self.products if p.get("id") != pid]

        if self.prefix:
            self.save()

    # ─── Search ────────────────────────────────────────────────────

    def search(self, query: str, k: int = 5, min_score: float = 0.0) -> list[MatchResult]:
        """Return the top-k catalog products most similar to `query`.

        Tombstoned rows (mapped to no current id) are filtered out.
        """
        if not query.strip() or self.index.ntotal == 0:
            return []

        vector = self.embedder.encode_one(query, kind="query")
        # Over-fetch a bit so tombstoned hits don't shrink the result set
        scores, indices = self.index.search(vector, max(k * 2, k + 5))

        # Reverse map: row -> product (only live rows)
        row_to_product = {row: None for row in self.id_to_row.values()}
        for p in self.products:
            row = self.id_to_row.get(p.get("id", ""))
            if row is not None:
                row_to_product[row] = p

        results: list[MatchResult] = []
        for score, row in zip(scores[0], indices[0]):
            if row == -1:
                continue
            product = row_to_product.get(int(row))
            if product is None:
                continue  # tombstoned
            score = float(score)
            if score < min_score:
                continue
            results.append(MatchResult(score=score, product=product))
            if len(results) >= k:
                break
        return results


def _product_text(product: dict) -> str:
    """Build the embedding input from a product dict (normalized name + brand).

    Normalisation = développement des abréviations + retrait des accents, pour
    aligner la forme catalogue sur la forme ticket.
    """
    return _embed_text(product.get("name", ""), product.get("brand", ""))
