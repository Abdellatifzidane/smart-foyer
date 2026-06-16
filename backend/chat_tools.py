"""
Outils déterministes pour l'agent IA (tool-calling).
=====================================================
Le LLM ne calcule JAMAIS lui-même un montant : il choisit un outil, Python
calcule le chiffre exact à partir des tickets du user, et le LLM se contente
de rédiger la réponse autour du résultat. Les nombres sont donc fiables par
construction.

Chaque fonction est PURE : elle prend la liste des payloads de tickets
(`receipts`, déjà scopés au user courant) et renvoie un dict de résultats.
Aucune dépendance réseau / base -> testable hors-ligne (voir
backend/test_chat_tools.py).

Organisation
------------
Un outil se déclare UNE seule fois, avec le décorateur ``@tool`` posé juste
au-dessus de sa fonction (schéma + implémentation collés ensemble). Le registre
en dérive automatiquement :
  - ``TOOL_SCHEMAS`` : la liste envoyée au LLM (format Groq / OpenAI),
  - ``run_tool(name, args, receipts)`` : le dispatch qui exécute l'outil.
=> impossible d'exposer au LLM un outil sans implémentation (ou l'inverse).

Forme d'un payload (cf. receipts_store.load_payloads) :
  {
    "scanned_at": "2026-03-30T12:37:00+00:00",
    "receipt": {"enseigne", "date" (JJ/MM/AAAA), "total",
                "items": [{"name", "price" (total de ligne), "quantity"}]},
    "comparisons": [ItemComparison...],   # alternatives moins chères du matching
    "total_savings": 1.56,
  }
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Callable

from matching.normalize import infer_category, normalize_text


# Catégories possibles renvoyées par infer_category (pour documenter l'outil).
CATEGORIES = [
    "Boulangerie", "Cremerie", "Boissons", "Cafe", "Epicerie sucree",
    "Epicerie salee", "Charcuterie", "Viande/Poisson", "Fruits/Legumes",
    "Surgele", "Hygiene", "Entretien", "Bebe", "Animaux",
]
_CAT_LIST = ", ".join(CATEGORIES)


# ─── Registre d'outils ───────────────────────────────────────────────
# Source unique de vérité : le décorateur enregistre, pour chaque outil, la
# fonction ET son schéma. TOOL_SCHEMAS et run_tool sont construits à partir
# de ce registre, donc toujours cohérents entre eux.
_REGISTRY: dict[str, dict] = {}


def tool(description: str, parameters: dict) -> Callable:
    """Décorateur qui enregistre une fonction comme outil exposé au LLM.

    Le nom de l'outil = le nom de la fonction. `description` + `parameters`
    forment le schéma (format Groq / OpenAI). La fonction est renvoyée telle
    quelle : elle reste appelable et testable directement.
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[fn.__name__] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": description,
                    "parameters": parameters,
                },
            },
        }
        return fn
    return decorator


# ─── Helpers (internes, non exposés au LLM) ──────────────────────────
def _parse_date(s: str | None) -> date | None:
    """date depuis 'JJ/MM/AAAA' ou 'AAAA-MM-JJ...' (ISO), sinon None."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _receipt_date(r: dict) -> date | None:
    receipt = r.get("receipt") or {}
    return _parse_date(receipt.get("date")) or _parse_date(r.get("scanned_at"))


def _in_range(d: date | None, start: date | None, end: date | None) -> bool:
    if d is None:
        # Un ticket sans date n'est compté que s'il n'y a aucun filtre temporel.
        return start is None and end is None
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def _filter_receipts(receipts: list[dict], start_date=None, end_date=None,
                     enseigne=None) -> list[dict]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    ens = (enseigne or "").strip().lower()
    out = []
    for r in receipts:
        if not _in_range(_receipt_date(r), start, end):
            continue
        if ens:
            r_ens = ((r.get("receipt") or {}).get("enseigne") or "").strip().lower()
            if ens not in r_ens:
                continue
        out.append(r)
    return out


# ─── Outils ──────────────────────────────────────────────────────────
@tool(
    description=(
        "Calcule les dépenses totales, le nombre de tickets et le panier "
        "moyen. À utiliser pour TOUTE question chiffrée sur les dépenses (sur "
        "une période, une enseigne, ou une catégorie). Les dates se déduisent "
        "de la date du jour fournie dans le contexte."),
    parameters={
        "type": "object",
        "properties": {
            "start_date": {"type": "string",
                           "description": "Date de début incluse, format AAAA-MM-JJ. Optionnel."},
            "end_date": {"type": "string",
                         "description": "Date de fin incluse, format AAAA-MM-JJ. Optionnel."},
            "enseigne": {"type": "string",
                         "description": "Filtre enseigne (ex. 'Lidl', 'Monoprix'). Optionnel."},
            "category": {"type": "string",
                         "description": f"Filtre catégorie produit. Valeurs possibles : {_CAT_LIST}. Optionnel."},
        },
    },
)
def spending_summary(receipts: list[dict], start_date=None, end_date=None,
                     enseigne=None, category=None) -> dict:
    """Dépenses totales, nb de tickets et panier moyen, filtrables par
    période / enseigne / catégorie. L'outil principal pour toute question
    chiffrée sur les dépenses."""
    sel = _filter_receipts(receipts, start_date, end_date, enseigne)
    filtre = {"start_date": start_date, "end_date": end_date,
              "enseigne": enseigne, "category": category}

    if category:
        cat = category.strip().lower()
        total = 0.0
        n_lines = 0
        for r in sel:
            for it in (r.get("receipt") or {}).get("items") or []:
                if infer_category(it.get("name") or "").lower() == cat:
                    total += float(it.get("price") or 0)
                    n_lines += 1
        return {
            "filtre": filtre,
            "total_depense_eur": round(total, 2),
            "nb_lignes_produit": n_lines,
            "nb_tickets_dans_periode": len(sel),
        }

    total = sum(float((r.get("receipt") or {}).get("total") or 0) for r in sel)
    n = len(sel)
    return {
        "filtre": filtre,
        "total_depense_eur": round(total, 2),
        "nb_tickets": n,
        "panier_moyen_eur": round(total / n, 2) if n else 0.0,
    }


@tool(
    description=(
        "Combien l'utilisateur a dépensé (et quelle quantité) sur un produit "
        "précis désigné par un mot-clé (ex. 'lait', 'coca', 'pain'). Renvoie "
        "le détail par libellé de produit."),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "Mot-clé du produit recherché, ex. 'lait'."},
        },
        "required": ["query"],
    },
)
def product_spending(receipts: list[dict], query: str) -> dict:
    """Dépense cumulée et quantité achetée pour les produits dont le nom
    contient `query` (recherche normalisée : accents/abréviations gérés)."""
    q = normalize_text(query or "", drop_quantity=True).strip()
    if not q:
        return {"query": query, "total_depense_eur": 0.0,
                "quantite_totale": 0.0, "nb_lignes": 0, "produits": []}

    total = qty = 0.0
    n = 0
    by_name: dict[str, dict] = defaultdict(
        lambda: {"total": 0.0, "quantite": 0.0, "n": 0})
    for r in receipts:
        for it in (r.get("receipt") or {}).get("items") or []:
            name = it.get("name") or ""
            if q in normalize_text(name, drop_quantity=True):
                price = float(it.get("price") or 0)
                quantity = float(it.get("quantity") or 0)
                total += price
                qty += quantity
                n += 1
                by_name[name]["total"] += price
                by_name[name]["quantite"] += quantity
                by_name[name]["n"] += 1

    produits = sorted(
        ({"nom": k, "total_eur": round(v["total"], 2),
          "quantite": round(v["quantite"], 2), "nb_achats": v["n"]}
         for k, v in by_name.items()),
        key=lambda x: -x["total_eur"],
    )[:10]
    return {
        "query": query,
        "total_depense_eur": round(total, 2),
        "quantite_totale": round(qty, 2),
        "nb_lignes": n,
        "produits": produits,
    }


@tool(
    description=(
        "Compare les enseignes : total dépensé, nombre de tickets et panier "
        "moyen pour chacune. À utiliser pour 'où je dépense le plus', 'Lidl ou "
        "Monoprix', 'mon panier moyen par magasin'."),
    parameters={"type": "object", "properties": {}},
)
def compare_enseignes(receipts: list[dict]) -> dict:
    """Total dépensé, nb de tickets et panier moyen par enseigne (pour
    comparer où l'utilisateur dépense le plus / le panier le plus cher)."""
    agg: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "n": 0})
    for r in receipts:
        receipt = r.get("receipt") or {}
        ens = (receipt.get("enseigne") or "Inconnu").strip() or "Inconnu"
        agg[ens]["total"] += float(receipt.get("total") or 0)
        agg[ens]["n"] += 1
    enseignes = sorted(
        ({"enseigne": k, "total_eur": round(v["total"], 2),
          "nb_tickets": v["n"],
          "panier_moyen_eur": round(v["total"] / v["n"], 2) if v["n"] else 0.0}
         for k, v in agg.items()),
        key=lambda x: -x["total_eur"],
    )
    return {"enseignes": enseignes}


@tool(
    description=(
        "Économies déjà réalisées (cumulées) et meilleures opportunités "
        "d'économie : produits qu'on aurait pu payer moins cher ailleurs. À "
        "utiliser pour les conseils d'économie."),
    parameters={
        "type": "object",
        "properties": {
            # Type permissif : certains modèles renvoient "5" (chaîne) au lieu
            # de 5 ; Python convertit ensuite via int(). Évite le rejet 400 de Groq.
            "limit": {"type": ["integer", "string"],
                      "description": "Nombre max d'opportunités à renvoyer (défaut 5)."},
        },
    },
)
def savings_summary(receipts: list[dict], limit: int = 5) -> dict:
    """Économies déjà réalisées (cumulées) + meilleures opportunités : pour
    chaque produit où une alternative moins chère existe dans une autre
    enseigne, le gain potentiel. Trié par économie décroissante."""
    total_savings = sum(float(r.get("total_savings") or 0) for r in receipts)
    opportunities = []
    for r in receipts:
        receipt = r.get("receipt") or {}
        ens = receipt.get("enseigne") or "?"
        date_str = receipt.get("date") or (r.get("scanned_at") or "")[:10]
        for comp in r.get("comparisons") or []:
            alts = comp.get("cheaper_alternatives") or []
            if not alts:
                continue
            best = alts[0]  # alternatives déjà triées par prix croissant
            saving = float(best.get("savings") or 0)
            if saving <= 0:
                continue
            opportunities.append({
                "produit": comp.get("scanned_name"),
                "prix_paye_eur": round(float(comp.get("scanned_price") or 0), 2),
                "enseigne_ticket": ens,
                "date": date_str,
                "alternative": best.get("name"),
                "enseigne_alternative": best.get("enseigne"),
                "prix_alternative_eur": round(float(best.get("price") or 0), 2),
                "economie_eur": round(saving, 2),
            })
    opportunities.sort(key=lambda o: -o["economie_eur"])
    return {
        "economies_cumulees_eur": round(total_savings, 2),
        "nb_opportunites": len(opportunities),
        "meilleures_opportunites": opportunities[: max(0, int(limit))],
    }


@tool(
    description=(
        "Classe les produits achetés selon une métrique. Choisis le bon "
        "`metric` selon la question : pour 'quel produit m'a coûté le plus "
        "cher', 'le produit/l'article le plus cher' -> 'prix_max' ; pour 'sur "
        "quoi je dépense le plus', 'mon plus gros poste de dépense' -> "
        "'total_cumule'."),
    parameters={
        "type": "object",
        "properties": {
            "metric": {"type": "string", "enum": ["total_cumule", "prix_max"],
                       "description": "'prix_max' = le produit dont UN achat a coûté le plus cher (pour 'le produit le plus cher'). 'total_cumule' = somme dépensée sur le produit ; un produit fréquent mais bon marché peut ressortir (pour 'sur quoi je dépense le plus')."},
            # Type permissif (cf. savings_summary) : "5" comme 5, converti par int().
            "limit": {"type": ["integer", "string"],
                      "description": "Nombre de produits à renvoyer (défaut 5)."},
        },
    },
)
def top_products(receipts: list[dict], metric: str = "total_cumule",
                 limit: int = 5) -> dict:
    """Classe les produits achetés — répond à « quel produit m'a coûté le
    plus cher ? », « sur quoi je dépense le plus ? ».

    Deux lectures possibles via `metric` :
      - "total_cumule" (défaut) : somme de tout ce que l'utilisateur a dépensé
        sur ce produit sur l'ensemble de l'historique. Un produit acheté
        souvent ressort, même s'il est peu cher à l'unité (ex. le pain).
      - "prix_max" : le produit dont UNE ligne de ticket a coûté le plus cher
        (le plus gros achat ponctuel, ex. une grosse lessive).

    Les produits sont regroupés par libellé exact. Renvoie le top `limit` avec,
    pour chacun, le total cumulé, le nombre d'achats et le prix de ligne max.
    """
    agg: dict[str, dict] = defaultdict(
        lambda: {"total": 0.0, "n": 0, "prix_max": 0.0})
    for r in receipts:
        for it in (r.get("receipt") or {}).get("items") or []:
            name = (it.get("name") or "").strip()
            if not name:
                continue
            price = float(it.get("price") or 0)
            a = agg[name]
            a["total"] += price
            a["n"] += 1
            a["prix_max"] = max(a["prix_max"], price)

    rows = [{"nom": k, "total_eur": round(v["total"], 2), "nb_achats": v["n"],
             "prix_ligne_max_eur": round(v["prix_max"], 2)}
            for k, v in agg.items()]
    key = "prix_ligne_max_eur" if metric == "prix_max" else "total_eur"
    rows.sort(key=lambda x: -x[key])
    return {"metric": metric, "produits": rows[: max(0, int(limit))]}


@tool(
    description=(
        "Compare les dépenses entre deux périodes. À utiliser pour 'est-ce que "
        "je dépense plus que le mois dernier', 'évolution de mes dépenses'. "
        "A = période récente, B = période de référence. Dates AAAA-MM-JJ."),
    parameters={
        "type": "object",
        "properties": {
            "periode_a_debut": {"type": "string", "description": "Début période A (AAAA-MM-JJ)."},
            "periode_a_fin": {"type": "string", "description": "Fin période A (AAAA-MM-JJ)."},
            "periode_b_debut": {"type": "string", "description": "Début période B (AAAA-MM-JJ)."},
            "periode_b_fin": {"type": "string", "description": "Fin période B (AAAA-MM-JJ)."},
        },
        "required": ["periode_a_debut", "periode_a_fin",
                     "periode_b_debut", "periode_b_fin"],
    },
)
def compare_periodes(receipts: list[dict],
                     periode_a_debut: str, periode_a_fin: str,
                     periode_b_debut: str, periode_b_fin: str) -> dict:
    """Compare les dépenses entre deux périodes — répond à « est-ce que je
    dépense plus que le mois dernier ? ».

    Calcule le total de chaque période et l'écart entre A et B :
      - `difference_eur` = total(A) - total(B),
      - `evolution_pct`  = évolution de A par rapport à B, en %,
      - `tendance`       = "hausse" / "baisse" / "stable".

    Convention : A = période récente (celle qui intéresse l'utilisateur),
    B = période de référence (la précédente). Dates au format AAAA-MM-JJ.
    """
    a = spending_summary(receipts, periode_a_debut, periode_a_fin)
    b = spending_summary(receipts, periode_b_debut, periode_b_fin)
    ta, tb = a["total_depense_eur"], b["total_depense_eur"]
    diff = round(ta - tb, 2)
    pct = round((ta - tb) / tb * 100, 1) if tb else None
    return {
        "periode_a": {"debut": periode_a_debut, "fin": periode_a_fin,
                      "total_eur": ta, "nb_tickets": a["nb_tickets"]},
        "periode_b": {"debut": periode_b_debut, "fin": periode_b_fin,
                      "total_eur": tb, "nb_tickets": b["nb_tickets"]},
        "difference_eur": diff,
        "evolution_pct": pct,
        "tendance": "hausse" if diff > 0 else "baisse" if diff < 0 else "stable",
    }


@tool(
    description=(
        "Où un produit a été le moins cher D'APRÈS L'HISTORIQUE de "
        "l'utilisateur (pas le catalogue des magasins). À utiliser pour 'où "
        "acheter tel produit au meilleur prix', 'où c'était le moins cher'. "
        "Limité aux produits déjà achetés."),
    parameters={
        "type": "object",
        "properties": {
            "product_query": {"type": "string",
                              "description": "Mot-clé du produit, ex. 'lait'."},
        },
        "required": ["product_query"],
    },
)
def cheapest_place_for_product(receipts: list[dict], product_query: str) -> dict:
    """Où un produit a été le moins cher — répond à « où acheter tel produit
    au meilleur prix ? », version HISTORIQUE.

    Important : ne consulte PAS le catalogue des magasins, seulement TES achats
    passés. La réponse est donc « d'après ce que tu as déjà payé, c'était le
    moins cher chez X » — fiable, mais limitée aux produits déjà achetés
    (et au moins une fois pour avoir une réponse).

    Pour chaque achat dont le nom matche `product_query`, calcule le prix par
    unité achetée (prix de ligne / quantité) puis regroupe par enseigne pour
    repérer le prix unitaire le plus bas par magasin. Compare des unités
    achetées (ex. par bouteille), pas au litre/kilo.
    """
    q = normalize_text(product_query or "", drop_quantity=True).strip()
    if not q:
        return {"product_query": product_query, "trouve": False,
                "message": "Requête vide."}

    by_enseigne: dict[str, dict] = defaultdict(
        lambda: {"prix_min": None, "nom": "", "date": ""})
    n = 0
    for r in receipts:
        receipt = r.get("receipt") or {}
        ens = (receipt.get("enseigne") or "Inconnu").strip() or "Inconnu"
        date_str = receipt.get("date") or (r.get("scanned_at") or "")[:10]
        for it in receipt.get("items") or []:
            name = it.get("name") or ""
            if q not in normalize_text(name, drop_quantity=True):
                continue
            qty = float(it.get("quantity") or 0) or 1.0
            unit = float(it.get("price") or 0) / qty
            n += 1
            e = by_enseigne[ens]
            if e["prix_min"] is None or unit < e["prix_min"]:
                e["prix_min"] = round(unit, 2)
                e["nom"] = name
                e["date"] = date_str

    if not n:
        return {"product_query": product_query, "trouve": False,
                "message": "Aucun achat de ce produit dans ton historique."}

    par_enseigne = sorted(
        ({"enseigne": k, "prix_par_unite_achetee_eur": v["prix_min"],
          "exemple_produit": v["nom"], "vu_le": v["date"]}
         for k, v in by_enseigne.items()),
        key=lambda x: x["prix_par_unite_achetee_eur"],
    )
    return {
        "product_query": product_query,
        "trouve": True,
        "nb_achats": n,
        "moins_cher_chez": par_enseigne[0],
        "par_enseigne": par_enseigne,
    }


# ─── Dérivés du registre (utilisés par backend/chat.py) ──────────────
# La liste exposée au LLM et le dispatch sont construits depuis le MÊME
# registre -> jamais de désynchronisation.
TOOL_SCHEMAS = [entry["schema"] for entry in _REGISTRY.values()]


def run_tool(name: str, args: dict, receipts: list[dict]) -> dict:
    """Exécute l'outil `name` avec `args` sur `receipts`. Ne lève jamais :
    une erreur est renvoyée comme résultat pour que le LLM puisse réagir."""
    entry = _REGISTRY.get(name)
    if entry is None:
        return {"error": f"Outil inconnu : {name}"}
    try:
        return entry["fn"](receipts, **(args or {}))
    except TypeError as e:
        return {"error": f"Arguments invalides pour {name} : {e}"}
    except Exception as e:  # garde-fou : jamais de crash de l'agent
        return {"error": f"Erreur dans {name} : {e}"}
