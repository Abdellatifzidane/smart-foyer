"""
Normalisation des noms de produits (cœur de la robustesse du matching)
=======================================================================
Les noms de produits arrivent sous trois formes très différentes :

  - **Ticket de caisse (OCR)** : MAJUSCULES, abrégé, parfois fautes OCR.
        "LAIT 1/2 ECR 1L", "CHOCO NOIR 100G", "P.Q TROPICO 6X1,5L"
  - **Catalogue Lidl / Monoprix (JSON-LD)** : mixte, avec marque + taille.
        "Lait demi-écrémé UHT 1 L - Lactel", "Tablette chocolat noir 100 g"

Pour comparer ces formes de façon fiable, on isole trois signaux distincts :

  1. **Texte sémantique** : nom normalisé (accents enlevés, abréviations
     développées, quantités retirées) → sert à l'embedding et au lexical.
  2. **Quantité** : (valeur, unité de base, multiplicateur) extraite et
     comparée séparément, pour ne JAMAIS présenter un 50 cl comme moins cher
     qu'un 1 L.
  3. **Catégorie** : famille grossière (Crémerie, Boissons…) pour bloquer les
     faux positifs entre familles éloignées.

Tout est pur stdlib (re, unicodedata) — testable sans dépendances lourdes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


# ─── Abréviations fréquentes sur les tickets FR ──────────────────────
# Développées AVANT le calcul du texte sémantique : un ticket écrit "ECR"
# et un catalogue écrit "écrémé" doivent se rejoindre.
_ABBREVIATIONS = {
    "1/2": "demi",
    "ecr": "ecreme",
    "ecre": "ecreme",
    "demi-ecr": "demi ecreme",
    "choco": "chocolat",
    "choco.": "chocolat",
    "from": "fromage",
    "frmg": "fromage",
    "from.": "fromage",
    "yt": "yaourt",
    "yaou": "yaourt",
    "yog": "yaourt",
    "cfe": "cafe",
    "caf": "cafe",
    "bisc": "biscuit",
    "biscu": "biscuit",
    "pqt": "paquet",
    "pq": "paquet",
    "paq": "paquet",
    "ptt": "petit",
    "pt": "petit",
    "gd": "grand",
    "gde": "grande",
    "nat": "nature",
    "natu": "nature",
    "sucr": "sucre",
    "ss": "sans",
    "av": "avec",
    "ble": "ble",
    "cereal": "cereales",
    "cerea": "cereales",
    "compl": "complet",
    "compl.": "complet",
    "tom": "tomate",
    "tomat": "tomate",
    "ldl": "lidl",
    "bio": "bio",
    "alleg": "allege",
    "all.": "allege",
    "surg": "surgele",
    "surgel": "surgele",
    "conf": "confiture",
    "fraich": "fraiche",
    "fr.": "frais",
    "lt": "lait",
    "jamb": "jambon",
    "jamb.": "jambon",
    "sauc": "saucisse",
    "poul": "poulet",
    "esc": "escalope",
    "filet": "filet",
    "ananas": "ananas",
    "orang": "orange",
    "ban": "banane",
    "pom": "pomme",
    "crm": "creme",
    "beur": "beurre",
    "beu": "beurre",
    "min": "mineral",
    "miner": "minerale",
    "gaz": "gazeuse",
    "natur": "nature",
    "emm": "emmental",
    "rape": "rape",
    "tranch": "tranche",
}

# Mots vides / unités à ignorer dans le sac de mots lexical : ils ne portent
# aucune information discriminante sur l'identité du produit.
STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "au", "aux", "un", "une",
    "et", "en", "a", "l", "d", "s", "ou", "pour", "par", "sur", "the",
    "kg", "kgs", "g", "gr", "grammes", "ml", "cl", "l", "lt", "litre",
    "litres", "cls", "mls", "pce", "pieces", "piece", "pcs",
    "pack", "lot", "x", "qty", "qte", "quantite", "ref", "tva",
    "eur", "euro", "euros", "uht", "upc", "ean",
}


# ─── Extraction de quantité ──────────────────────────────────────────
# On ramène tout vers une unité de base : volume → ml, masse → g, sinon
# "unit" (compte de pièces). Un multiplicateur gère "6 x 1,5 L".

_UNIT_TO_BASE = {
    "l": ("ml", 1000.0),
    "litre": ("ml", 1000.0),
    "litres": ("ml", 1000.0),
    "cl": ("ml", 10.0),
    "ml": ("ml", 1.0),
    "kg": ("g", 1000.0),
    "kgs": ("g", 1000.0),
    "g": ("g", 1.0),
    "gr": ("g", 1.0),
    "grammes": ("g", 1.0),
    "mg": ("g", 0.001),
}

# "6x1,5l", "6 x 1.5 l", "lot de 4", "pack de 6", "x6", "750 g", "1,5l"
_MULT_RE = re.compile(r"(?:(?:lot|pack|paquet)\s*(?:de)?\s*|x\s*)(\d{1,2})\b", re.I)
_MULT_PREFIX_RE = re.compile(r"\b(\d{1,2})\s*[x×]\s*(?=\d)", re.I)
_QTY_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kgs?|kg|mg|gr?|grammes|cl|ml|litres?|l)\b",
    re.I,
)


@dataclass(frozen=True)
class Quantity:
    """Quantité normalisée d'un produit.

    base_value : contenu total exprimé dans l'unité de base (ml ou g).
                 Pour "6 x 1,5 L" → 9000.0 ml.
    base_unit  : "ml", "g" ou "unit".
    multiplier : nombre d'unités de conditionnement (6 pour un pack de 6).
    """
    base_value: float
    base_unit: str
    multiplier: int = 1

    @property
    def is_known(self) -> bool:
        return self.base_value > 0 and self.base_unit in ("ml", "g")


def extract_quantity(text: str) -> Quantity:
    """Extrait la quantité totale d'un libellé produit.

    Renvoie une Quantity(base_value=0, base_unit="unit") si rien n'est trouvé.
    """
    if not text:
        return Quantity(0.0, "unit")
    s = text.lower().replace(" ", " ")

    multiplier = 1
    m = _MULT_PREFIX_RE.search(s) or _MULT_RE.search(s)
    if m:
        try:
            multiplier = max(1, int(m.group(1)))
        except ValueError:
            multiplier = 1

    qm = _QTY_RE.search(s)
    if not qm:
        return Quantity(0.0, "unit", multiplier)

    try:
        value = float(qm.group(1).replace(",", "."))
    except ValueError:
        return Quantity(0.0, "unit", multiplier)

    unit = qm.group(2).lower()
    base_unit, factor = _UNIT_TO_BASE.get(unit, (None, None))
    if base_unit is None:
        return Quantity(0.0, "unit", multiplier)

    base_value = value * factor * multiplier
    return Quantity(base_value=base_value, base_unit=base_unit, multiplier=multiplier)


def quantity_compatible(a: Quantity, b: Quantity, tol: float = 0.18) -> bool:
    """Deux quantités sont comparables si même nature (volume/masse) et
    contenu total à ±`tol` (18 % par défaut).

    Si l'une des deux est inconnue, on reste permissif (True) — on ne veut pas
    écarter un bon match juste parce que le ticket n'imprime pas la taille.
    """
    if not a.is_known or not b.is_known:
        return True
    if a.base_unit != b.base_unit:
        return False
    hi = max(a.base_value, b.base_value)
    lo = min(a.base_value, b.base_value)
    if hi <= 0:
        return True
    return (hi - lo) / hi <= tol


# ─── Prix au litre / au kilo ─────────────────────────────────────────

def price_per_base_unit(price: float, qty: Quantity) -> float | None:
    """Prix ramené à l'unité de base (€ / litre ou € / kg) si la quantité est
    connue, sinon None. Permet une comparaison « moins cher » équitable.
    """
    if not qty.is_known or price <= 0 or qty.base_value <= 0:
        return None
    if qty.base_unit == "ml":
        return price / (qty.base_value / 1000.0)  # € par litre
    if qty.base_unit == "g":
        return price / (qty.base_value / 1000.0)  # € par kg
    return None


# ─── Catégorie grossière (blocking) ──────────────────────────────────
_CATEGORY_KEYWORDS = {
    "Boulangerie": ("pain", "baguette", "viennoiserie", "brioche", "croissant", "mie"),
    "Cremerie": ("lait", "yaourt", "fromage", "beurre", "creme", "emmental",
                 "camembert", "mozzarella", "oeuf", "oeufs"),
    "Boissons": ("eau", "jus", "soda", "coca", "vin", "biere", "biere",
                 "sirop", "limonade", "the", "infusion", "boisson"),
    "Cafe": ("cafe", "expresso", "capsule", "dosette"),
    "Epicerie sucree": ("chocolat", "bonbon", "biscuit", "gateau", "confiture",
                         "miel", "cereales", "compote", "nutella", "barre"),
    "Epicerie salee": ("pates", "riz", "semoule", "farine", "huile", "sauce",
                       "conserve", "tomate", "concentre", "soupe", "lentille"),
    "Charcuterie": ("jambon", "saucisse", "lardon", "pate", "chorizo", "saucisson",
                    "bacon"),
    "Viande/Poisson": ("poulet", "boeuf", "porc", "steak", "escalope", "filet",
                       "saumon", "thon", "poisson", "viande", "dinde"),
    "Fruits/Legumes": ("pomme", "banane", "tomate", "salade", "carotte", "fruit",
                       "legume", "orange", "fraise", "courgette", "oignon",
                       "avocat", "ananas", "citron", "poire"),
    "Surgele": ("surgele", "glace", "frites"),
    "Hygiene": ("desinfect", "savon", "dentifrice", "shampoing", "gel",
                "deodorant", "rasoir", "coton", "papier toilette", "mouchoir"),
    "Entretien": ("lessive", "liquide vaisselle", "nettoyant", "javel",
                  "adoucissant", "eponge", "sac poubelle"),
    "Bebe": ("couche", "petit pot", "lait infantile"),
    "Animaux": ("croquette", "chat", "chien", "litiere"),
}


def infer_category(text: str) -> str:
    """Famille grossière du produit, "" si indéterminée.

    Le texte est normalisé (abréviations développées) afin que "CHOCO" ou
    "CFE" d'un ticket tombent dans la même famille que "chocolat"/"café".
    """
    if not text:
        return ""
    s = normalize_text(text, drop_quantity=True)
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(kw in s for kw in kws):
            return cat
    return ""


# ─── Normalisation texte ─────────────────────────────────────────────

def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_text(name: str, *, drop_quantity: bool = True) -> str:
    """Forme canonique d'un nom de produit pour comparaison.

    Étapes : retrait du tag TVA final, minuscule, suppression des accents,
    développement des abréviations, retrait optionnel des quantités, nettoyage
    de la ponctuation.
    """
    if not name:
        return ""
    s = name.strip()
    # Retire un tag TVA final ("Pain complet A" → "Pain complet")
    s = re.sub(r"\s+[A-Z]$", "", s)
    s = s.lower()
    s = strip_accents(s)
    # Fractions courantes AVANT le nettoyage de ponctuation ("1/2 ecr" → "demi")
    s = re.sub(r"\b1\s*/\s*2\b", " demi ", s)
    s = re.sub(r"\b1\s*/\s*4\b", " quart ", s)
    # Désolidarise les unités collées aux nombres ("1l" → "1 l", "500g" → "500 g")
    s = re.sub(r"(\d)([a-z]{1,3})\b", r"\1 \2", s)
    # Sépare le multiplicateur ("6x1.5" → "6 x 1.5")
    s = re.sub(r"(\d)\s*[x×]\s*(\d)", r"\1 x \2", s)
    if drop_quantity:
        # Retire les quantités (volume/masse) — comparées séparément
        s = _QTY_RE.sub(" ", s)
        s = re.sub(r"\b\d+\s*[x×]\b", " ", s)
    # Ponctuation → espace
    s = re.sub(r"[^a-z0-9\s%]+", " ", s)
    # Développe les abréviations token par token
    tokens = [_ABBREVIATIONS.get(t, t) for t in s.split()]
    s = " ".join(tokens)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def content_tokens(normalized: str) -> set[str]:
    """Sac de mots discriminants (sans stopwords/unités ni nombres purs)."""
    if not normalized:
        return set()
    toks = {t for t in normalized.split() if t and t not in STOPWORDS}
    return {t for t in toks if not t.isdigit() and len(t) > 1}


def product_text(name: str, brand: str = "") -> str:
    """Texte combiné (nom + marque) brut, lisible."""
    name = (name or "").strip()
    brand = (brand or "").strip()
    if brand and brand.lower() not in name.lower():
        return f"{name} {brand}".strip()
    return name


def embed_text(name: str, brand: str = "") -> str:
    """Texte normalisé servant d'entrée à l'embedding (côté ticket ET côté
    catalogue, pour aligner les abréviations type "ECR" → "ecreme"). On garde
    la quantité ici (indice faible utile), le filtrage dur se fait à part.
    """
    base = normalize_text(name, drop_quantity=False)
    if brand:
        b = normalize_text(brand, drop_quantity=False)
        if b and b not in base:
            base = f"{base} {b}".strip()
    return base
