"""
Receipt data models
===================
Defines the structured representation of a parsed receipt.

To add a new field:
  1. Add it to LineItem or Receipt below (with a sensible default).
  2. Add a corresponding line in ner/prompt.py describing it to the LLM.

That's it - the rest of the pipeline picks it up automatically.
"""

from dataclasses import dataclass, field, asdict
import json


@dataclass
class LineItem:
    """A single product line on the receipt."""
    name: str                # nom du produit
    price: float             # prix du produit (unitaire ou total ligne)
    quantity: float = 1.0    # quantite achetee

    # ─── Ajouter ici les champs optionnels (un par ligne) ───
    # category: str = ""
    # unit_price: float = 0.0
    # weight: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Receipt:
    """A parsed receipt."""
    enseigne: str = ""              # nom de l'enseigne (Monoprix, Carrefour, ...)
    total: float = 0.0              # prix total du ticket
    items: list[LineItem] = field(default_factory=list)  # produits achetes

    # ─── Ajouter ici les champs optionnels (un par ligne) ───
    date: str = ""                  # date du ticket (format YYYY-MM-DD si possible)
    # address: str = ""
    # payment_method: str = ""
    # currency: str = "EUR"

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "items"},
            "items": [i.to_dict() for i in self.items],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "Receipt":
        """Build a Receipt from an LLM JSON output (tolerant to missing fields)."""
        items = [
            LineItem(
                name=str(it.get("name", "")).strip(),
                price=_to_float(it.get("price")),
                quantity=_to_float(it.get("quantity", 1)) or 1.0,
            )
            for it in (data.get("items") or [])
            if it.get("name")
        ]
        return cls(
            enseigne=str(data.get("enseigne", "")).strip(),
            total=_to_float(data.get("total")),
            items=items,
            date=str(data.get("date", "")).strip(),
        )


def _to_float(value) -> float:
    """Coerce LLM output to float, tolerating strings like '1,29 EUR'."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", ".").replace("EUR", "").replace("€", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
