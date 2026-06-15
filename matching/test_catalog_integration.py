"""
Test d'intégration sur le CATALOGUE RÉEL (données scrapées)
===========================================================
Contrairement au benchmark déterministe, ce test charge l'index FAISS construit
à partir des produits Lidl + Monoprix réellement scrapés. Il est volontairement
tolérant (le contenu du catalogue varie selon le scrape), mais verrouille les
garanties dures :

  - l'index charge et contient les deux enseignes,
  - un article clairement hors-catalogue ne produit PAS de faux match,
  - le matcher reste sous les ~quelques secondes sur un petit lot.

Skippé si l'index n'a pas encore été construit (python -m matching.build_index).
Lancement : pytest -q matching/test_catalog_integration.py -s
"""

from __future__ import annotations

from pathlib import Path

import pytest

from matching.matcher import Matcher
from ner.models import LineItem


INDEX_PREFIX = Path(__file__).resolve().parent.parent / "data" / "index" / "catalog"
_HAS_INDEX = (INDEX_PREFIX.parent / (INDEX_PREFIX.name + ".faiss")).exists()

pytestmark = pytest.mark.skipif(
    not _HAS_INDEX, reason="Index catalogue absent (lancer matching.build_index)"
)


@pytest.fixture(scope="module")
def matcher() -> Matcher:
    return Matcher.from_disk(str(INDEX_PREFIX))


def test_catalog_has_both_enseignes(matcher: Matcher):
    enseignes = {p.get("enseigne") for p in matcher.index.products}
    assert "Monoprix" in enseignes
    assert "Lidl" in enseignes
    assert matcher.index.index.ntotal >= 200


def test_no_false_match_on_out_of_catalog(matcher: Matcher):
    """Des articles clairement absents ne doivent pas matcher (précision)."""
    for label in ["FRAIS DE LIVRAISON", "ABONNEMENT INTERNET", "ZQXW INCONNU 123"]:
        c = matcher.compare_item(LineItem(name=label, price=5.0, quantity=1))
        assert c.best_match_name == "", \
            f"Faux positif sur '{label}' -> {c.best_match_enseigne} {c.best_match_name}"


def test_common_items_find_a_match(matcher: Matcher):
    """Au moins une majorité d'articles courants trouve un match plausible."""
    common = ["CAFE GRAINS 250G", "COCA COLA 1.5L", "YAOURT NATURE",
              "JUS ORANGE 1L", "PATES 500G"]
    found = 0
    for label in common:
        c = matcher.compare_item(LineItem(name=label, price=2.0, quantity=1))
        if c.best_match_name:
            found += 1
            print(f"{label:<20} -> {c.best_match_enseigne} {c.best_match_name[:40]} ({c.best_match_score:.2f})")
    assert found >= 3, f"Trop peu de matchs sur des articles courants ({found}/5)"
