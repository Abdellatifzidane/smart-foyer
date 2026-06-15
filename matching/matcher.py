"""
Matcher haut-niveau (comparaison ticket ↔ catalogue)
====================================================
Pour chaque produit d'un ticket scanné, trouve le meilleur produit
correspondant dans le catalogue multi-enseignes, puis liste les alternatives
réellement moins chères à quantité comparable.

Stratégie de matching (pensée pour la robustesse cross-enseignes)
-----------------------------------------------------------------
1. **Recall dense** : top-40 voisins par cosinus sur embeddings E5 multilingues
   (le texte est normalisé : abréviations développées, accents retirés).
2. **Re-ranking hybride** : le cosinus E5 est peu discriminant (plage 0.7–0.95),
   on le rescale et on le combine à un score lexical robuste
   (RapidFuzz token_set/sort + Jaccard sur tokens de contenu).
        score = W_DENSE * dense_rescaled + W_LEX * lexical
3. **Gate quantité** : un produit dont la contenance connue diffère de plus de
   ~18 % de l'item scanné est écarté (jamais un 50 cl présenté comme un 1 L).
4. **Pénalité catégorie** : si les deux familles sont connues et différentes,
   on pénalise (évite "chocolat" ↔ "gel douche au chocolat").
5. **Seuil** : sous le seuil hybride OU sous un minimum lexical, on répond
   "aucune correspondance" plutôt qu'un faux positif.
6. **Alternatives moins chères** : comparaison au **prix par litre/kg** quand la
   quantité est connue des deux côtés (comparaison équitable), sinon au prix
   absolu à quantité compatible. Top 3, enseigne différente.

Usage :
  matcher = Matcher.from_disk("data/index/catalog")
  comparisons = matcher.compare(receipt)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field

from rapidfuzz import fuzz

from matching.embeddings import Embedder
from matching.index import ProductIndex, MatchResult
from matching.normalize import (
    normalize_text,
    embed_text,
    content_tokens,
    extract_quantity,
    quantity_compatible,
    price_per_base_unit,
    infer_category,
    Quantity,
)
from ner.models import Receipt, LineItem


# ─── Paramètres de scoring (calibrés via matching/test_matching_quality.py) ──
W_DENSE = 0.45          # poids du signal sémantique (dense)
W_LEX = 0.55            # poids du signal lexical (fuzzy + tokens)
DENSE_FLOOR = 0.70      # cosinus E5 en-dessous duquel on considère "rien"
DENSE_CEIL = 0.95       # cosinus E5 au-dessus duquel c'est "parfait"
CAT_PENALTY = 0.15      # malus si catégories connues et différentes
DEFAULT_MIN_SCORE = 0.60  # seuil hybride final (calibré : vrais matchs ≥0.74,
                          # faux positifs type "frais de livraison" ~0.52)
MIN_LEXICAL = 0.25      # garde-fou lexical : sous ce seuil, pas de match
RECALL_K = 40           # nb de candidats denses sur-récupérés
QTY_TOLERANCE = 0.18    # tolérance de contenance (18 %)


@dataclass
class ItemComparison:
    """Comparaison d'un item scanné contre le catalogue."""
    scanned_name: str
    scanned_price: float
    best_match_name: str = ""
    best_match_enseigne: str = ""
    best_match_price: float = 0.0
    best_match_score: float = 0.0
    best_match_unit_price: float = 0.0   # €/L ou €/kg (0 si inconnu)
    scanned_quantity: str = ""           # quantité détectée (libellé lisible)
    cheaper_alternatives: list[dict] = field(default_factory=list)
    savings: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class Matcher:
    """Compare les items d'un ticket au catalogue indexé."""

    def __init__(self, index: ProductIndex):
        self.index = index

    @classmethod
    def from_disk(cls, index_prefix: str, embedder: Embedder | None = None) -> "Matcher":
        embedder = embedder or Embedder()
        index = ProductIndex.load(index_prefix, embedder)
        return cls(index=index)

    # ─── Comparaison d'un item ─────────────────────────────────────
    def compare_item(
        self,
        item: LineItem,
        k: int = 5,
        min_score: float = DEFAULT_MIN_SCORE,
        scanned_enseigne: str = "",
    ) -> ItemComparison:
        q_norm = normalize_text(item.name)
        if not q_norm:
            return ItemComparison(
                scanned_name=item.name, scanned_price=item.price,
            )

        q_embed = embed_text(item.name)
        q_tokens = content_tokens(q_norm)
        q_qty = extract_quantity(item.name)
        q_cat = infer_category(item.name)

        raw_hits = self.index.search(q_embed, k=RECALL_K, min_score=0.0)

        scored: list[tuple[float, MatchResult, float, float, Quantity]] = []
        for h in raw_hits:
            price = _safe_price(h.product.get("price"))
            if price <= 0:
                continue  # jamais de match à 0,00 €

            c_qty = extract_quantity(_full_name(h.product))
            # Gate quantité : écarte les contenances incompatibles
            if not quantity_compatible(q_qty, c_qty, tol=QTY_TOLERANCE):
                continue

            c_norm = normalize_text(_full_name(h.product))
            lex = _lexical_score(q_norm, c_norm, q_tokens, content_tokens(c_norm))
            dense = _rescale_dense(float(h.score))

            hybrid = W_DENSE * dense + W_LEX * lex

            # Pénalité de famille
            c_cat = infer_category(_full_name(h.product))
            if q_cat and c_cat and q_cat != c_cat:
                hybrid -= CAT_PENALTY

            scored.append((hybrid, h, lex, dense, c_qty))

        if not scored:
            return ItemComparison(
                scanned_name=item.name, scanned_price=item.price,
                scanned_quantity=_qty_label(q_qty),
            )

        scored.sort(key=lambda c: c[0], reverse=True)
        best_hybrid, best_hit, best_lex, _, best_qty = scored[0]

        # Seuil : rejette les faux positifs
        if best_hybrid < min_score or best_lex < MIN_LEXICAL:
            return ItemComparison(
                scanned_name=item.name, scanned_price=item.price,
                scanned_quantity=_qty_label(q_qty),
            )

        best_price = _safe_price(best_hit.product.get("price"))
        best_enseigne = best_hit.product.get("enseigne", "")
        best_unit = price_per_base_unit(best_price, best_qty)

        # Alternatives MOINS CHÈRES QUE LE PRIX PAYÉ (item.price), dans une autre
        # enseigne que celle du ticket. On ne propose jamais un produit plus cher
        # que ce que l'utilisateur a réellement déboursé.
        cheaper = self._cheaper_than_paid(
            scored, item.price, q_qty, scanned_enseigne, min_score=min_score,
        )
        savings = round(item.price - cheaper[0]["price"], 2) if cheaper else 0.0

        return ItemComparison(
            scanned_name=item.name,
            scanned_price=item.price,
            best_match_name=best_hit.product.get("name", ""),
            best_match_enseigne=best_enseigne,
            best_match_price=best_price,
            best_match_score=round(best_hybrid, 4),
            best_match_unit_price=round(best_unit, 3) if best_unit else 0.0,
            scanned_quantity=_qty_label(q_qty),
            cheaper_alternatives=cheaper,
            savings=max(savings, 0.0),
        )

    def _cheaper_than_paid(
        self, scored, paid_price, paid_qty, scanned_enseigne, min_score: float,
    ) -> list[dict]:
        """Alternatives strictement MOINS CHÈRES QUE LE PRIX PAYÉ.

        Une alternative doit :
          - être LE MÊME produit (passer la barre de match),
          - venir d'une AUTRE enseigne que celle du ticket,
          - être réellement moins chère que ce que l'utilisateur a payé :
            comparaison au prix au litre/kg si les deux contenances sont connues
            (équitable), sinon au prix absolu à quantité comparable.

        Si aucun prix payé n'a été extrait du ticket, on ne peut rien affirmer
        -> aucune alternative (on ne devine pas une "économie").
        """
        if paid_price <= 0:
            return []

        paid_unit = price_per_base_unit(paid_price, paid_qty)
        scanned_ens = (scanned_enseigne or "").strip().lower()
        out: list[dict] = []
        seen_keys: set[tuple] = set()

        for hybrid, h, lex, _, c_qty in scored:
            if hybrid < min_score or lex < MIN_LEXICAL:
                continue  # pas le même produit
            price = _safe_price(h.product.get("price"))
            ens = h.product.get("enseigne", "")
            if price <= 0:
                continue
            if scanned_ens and ens.strip().lower() == scanned_ens:
                continue  # même enseigne que le ticket → pas une alternative

            c_unit = price_per_base_unit(price, c_qty)
            if paid_unit is not None and c_unit is not None:
                cheaper = c_unit < paid_unit          # €/L ou €/kg
            elif quantity_compatible(paid_qty, c_qty, tol=QTY_TOLERANCE):
                cheaper = price < paid_price           # prix absolu, qté comparable
            else:
                cheaper = False
            if not cheaper:
                continue

            key = (ens, h.product.get("name", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append({
                "name": h.product.get("name", ""),
                "enseigne": ens,
                "price": price,
                "unit_price": round(c_unit, 3) if c_unit else 0.0,
                "score": round(hybrid, 4),
                "savings": round(paid_price - price, 2),
            })
        out.sort(key=lambda c: c["price"])
        return out[:3]

    def compare(
        self,
        receipt: Receipt,
        k: int = 5,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> list[ItemComparison]:
        return [
            self.compare_item(
                it, k=k, min_score=min_score, scanned_enseigne=receipt.enseigne
            )
            for it in receipt.items
        ]


# ─── Helpers de scoring ──────────────────────────────────────────────

def _full_name(p: dict) -> str:
    """Nom + marque du produit catalogue (pour normalisation/quantité)."""
    name = p.get("name", "")
    brand = p.get("brand", "")
    if brand and brand.lower() not in name.lower():
        return f"{name} {brand}"
    return name


def _rescale_dense(cos: float) -> float:
    """Rescale le cosinus E5 (plage utile ~0.70–0.95) vers [0, 1]."""
    if cos <= DENSE_FLOOR:
        return 0.0
    if cos >= DENSE_CEIL:
        return 1.0
    return (cos - DENSE_FLOOR) / (DENSE_CEIL - DENSE_FLOOR)


def _lexical_score(
    q_norm: str, c_norm: str, q_tokens: set[str], c_tokens: set[str]
) -> float:
    """Score lexical robuste dans [0, 1].

    Combine RapidFuzz (token_set_ratio gère mots manquants/réordonnés) et un
    Jaccard sur tokens de contenu (récompense les mots discriminants partagés).
    """
    if not q_norm or not c_norm:
        return 0.0
    fuzzy = max(
        fuzz.token_set_ratio(q_norm, c_norm),
        fuzz.token_sort_ratio(q_norm, c_norm),
    ) / 100.0
    jacc = _jaccard(q_tokens, c_tokens)
    # Le Jaccard sur tokens discriminants est un signal fort de vraie identité.
    return 0.6 * fuzzy + 0.4 * jacc


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _qty_label(q: Quantity) -> str:
    if not q.is_known:
        return ""
    if q.base_unit == "ml":
        v = q.base_value
        return f"{v/1000:g} L" if v >= 1000 else f"{v:g} ml"
    if q.base_unit == "g":
        v = q.base_value
        return f"{v/1000:g} kg" if v >= 1000 else f"{v:g} g"
    return ""


def _safe_price(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
