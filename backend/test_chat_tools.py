"""
Tests des outils déterministes de l'agent IA (backend/chat_tools.py).
Hors-ligne : aucune dépendance réseau, base ni clé API. C'est ce qui permet
de valider l'agent sans se connecter à l'app.

    pytest backend/test_chat_tools.py
"""

from backend import chat_tools as ct


# ─── Fixtures : 3 tickets factices ───────────────────────────────────
RECEIPTS = [
    {
        "scanned_at": "2026-03-30T12:00:00+00:00",
        "receipt": {
            "enseigne": "Lidl",
            "date": "30/03/2026",
            "total": 12.0,
            "items": [
                {"name": "Jus d'orange 1L", "price": 5.0, "quantity": 2.0},
                {"name": "Baguette tradition", "price": 3.0, "quantity": 3.0},
                {"name": "Lait demi-écrémé 1L", "price": 4.0, "quantity": 4.0},
            ],
        },
        "comparisons": [
            {
                "scanned_name": "Jus d'orange 1L",
                "scanned_price": 5.0,
                "cheaper_alternatives": [
                    {"name": "Jus orange Monoprix 1L", "enseigne": "Monoprix",
                     "price": 3.5, "savings": 1.5},
                ],
            },
        ],
        "total_savings": 1.5,
    },
    {
        "scanned_at": "2026-04-10T12:00:00+00:00",
        "receipt": {
            "enseigne": "Monoprix",
            "date": "10/04/2026",
            "total": 8.0,
            "items": [
                {"name": "Lait demi-écrémé 1L", "price": 2.0, "quantity": 2.0},
                {"name": "Pain de mie complet", "price": 6.0, "quantity": 1.0},
            ],
        },
        "comparisons": [],
        "total_savings": 0.0,
    },
    {
        "scanned_at": "2026-04-20T12:00:00+00:00",
        "receipt": {
            "enseigne": "Lidl",
            "date": "20/04/2026",
            "total": 10.0,
            "items": [
                {"name": "Coca-Cola 1.5L", "price": 10.0, "quantity": 4.0},
            ],
        },
        "comparisons": [],
        "total_savings": 0.0,
    },
]


# ─── spending_summary ────────────────────────────────────────────────
def test_spending_summary_global():
    res = ct.spending_summary(RECEIPTS)
    assert res["total_depense_eur"] == 30.0          # 12 + 8 + 10
    assert res["nb_tickets"] == 3
    assert res["panier_moyen_eur"] == 10.0


def test_spending_summary_by_enseigne():
    res = ct.spending_summary(RECEIPTS, enseigne="Lidl")
    assert res["total_depense_eur"] == 22.0          # 12 + 10
    assert res["nb_tickets"] == 2


def test_spending_summary_by_period():
    # Avril uniquement -> Monoprix (8) + Lidl 20/04 (10)
    res = ct.spending_summary(RECEIPTS, start_date="2026-04-01",
                              end_date="2026-04-30")
    assert res["total_depense_eur"] == 18.0
    assert res["nb_tickets"] == 2


def test_spending_summary_by_category():
    # Cremerie = lait (4.0 chez Lidl + 2.0 chez Monoprix)
    res = ct.spending_summary(RECEIPTS, category="Cremerie")
    assert res["total_depense_eur"] == 6.0
    assert res["nb_lignes_produit"] == 2


def test_spending_summary_period_and_category():
    # Boissons en avril -> Coca 10.0 (le jus d'orange est en mars)
    res = ct.spending_summary(RECEIPTS, start_date="2026-04-01",
                              end_date="2026-04-30", category="Boissons")
    assert res["total_depense_eur"] == 10.0


# ─── product_spending ────────────────────────────────────────────────
def test_product_spending_lait():
    res = ct.product_spending(RECEIPTS, "lait")
    assert res["total_depense_eur"] == 6.0           # 4.0 + 2.0
    assert res["quantite_totale"] == 6.0             # 4 + 2
    assert res["nb_lignes"] == 2
    assert len(res["produits"]) == 1                 # même libellé regroupé


def test_product_spending_accent_insensitive():
    # "ecreme" sans accent doit matcher "écrémé"
    res = ct.product_spending(RECEIPTS, "ecreme")
    assert res["total_depense_eur"] == 6.0


def test_product_spending_no_match():
    res = ct.product_spending(RECEIPTS, "saumon")
    assert res["total_depense_eur"] == 0.0
    assert res["nb_lignes"] == 0


# ─── compare_enseignes ───────────────────────────────────────────────
def test_compare_enseignes():
    res = ct.compare_enseignes(RECEIPTS)
    by = {e["enseigne"]: e for e in res["enseignes"]}
    assert by["Lidl"]["total_eur"] == 22.0
    assert by["Lidl"]["nb_tickets"] == 2
    assert by["Lidl"]["panier_moyen_eur"] == 11.0
    assert by["Monoprix"]["total_eur"] == 8.0
    # trié par total décroissant
    assert res["enseignes"][0]["enseigne"] == "Lidl"


# ─── savings_summary ─────────────────────────────────────────────────
def test_savings_summary():
    res = ct.savings_summary(RECEIPTS)
    assert res["economies_cumulees_eur"] == 1.5
    assert res["nb_opportunites"] == 1
    opp = res["meilleures_opportunites"][0]
    assert opp["produit"] == "Jus d'orange 1L"
    assert opp["enseigne_alternative"] == "Monoprix"
    assert opp["economie_eur"] == 1.5


# ─── top_products ────────────────────────────────────────────────────
def test_top_products_total_cumule():
    res = ct.top_products(RECEIPTS, metric="total_cumule")
    # Lait : 4.0 (Lidl) + 2.0 (Monoprix) = 6.0 ; Coca : 10.0 ; Jus : 5.0 ...
    by = {p["nom"]: p for p in res["produits"]}
    assert by["Coca-Cola 1.5L"]["total_eur"] == 10.0
    assert by["Lait demi-écrémé 1L"]["total_eur"] == 6.0
    assert by["Lait demi-écrémé 1L"]["nb_achats"] == 2
    # le plus cher en cumulé arrive en tête
    assert res["produits"][0]["nom"] == "Coca-Cola 1.5L"


def test_top_products_prix_max():
    res = ct.top_products(RECEIPTS, metric="prix_max", limit=1)
    assert res["produits"][0]["nom"] == "Coca-Cola 1.5L"
    assert res["produits"][0]["prix_ligne_max_eur"] == 10.0


# ─── compare_periodes ────────────────────────────────────────────────
def test_compare_periodes():
    # A = avril (8 + 10 = 18), B = mars (12)
    res = ct.compare_periodes(
        RECEIPTS,
        periode_a_debut="2026-04-01", periode_a_fin="2026-04-30",
        periode_b_debut="2026-03-01", periode_b_fin="2026-03-31",
    )
    assert res["periode_a"]["total_eur"] == 18.0
    assert res["periode_b"]["total_eur"] == 12.0
    assert res["difference_eur"] == 6.0
    assert res["evolution_pct"] == 50.0
    assert res["tendance"] == "hausse"


def test_compare_periodes_reference_vide():
    # B sans ticket -> pas de pourcentage (évite la division par zéro)
    res = ct.compare_periodes(
        RECEIPTS,
        periode_a_debut="2026-03-01", periode_a_fin="2026-03-31",
        periode_b_debut="2026-01-01", periode_b_fin="2026-01-31",
    )
    assert res["periode_b"]["total_eur"] == 0.0
    assert res["evolution_pct"] is None


# ─── cheapest_place_for_product ──────────────────────────────────────
def test_cheapest_place_for_product():
    # Lait : Lidl 4.0/4 = 1.0/unité ; Monoprix 2.0/2 = 1.0/unité -> égalité
    res = ct.cheapest_place_for_product(RECEIPTS, "lait")
    assert res["trouve"] is True
    assert res["nb_achats"] == 2
    assert res["moins_cher_chez"]["prix_par_unite_achetee_eur"] == 1.0
    assert len(res["par_enseigne"]) == 2


def test_cheapest_place_for_product_not_found():
    res = ct.cheapest_place_for_product(RECEIPTS, "saumon")
    assert res["trouve"] is False


# ─── category_breakdown ──────────────────────────────────────────────
def test_category_breakdown():
    # Boissons : jus 5 + coca 10 = 15 ; Boulangerie : baguette 3 + pain 6 = 9 ;
    # Cremerie : lait 4 + 2 = 6. Total = 30.
    res = ct.category_breakdown(RECEIPTS)
    assert res["total_eur"] == 30.0
    cats = {c["categorie"]: c for c in res["categories"]}
    assert cats["Boissons"]["total_eur"] == 15.0
    assert cats["Boissons"]["part_pct"] == 50.0
    assert res["categories"][0]["categorie"] == "Boissons"  # trié desc


# ─── spending_trend ──────────────────────────────────────────────────
def test_spending_trend():
    res = ct.spending_trend(RECEIPTS)
    serie = {p["mois"]: p["total_eur"] for p in res["par_mois"]}
    assert serie["2026-03"] == 12.0           # un ticket Lidl
    assert serie["2026-04"] == 18.0           # 8 + 10
    assert res["tendance_globale"] == "hausse"


# ─── price_evolution ─────────────────────────────────────────────────
def test_price_evolution_lait():
    # Lidl 30/03 : 4.0/4 = 1.0 ; Monoprix 10/04 : 2.0/2 = 1.0 -> stable
    res = ct.price_evolution(RECEIPTS, "lait")
    assert res["trouve"] is True
    assert res["nb_points"] == 2
    assert res["prix_premier_eur"] == 1.0
    assert res["prix_dernier_eur"] == 1.0
    assert res["variation_eur"] == 0.0


def test_price_evolution_not_found():
    res = ct.price_evolution(RECEIPTS, "saumon")
    assert res["trouve"] is False


# ─── frequent_products ───────────────────────────────────────────────
def test_frequent_products():
    res = ct.frequent_products(RECEIPTS)
    by = {p["nom"]: p for p in res["produits"]}
    # le lait est acheté 2 fois (Lidl + Monoprix)
    assert by["Lait demi-écrémé 1L"]["nb_achats"] == 2
    assert res["produits"][0]["nb_achats"] == 2  # le plus fréquent en tête


# ─── biggest_receipt ─────────────────────────────────────────────────
def test_biggest_receipt():
    res = ct.biggest_receipt(RECEIPTS)
    assert res["trouve"] is True
    assert res["total_eur"] == 12.0           # le ticket Lidl du 30/03
    assert res["enseigne"] == "Lidl"


def test_biggest_receipt_empty():
    res = ct.biggest_receipt([])
    assert res["trouve"] is False


# ─── run_tool (dispatcher) ───────────────────────────────────────────
def test_run_tool_dispatch():
    res = ct.run_tool("compare_enseignes", {}, RECEIPTS)
    assert "enseignes" in res


def test_run_tool_unknown():
    res = ct.run_tool("does_not_exist", {}, RECEIPTS)
    assert "error" in res


def test_run_tool_bad_args_does_not_raise():
    # argument inconnu -> erreur renvoyée, pas d'exception
    res = ct.run_tool("product_spending", {"wrong": "x"}, RECEIPTS)
    assert "error" in res


def test_run_tool_empty_receipts():
    res = ct.run_tool("spending_summary", {}, [])
    assert res["total_depense_eur"] == 0.0
    assert res["panier_moyen_eur"] == 0.0
