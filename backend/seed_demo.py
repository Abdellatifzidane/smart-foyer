"""
Données de démo rattachées à un compte utilisateur
==================================================
Crée (si besoin) un compte de démonstration et lui rattache des tickets
réalistes, pour que l'historique, les analytics et l'agent IA aient du contenu
dès l'ouverture — le tout dans la nouvelle base SQLite, isolé par utilisateur.

  python -m backend.seed_demo                       # compte demo par défaut
  python -m backend.seed_demo --email moi@x.fr --n 20
  python -m backend.seed_demo --clear               # purge les tickets démo

Compte par défaut : demo@smartfoyer.fr / demo1234
Les vrais tickets (non taggés demo) ne sont jamais supprimés.
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from backend.auth import hash_password
from backend.db import Receipt, User, init_db, session_scope
from backend import receipts_store


DEFAULT_EMAIL = "demo@smartfoyer.fr"
DEFAULT_PASSWORD = "demo1234"

PRODUCTS = {
    "pates": [("Panzani Penne Rigate 500g", 1.20, 1.80),
              ("Barilla Spaghetti n°5", 1.50, 2.20),
              ("Lustucru Coquillettes 500g", 1.10, 1.60),
              ("Panzani Pulpe de Tomate Fine", 3.80, 4.40)],
    "boulangerie": [("Pain de mie complet 500g", 1.40, 2.10),
                    ("Baguette tradition", 0.95, 1.20),
                    ("Brioche tranchée", 2.20, 3.10)],
    "produits_laitiers": [("Lait demi-écrémé 1L", 0.95, 1.30),
                          ("Beurre doux 250g", 2.10, 3.20),
                          ("Yaourts nature x4", 1.80, 2.60),
                          ("Emmental râpé 200g", 2.20, 3.00)],
    "viandes_poisson": [("Escalope poulet 500g", 5.50, 7.50),
                        ("Steak haché 5% x4", 5.20, 7.00),
                        ("Jambon blanc x4 tr", 2.80, 4.10)],
    "fruits_legumes": [("Tomates grappe vrac", 0.90, 1.80),
                       ("Bananes vrac", 0.80, 1.40),
                       ("Pommes Gala 1kg", 1.50, 2.40),
                       ("Salade laitue", 1.10, 1.70)],
    "epicerie": [("Huile d'olive 75cl", 5.20, 8.00),
                 ("Riz long 1kg", 2.10, 3.10),
                 ("Café moulu Carte Noire 250g", 3.20, 4.50)],
    "boissons": [("Eau minérale 6x1.5L", 2.20, 3.20),
                 ("Jus d'orange 1L", 1.80, 2.80),
                 ("Coca-Cola 1.5L", 1.70, 2.30)],
    "hygiene": [("Dentifrice Signal 75ml", 1.80, 2.50),
                ("Gel douche 250ml", 2.10, 3.20)],
}

STORES = ["Intermarché", "Carrefour", "Monoprix", "Lidl", "Franprix"]


def _random_basket() -> list[tuple[str, float, int]]:
    n = random.randint(5, 12)
    items: list[tuple[str, float, int]] = []
    cats = list(PRODUCTS.keys())
    while len(items) < n:
        cat = random.choice(cats)
        name, lo, hi = random.choice(PRODUCTS[cat])
        if any(name == it[0] for it in items):
            continue
        price = round(random.uniform(lo, hi), 2)
        qty = random.choices([1, 2, 3], weights=[7, 2, 1])[0]
        items.append((name, price, qty))
    return items


def _build_payload(store: str, when: datetime) -> dict:
    items = [
        {"name": name, "price": round(price * qty, 2), "quantity": float(qty)}
        for (name, price, qty) in _random_basket()
    ]
    total = round(sum(it["price"] for it in items), 2)
    return {
        "demo": True,
        "ocr": {"text": "(seed demo)", "avg_confidence": 0.95, "line_count": len(items)},
        "receipt": {"enseigne": store, "date": when.strftime("%Y-%m-%d"),
                    "total": total, "items": items},
        "comparisons": [],
        "total_savings": round(random.uniform(0.5, 8.0), 2),
    }


def _get_or_create_user(db, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, name=email.split("@")[0],
                    password_hash=hash_password(password))
        db.add(user)
        db.flush()
        print(f"Compte démo créé : {email} / {password}")
    return user


def seed(email: str, password: str, n: int, days_back: int) -> None:
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        user = _get_or_create_user(db, email, password)
        for _ in range(n):
            offset = random.uniform(0, days_back)
            when = (now - timedelta(days=offset)).replace(
                hour=random.randint(8, 20), minute=random.randint(0, 59),
                second=0, microsecond=0)
            payload = _build_payload(random.choice(STORES), when)
            rid, _ = receipts_store.save_receipt(db, user, payload)
            # Aligne scanned_at sur la date simulée
            rec = db.get(Receipt, rid)
            if rec:
                rec.scanned_at = when
        print(f"{n} tickets démo ajoutés pour {email}.")


def clear(email: str) -> None:
    with session_scope() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"Aucun compte {email}.")
            return
        removed = 0
        for rec in db.query(Receipt).filter(Receipt.user_id == user.id).all():
            if rec.payload().get("demo") is True:
                db.delete(rec)
                removed += 1
        print(f"{removed} tickets démo supprimés pour {email}. Les vrais sont gardés.")


def main():
    parser = argparse.ArgumentParser(description="Seed/clear demo receipts (per user)")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--n", type=int, default=18)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    init_db()
    if args.clear:
        clear(args.email)
    else:
        random.seed()
        seed(args.email, args.password, args.n, args.days)


if __name__ == "__main__":
    main()
