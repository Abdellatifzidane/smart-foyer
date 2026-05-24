"""
Seed demo receipts for the SmartFoyer history.
==============================================
Generates realistic French grocery receipts in data/receipts/ so the
history screen and the (upcoming) RAG agent have something to show on a
fresh install.

Each receipt is tagged with "demo": true so it can be purged later:

  python -m backend.seed_demo            # add demo receipts
  python -m backend.seed_demo --clear    # remove demo receipts only

Real (user-scanned) receipts are never touched.
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "data" / "receipts"

# Pool of realistic products grouped by category, with typical price ranges.
PRODUCTS = {
    "pates": [("Panzani Penne Rigate 500g", 1.20, 1.80),
              ("Barilla Spaghetti n°5", 1.50, 2.20),
              ("Lustucru Coquillettes 500g", 1.10, 1.60),
              ("Panzani Pulpe de Tomate Fine", 3.80, 4.40),
              ("Buitoni Tortellini Ricotta 250g", 2.50, 3.20)],
    "boulangerie": [("Pain de mie complet 500g", 1.40, 2.10),
                    ("Baguette tradition", 0.95, 1.20),
                    ("Brioche tranchée", 2.20, 3.10),
                    ("Pain aux céréales", 1.90, 2.80)],
    "produits_laitiers": [("Lait demi-écrémé 1L", 0.95, 1.30),
                          ("Beurre doux 250g", 2.10, 3.20),
                          ("Crème fraîche 30% 25cl", 1.40, 2.00),
                          ("Yaourts nature x4", 1.80, 2.60),
                          ("Emmental râpé 200g", 2.20, 3.00),
                          ("Camembert 250g", 2.30, 3.40)],
    "viandes_poisson": [("Escalope poulet 500g", 5.50, 7.50),
                        ("Steak haché 5% x4", 5.20, 7.00),
                        ("Saumon fumé 150g", 4.40, 6.20),
                        ("Jambon blanc x4 tr", 2.80, 4.10),
                        ("Filet de cabillaud 300g", 6.10, 8.00)],
    "fruits_legumes": [("Tomates grappe vrac", 0.90, 1.80),
                       ("Bananes vrac", 0.80, 1.40),
                       ("Pommes Gala 1kg", 1.50, 2.40),
                       ("Avocat à la pièce", 0.90, 1.40),
                       ("Oignon blanc vrac", 1.00, 1.60),
                       ("Salade laitue", 1.10, 1.70),
                       ("Courgettes 1kg", 1.80, 2.80),
                       ("Carottes 1kg", 1.20, 1.90)],
    "epicerie": [("Concentré de tomate 140g", 0.90, 1.40),
                 ("Huile d'olive 75cl", 5.20, 8.00),
                 ("Riz long 1kg", 2.10, 3.10),
                 ("Lentilles vertes 500g", 1.90, 2.70),
                 ("Café moulu Carte Noire 250g", 3.20, 4.50),
                 ("Sucre en poudre 1kg", 1.20, 1.80)],
    "boissons": [("Eau minérale 6x1.5L", 2.20, 3.20),
                 ("Jus d'orange 1L", 1.80, 2.80),
                 ("Coca-Cola 1.5L", 1.70, 2.30)],
    "hygiene": [("Dentifrice Signal 75ml", 1.80, 2.50),
                ("Gel douche 250ml", 2.10, 3.20),
                ("Shampoing Elseve 250ml", 2.80, 4.20),
                ("Papier toilette x6", 3.40, 5.20)],
    "menager": [("Liquide vaisselle 500ml", 1.90, 2.80),
                ("Lessive liquide 30 lavages", 6.50, 9.20),
                ("Sopalin x2", 2.10, 3.10)],
}

# Typical receipts per store - dict of (enseigne, baskets_template)
# Each basket is a list of (category, qty_min, qty_max) telling the recipe.
STORES = ["Intermarché", "Carrefour", "Monoprix", "Lidl", "Franprix"]


def random_basket() -> list[tuple[str, float, int]]:
    """Pick a realistic grocery basket (5-12 items)."""
    n = random.randint(5, 12)
    items: list[tuple[str, float, int]] = []
    # Make sure we sample without immediate duplicates
    categories = list(PRODUCTS.keys())
    while len(items) < n:
        cat = random.choice(categories)
        name, lo, hi = random.choice(PRODUCTS[cat])
        if any(name == it[0] for it in items):
            continue
        price = round(random.uniform(lo, hi), 2)
        qty = random.choices([1, 2, 3], weights=[7, 2, 1])[0]
        items.append((name, price, qty))
    return items


def build_receipt(store: str, when: datetime) -> dict:
    """Build a fake receipt payload matching the /scan response shape."""
    items = random_basket()
    receipt_items = [
        {"name": name, "price": round(price * qty, 2), "quantity": float(qty)}
        for (name, price, qty) in items
    ]
    total = round(sum(it["price"] for it in receipt_items), 2)

    receipt_id = uuid.uuid4().hex[:12]
    return {
        "id": receipt_id,
        "scanned_at": when.isoformat(),
        "demo": True,
        "ocr": {
            "text": "(seed demo - no OCR text)",
            "avg_confidence": 0.95,
            "line_count": len(receipt_items),
        },
        "receipt": {
            "enseigne": store,
            "date": when.strftime("%d/%m/%Y"),
            "total": total,
            "items": receipt_items,
        },
        "comparisons": [],
        "total_savings": round(random.uniform(0.5, 8.0), 2),
    }


def save(payload: dict) -> Path:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RECEIPTS_DIR / f"{payload['id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def clear_demo() -> int:
    """Remove every receipt tagged demo=True. Real scans are kept."""
    if not RECEIPTS_DIR.exists():
        return 0
    removed = 0
    for path in RECEIPTS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("demo") is True:
            path.unlink()
            removed += 1
    return removed


def seed(n_receipts: int, days_back: int):
    """Spread n receipts across the last `days_back` days."""
    now = datetime.now(timezone.utc)
    created = []
    for _ in range(n_receipts):
        store = random.choice(STORES)
        offset_days = random.uniform(0, days_back)
        offset_hours = random.uniform(8, 20)
        when = now - timedelta(days=offset_days)
        when = when.replace(hour=int(offset_hours), minute=random.randint(0, 59), second=0, microsecond=0)
        payload = build_receipt(store, when)
        path = save(payload)
        created.append((store, payload["receipt"]["total"], path))

    created.sort(key=lambda x: x[2].stat().st_mtime, reverse=True)
    print(f"Created {len(created)} demo receipts in {RECEIPTS_DIR}")
    by_store: dict[str, int] = {}
    for store, _, _ in created:
        by_store[store] = by_store.get(store, 0) + 1
    print("Repartition :")
    for store, count in sorted(by_store.items()):
        print(f"  {store:<14} {count} tickets")


def main():
    parser = argparse.ArgumentParser(description="Seed/clear demo receipts")
    parser.add_argument("--n", type=int, default=15, help="Number of demo receipts to create")
    parser.add_argument("--days", type=int, default=90, help="Spread over the last N days")
    parser.add_argument("--clear", action="store_true", help="Remove demo receipts only")
    args = parser.parse_args()

    if args.clear:
        n = clear_demo()
        print(f"Removed {n} demo receipts. Real scans were kept.")
        return

    random.seed()  # truly random
    seed(args.n, args.days)


if __name__ == "__main__":
    main()
