"""
High-level matcher
==================
Takes a parsed Receipt and returns, for each item, the cheapest matching
product across the scraped catalog (grouped by enseigne).

Matching strategy
-----------------
1. Dense recall: cosine similarity over multilingual sentence embeddings
   (over-fetched: top-30).
2. Lexical re-rank: token-overlap (Jaccard) on normalized words to break ties
   and demote spurious semantic matches (e.g. "Chocolat NoL galette pain
   d'épice" vs "Beignet chocolat noisette": same theme, but few shared tokens).
3. Hybrid score: 0.6 * dense + 0.4 * lexical. Items with a price <= 0
   (rupture de stock, mauvais scrape) are filtered out so the user never
   sees a "0.00 €" match.
4. Cheaper-alternatives: among the top hits with a *different* enseigne and a
   strictly lower price than the best match, surface the best 3.

Usage:
  matcher = Matcher.from_disk("data/index/catalog")
  comparison = matcher.compare(receipt)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict

from matching.embeddings import Embedder
from matching.index import ProductIndex, MatchResult
from ner.models import Receipt, LineItem


# Minimum score (hybrid 0..1) below which we report "no match found".
# Calibrated so "Chocolat noel galette pain d'épice" vs "Beignet chocolat
# noisette" falls below the bar (few shared tokens beyond the generic
# "chocolat") while clear matches like "Désinfectant sensits" vs "Sanytol
# Désinfectant Linge" stay above.
DEFAULT_MIN_SCORE = 0.45

# Generic French food words that should NOT, on their own, justify a match.
# These are stripped from the lexical bag-of-words used for re-ranking.
_GENERIC_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "au", "aux", "un", "une",
    "et", "en", "a", "à", "l", "d", "s", "ou", "pour", "par", "sur",
    "kg", "kgs", "g", "gr", "ml", "cl", "l", "lt", "litre", "litres",
    "pack", "lot", "x", "qty", "qte", "quantite", "quantité",
    "bio", "ref", "tva", "eur", "euro", "euros",
}


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

    def compare_item(
        self,
        item: LineItem,
        k: int = 5,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> ItemComparison:
        """Find the best catalog match for one item and list cheaper alternatives."""
        query = _normalize_for_search(item.name)
        # Empty / unusable query — short-circuit
        if not query:
            return ItemComparison(
                scanned_name=item.name,
                scanned_price=item.price,
                cheaper_alternatives=[],
            )

        # Over-fetch dense candidates so the lexical re-ranker has something to
        # work with. We then filter zero-priced products before re-ranking.
        raw_hits = self.index.search(query, k=30, min_score=0.0)
        candidates: list[tuple[float, MatchResult, float, float]] = []
        # tuple = (hybrid_score, hit, dense_score, lexical_score)
        q_tokens = _tokenize(query)
        for h in raw_hits:
            price = _safe_price(h.product.get("price"))
            if price <= 0:
                continue  # never show "0,00 €" matches
            cat_text = _normalize_for_search(_product_label(h.product))
            lex = _lexical_score(q_tokens, _tokenize(cat_text))
            hybrid = 0.6 * float(h.score) + 0.4 * lex
            candidates.append((hybrid, h, float(h.score), lex))

        if not candidates:
            return ItemComparison(
                scanned_name=item.name,
                scanned_price=item.price,
                cheaper_alternatives=[],
            )

        candidates.sort(key=lambda c: c[0], reverse=True)
        top = candidates[: max(k, 5)]

        best_hybrid, best_hit, _, _ = top[0]
        if best_hybrid < min_score:
            return ItemComparison(
                scanned_name=item.name,
                scanned_price=item.price,
                cheaper_alternatives=[],
            )

        best_price = _safe_price(best_hit.product.get("price"))
        best_enseigne = best_hit.product.get("enseigne", "")

        # Cheaper = different enseigne AND strictly cheaper than the best match
        cheaper: list[dict] = []
        for hybrid, h, _, _ in top[1:]:
            price = _safe_price(h.product.get("price"))
            ens = h.product.get("enseigne", "")
            if price <= 0 or price >= best_price:
                continue
            if ens and ens == best_enseigne:
                continue
            cheaper.append({
                "name": h.product.get("name", ""),
                "enseigne": ens,
                "price": price,
                "score": round(hybrid, 4),
                "savings": round(best_price - price, 2),
            })
        cheaper.sort(key=lambda c: c["price"])
        cheaper = cheaper[:3]

        savings = round(best_price - cheaper[0]["price"], 2) if cheaper else 0.0
        return ItemComparison(
            scanned_name=item.name,
            scanned_price=item.price,
            best_match_name=best_hit.product.get("name", ""),
            best_match_enseigne=best_enseigne,
            best_match_price=best_price,
            best_match_score=round(best_hybrid, 4),
            cheaper_alternatives=cheaper,
            savings=max(savings, 0.0),
        )

    def compare(
        self,
        receipt: Receipt,
        k: int = 5,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> list[ItemComparison]:
        """Compare every line item of a receipt."""
        return [self.compare_item(item, k=k, min_score=min_score) for item in receipt.items]


# ─── Normalization helpers ────────────────────────────────────────────


def _product_label(p: dict) -> str:
    """Text used to compare a catalog product against a scanned line."""
    parts = [p.get("name", "")]
    brand = p.get("brand", "")
    if brand and brand.lower() not in (parts[0] or "").lower():
        parts.append(brand)
    return " ".join(part for part in parts if part)


def _normalize_for_search(name: str) -> str:
    """Strip accents, units, VAT tags and lowercase.

    Receipt names come out of OCR as uppercase with abbreviations and
    trailing TVA-category tags (' A', ' B'). Catalog names are mixed-case
    with brands and units. We normalize both sides to a comparable form.
    """
    if not name:
        return ""
    s = name.strip()
    # Drop trailing single-letter VAT tag ("Pain complet A" → "Pain complet")
    s = re.sub(r"\s+[A-Z]$", "", s)
    s = s.lower()
    # Remove accents (café → cafe, désinfectant → desinfectant)
    s = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    # Collapse units glued to numbers ("1l" → "1 l", "500g" → "500 g")
    s = re.sub(r"(\d)([a-z]{1,3})\b", r"\1 \2", s)
    # Drop standalone punctuation
    s = re.sub(r"[^a-z0-9\s%]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokenize(text: str) -> set[str]:
    """Bag-of-words minus generic stopwords/units, used for lexical overlap."""
    if not text:
        return set()
    toks = {t for t in text.split() if t and t not in _GENERIC_STOPWORDS}
    # Drop pure-digit tokens (weights, codes) — they hurt more than they help
    return {t for t in toks if not t.isdigit()}


def _lexical_score(a: set[str], b: set[str]) -> float:
    """Jaccard similarity on normalized tokens, in [0, 1]."""
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union)


def _safe_price(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
