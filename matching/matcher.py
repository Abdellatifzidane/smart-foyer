"""
High-level matcher
==================
Takes a parsed Receipt and returns, for each item, the cheapest matching
product across the scraped catalog (grouped by enseigne).

Usage:
  matcher = Matcher.from_disk("data/index/catalog")
  comparison = matcher.compare(receipt)
  print(comparison)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from matching.embeddings import Embedder
from matching.index import ProductIndex, MatchResult
from ner.models import Receipt, LineItem


@dataclass
class ItemComparison:
    """Comparison of one scanned item against catalog matches."""
    scanned_name: str
    scanned_price: float
    best_match_name: str = ""
    best_match_enseigne: str = ""
    best_match_price: float = 0.0
    best_match_score: float = 0.0
    cheaper_alternatives: list[dict] = None  # other enseignes that are cheaper
    savings: float = 0.0                     # vs best_match_price

    def to_dict(self) -> dict:
        return asdict(self)


class Matcher:
    """Compares scanned receipt items against the indexed catalog."""

    def __init__(self, index: ProductIndex):
        self.index = index

    @classmethod
    def from_disk(cls, index_prefix: str, embedder: Embedder | None = None) -> "Matcher":
        embedder = embedder or Embedder()
        index = ProductIndex.load(index_prefix, embedder)
        return cls(index=index)

    def compare_item(self, item: LineItem, k: int = 5, min_score: float = 0.7) -> ItemComparison:
        """Find the best catalog match for one item and list cheaper alternatives."""
        hits = self.index.search(item.name, k=k, min_score=min_score)

        if not hits:
            return ItemComparison(
                scanned_name=item.name,
                scanned_price=item.price,
                cheaper_alternatives=[],
            )

        # Best semantic match (highest similarity)
        best = hits[0]
        best_price = float(best.product.get("price", 0.0))

        # Cheaper alternatives = other hits whose enseigne differs and price is lower
        cheaper = []
        for h in hits[1:]:
            price = float(h.product.get("price", 0.0))
            if price > 0 and price < best_price:
                cheaper.append({
                    "name": h.product.get("name", ""),
                    "enseigne": h.product.get("enseigne", ""),
                    "price": price,
                    "score": h.score,
                    "savings": round(best_price - price, 2),
                })

        return ItemComparison(
            scanned_name=item.name,
            scanned_price=item.price,
            best_match_name=best.product.get("name", ""),
            best_match_enseigne=best.product.get("enseigne", ""),
            best_match_price=best_price,
            best_match_score=best.score,
            cheaper_alternatives=cheaper,
            savings=round(max((best_price - min((c["price"] for c in cheaper), default=best_price)), 0), 2),
        )

    def compare(self, receipt: Receipt, k: int = 5, min_score: float = 0.7) -> list[ItemComparison]:
        """Compare every line item of a receipt."""
        return [self.compare_item(item, k=k, min_score=min_score) for item in receipt.items]
