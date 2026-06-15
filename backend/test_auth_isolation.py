"""
Tests d'authentification et d'ISOLATION des données par utilisateur
===================================================================
Vérifie le point dur de la demande métier : un utilisateur ne doit JAMAIS voir
les tickets d'un autre.

  - inscription / connexion email+mot de passe + JWT,
  - /history, /history/{id}, /history/stats strictement scopés,
  - accès sans token refusé (401),
  - endpoint Google câblé et refusant un token bidon.

La base est une SQLite temporaire (aucune pollution du vrai data/).
Le pipeline OCR/NER n'est pas sollicité : on insère les tickets via le store.
Lancement : pytest -q backend/test_auth_isolation.py
"""

from __future__ import annotations

import os
import tempfile

import pytest

# Base de test AVANT tout import applicatif.
_TMP_DB = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["SMARTFOYER_DB_URL"] = f"sqlite:///{_TMP_DB}"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend import db as db_module  # noqa: E402
from backend import receipts_store  # noqa: E402


client = TestClient(app)


def _fake_payload(enseigne: str, total: float) -> dict:
    return {
        "receipt": {
            "enseigne": enseigne,
            "date": "2026-06-01",
            "total": total,
            "items": [
                {"name": "Lait demi-écrémé 1L", "price": 1.20, "quantity": 1},
                {"name": "Chocolat noir 100g", "price": 1.89, "quantity": 1},
            ],
        },
        "total_savings": 0.50,
        "ocr": {"avg_confidence": 0.93, "text": "...", "line_count": 10},
        "comparisons": [],
    }


def _register(email: str, password: str = "secret123") -> str:
    r = client.post("/auth/register", json={"email": email, "password": password,
                                            "name": email.split("@")[0]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me():
    token = _register("alice@example.com")
    # /me renvoie le bon profil
    me = client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"

    # mauvais mot de passe rejeté
    bad = client.post("/auth/login", json={"email": "alice@example.com",
                                           "password": "wrong"})
    assert bad.status_code == 401

    # bon mot de passe accepté
    ok = client.post("/auth/login", json={"email": "alice@example.com",
                                          "password": "secret123"})
    assert ok.status_code == 200 and ok.json()["access_token"]

    # email déjà pris
    dup = client.post("/auth/register", json={"email": "alice@example.com",
                                              "password": "secret123"})
    assert dup.status_code == 409


def test_history_requires_auth():
    assert client.get("/history").status_code == 401
    assert client.get("/history/stats").status_code == 401
    assert client.post("/chat", json={"question": "x"}).status_code == 401


def test_data_isolation_between_users():
    tok_a = _register("bob@example.com")
    tok_b = _register("carol@example.com")

    # Insère 2 tickets pour Bob, 0 pour Carol (via le store, scopé).
    db = db_module.get_session()
    try:
        from backend.db import User
        bob = db.query(User).filter(User.email == "bob@example.com").first()
        rid1, _ = receipts_store.save_receipt(db, bob, _fake_payload("Monoprix", 12.5))
        rid2, _ = receipts_store.save_receipt(db, bob, _fake_payload("Lidl", 8.0))
    finally:
        db.close()

    # Bob voit ses 2 tickets
    ha = client.get("/history", headers=_auth(tok_a))
    assert ha.status_code == 200 and len(ha.json()) == 2

    # Carol n'en voit AUCUN
    hb = client.get("/history", headers=_auth(tok_b))
    assert hb.status_code == 200 and hb.json() == []

    # Carol ne peut PAS lire le détail d'un ticket de Bob → 404
    detail_b = client.get(f"/history/{rid1}", headers=_auth(tok_b))
    assert detail_b.status_code == 404
    # Bob peut
    detail_a = client.get(f"/history/{rid1}", headers=_auth(tok_a))
    assert detail_a.status_code == 200
    assert detail_a.json()["receipt"]["enseigne"] == "Monoprix"

    # Stats scopées : Bob a un total, Carol a 0
    sa = client.get("/history/stats", headers=_auth(tok_a)).json()
    sb = client.get("/history/stats", headers=_auth(tok_b)).json()
    assert sa["n_receipts"] == 2 and sa["total_spent"] == pytest.approx(20.5)
    assert sb["n_receipts"] == 0 and sb["total_spent"] == 0
    # Catégories calculées (lait → Crémerie, chocolat → Épicerie sucrée)
    assert sa["by_category"]


def test_delete_receipt_scoped():
    """Suppression d'un ticket : seul le propriétaire peut, et ça disparaît."""
    tok_a = _register("dave@example.com")
    tok_b = _register("erin@example.com")

    db = db_module.get_session()
    try:
        from backend.db import User
        dave = db.query(User).filter(User.email == "dave@example.com").first()
        rid, _ = receipts_store.save_receipt(db, dave, _fake_payload("Monoprix", 9.9))
    finally:
        db.close()

    # Erin ne peut pas supprimer le ticket de Dave
    assert client.delete(f"/history/{rid}", headers=_auth(tok_b)).status_code == 404
    # Le ticket de Dave est toujours là
    assert len(client.get("/history", headers=_auth(tok_a)).json()) == 1
    # Dave le supprime
    assert client.delete(f"/history/{rid}", headers=_auth(tok_a)).status_code == 200
    # Plus aucun ticket
    assert client.get("/history", headers=_auth(tok_a)).json() == []
    # Suppression d'un id inexistant -> 404
    assert client.delete("/history/inexistant123", headers=_auth(tok_a)).status_code == 404


def test_google_endpoint_rejects_bogus_token():
    r = client.post("/auth/google", json={"id_token": "not-a-real-token"})
    # Selon que GOOGLE_CLIENT_ID est configuré : 401 (token invalide) ou 503.
    assert r.status_code in (400, 401, 503)
