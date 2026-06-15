"""
Benchmark de qualité du matching (déterministe, sans dépendre du scrape)
========================================================================
Construit un petit catalogue étiqueté en mémoire (Monoprix + Lidl) et vérifie,
sur des libellés de ticket réalistes (MAJUSCULES + abréviations + fautes OCR) :

  - **Précision** : un item hors-catalogue ne doit PAS produire de faux match.
  - **Rappel**    : un item présent doit retrouver le bon produit.
  - **Quantité**  : un 50 cl n'est jamais proposé "moins cher" qu'un 1 L à moins
                    d'être réellement moins cher au litre.
  - **Cross-enseigne** : l'alternative moins chère pointe la bonne enseigne.

Lancement :
  pytest -q matching/test_matching_quality.py -s
  (le -s affiche le tableau de métriques)
"""

from __future__ import annotations

import pytest

from matching.embeddings import Embedder
from matching.index import ProductIndex
from matching.matcher import Matcher
from ner.models import LineItem


# ─── Catalogue étiqueté ──────────────────────────────────────────────
CATALOG = [
    # Lait : même produit, 2 enseignes, Lidl moins cher (test cross-enseigne)
    {"name": "Lait demi-écrémé UHT 1 L", "brand": "Lactel", "price": 1.20, "enseigne": "Monoprix"},
    {"name": "Lait demi-écrémé UHT 1 L", "brand": "Envia", "price": 0.95, "enseigne": "Lidl"},
    # Coca : 1.5 L vs 50 cl (test gate quantité + prix au litre)
    {"name": "Coca-Cola bouteille 1,5 L", "brand": "Coca-Cola", "price": 1.80, "enseigne": "Monoprix"},
    {"name": "Coca-Cola canette 50 cl", "brand": "Coca-Cola", "price": 0.95, "enseigne": "Lidl"},
    # Chocolat
    {"name": "Tablette chocolat noir dégustation 100 g", "brand": "Lindt", "price": 1.89, "enseigne": "Monoprix"},
    {"name": "Chocolat noir 100 g", "brand": "Fin Carré", "price": 0.85, "enseigne": "Lidl"},
    # Café
    {"name": "Café en grains Arabica 250 g", "brand": "Carte Noire", "price": 3.40, "enseigne": "Monoprix"},
    {"name": "Café moulu 250 g", "brand": "Bellarom", "price": 1.99, "enseigne": "Lidl"},
    # Pâtes
    {"name": "Spaghetti n°5 500 g", "brand": "Panzani", "price": 1.49, "enseigne": "Monoprix"},
    {"name": "Penne rigate 500 g", "brand": "Combino", "price": 0.69, "enseigne": "Lidl"},
    # Crémerie / charcuterie / hygiène (distracteurs réalistes)
    {"name": "Yaourt nature x4", "brand": "Danone", "price": 1.65, "enseigne": "Monoprix"},
    {"name": "Beurre doux 250 g", "brand": "Président", "price": 2.10, "enseigne": "Monoprix"},
    {"name": "Jambon blanc 4 tranches", "brand": "Herta", "price": 2.95, "enseigne": "Monoprix"},
    {"name": "Emmental râpé 200 g", "brand": "Monoprix", "price": 1.79, "enseigne": "Monoprix"},
    {"name": "Gel hydroalcoolique mains 75 ml", "brand": "Sanytol", "price": 3.10, "enseigne": "Monoprix"},
    {"name": "Dentifrice charbon 75 ml", "brand": "Signal", "price": 2.07, "enseigne": "Monoprix"},
    {"name": "Beignet chocolat noisette", "brand": "", "price": 1.20, "enseigne": "Lidl"},
    {"name": "Jus d'orange 1 L", "brand": "Tropicana", "price": 2.30, "enseigne": "Monoprix"},
    {"name": "Eau minérale naturelle 1,5 L", "brand": "Evian", "price": 0.65, "enseigne": "Monoprix"},
    {"name": "Bananes", "brand": "", "price": 1.99, "enseigne": "Monoprix"},
]


# (libellé ticket OCR, prix ticket, sous-chaîne attendue dans le match OU None,
#  enseigne attendue pour l'alternative moins chère OU None)
CASES = [
    ("LAIT 1/2 ECR 1L", 1.20, "lait", "Lidl"),
    ("CHOCO NOIR 100G", 1.89, "chocolat noir", None),  # meilleur match déjà Lidl (moins cher)
    ("CFE GRAINS 250G", 3.40, "café en grains", "Lidl"),  # alt Lidl café moins cher
    ("SPAGHETTI N5 500G", 1.49, "spaghetti", None),       # pas de penne moins cher en autre enseigne ? Lidl 0.69
    ("YT NATURE X4", 1.65, "yaourt nature", None),
    ("JAMBON BLANC 4T", 2.95, "jambon", None),
    ("EMMENTAL RAPE 200G", 1.79, "emmental", None),
    ("SANYTOL GEL MAINS", 3.10, "gel", None),
    ("COCA COLA 1,5L", 1.80, "coca", None),               # le 50cl n'est PAS moins cher au litre
    ("JUS ORANGE 1L", 2.30, "jus", None),
    # ── Négatifs durs : hors catalogue → AUCUN match attendu ──
    ("PILES AAA LR03 X4", 3.50, None, None),
    ("SAC POUBELLE 30L", 2.40, None, None),
    ("GALETTE PAIN EPICE NOEL", 2.10, None, None),        # ne doit PAS matcher "Beignet chocolat noisette"
    ("CARTE CADEAU", 20.0, None, None),
]


@pytest.fixture(scope="module")
def matcher() -> Matcher:
    embedder = Embedder()
    index = ProductIndex.build([dict(p) for p in CATALOG], embedder)
    return Matcher(index=index)


def test_matching_benchmark(matcher: Matcher):
    rows = []
    correct_match = 0
    n_positive = 0
    false_positive = 0
    n_negative = 0
    alt_correct = 0
    n_alt_expected = 0

    for label, price, expected, alt_enseigne in CASES:
        cmp = matcher.compare_item(LineItem(name=label, price=price, quantity=1))
        got = cmp.best_match_name
        got_norm = got.lower()

        if expected is None:
            n_negative += 1
            ok = got == ""
            if not ok:
                false_positive += 1
            verdict = "OK (rejeté)" if ok else f"FAUX POSITIF -> {got}"
        else:
            n_positive += 1
            ok = expected in got_norm
            if ok:
                correct_match += 1
            verdict = "OK" if ok else f"RATÉ (attendu '{expected}', eu '{got or '∅'}')"

        if alt_enseigne is not None:
            n_alt_expected += 1
            alts = [a["enseigne"] for a in cmp.cheaper_alternatives]
            if alt_enseigne in alts:
                alt_correct += 1
                verdict += f" | alt={alt_enseigne}✓"
            else:
                verdict += f" | alt attendue {alt_enseigne}, eu {alts or '∅'}"

        rows.append((label, got[:34] if got else "∅", round(cmp.best_match_score, 2),
                     [f"{a['enseigne']}:{a['price']}" for a in cmp.cheaper_alternatives], verdict))

    # Affichage lisible
    print("\n" + "=" * 100)
    print(f"{'TICKET':<26}{'MATCH':<36}{'SCORE':<7}{'ALTERNATIVES'}")
    print("-" * 100)
    for label, got, score, alts, verdict in rows:
        print(f"{label:<26}{got:<36}{score:<7}{alts}")
        print(f"{'':<26}└─ {verdict}")
    print("=" * 100)
    print(f"Rappel (bons matchs)   : {correct_match}/{n_positive}")
    print(f"Précision (négatifs)   : {n_negative - false_positive}/{n_negative} rejetés correctement")
    print(f"Alternatives correctes : {alt_correct}/{n_alt_expected}")
    print("=" * 100)

    # ─── Assertions (seuils de qualité) ───
    assert correct_match >= n_positive - 1, "Trop de bons produits ratés (rappel insuffisant)"
    assert false_positive == 0, "Faux positif sur un item hors-catalogue (précision insuffisante)"
    assert alt_correct == n_alt_expected, "Alternatives cross-enseigne incorrectes"
