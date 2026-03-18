# Guide d'utilisation des Scrapers SmartFoyer

## Prerequis

- Python 3.11+
- Un terminal Linux/WSL

## Installation

```bash
cd ~/smart-foyer

# Creer et activer le venv
python3 -m venv .venv
source .venv/bin/activate

# Installer les dependances
pip install -r requirements.txt
```

## Structure des fichiers

```
scrapers/
├── config.py              # Configuration (rate limit, timeout, logs)
├── models.py              # Dataclass Product + export JSON
├── scraper_monoprix.py    # Scraper courses.monoprix.fr (26 000+ produits)
├── scraper_lidl.py        # Scraper lidl.fr (10 000+ produits)
├── scraper_carrefour.py   # Placeholder (bloque par anti-bot)
└── run_all.py             # Lance Monoprix + Lidl et fusionne les resultats
```

## Lancer les scrapers

Tous les scripts se lancent depuis le dossier `scrapers/` :

```bash
cd ~/smart-foyer/scrapers
```

### Monoprix

Source : `courses.monoprix.fr` (~26 000 produits alimentaires)

```bash
# Scraper 20 produits
python scraper_monoprix.py --max-products 20

# Filtrer par mot-cle dans l'URL (lait, cafe, chocolat, biere, fromage...)
python scraper_monoprix.py --category "cafe" --max-products 10

# Tout scraper (long ~22h a 3s/requete)
python scraper_monoprix.py
```

### Lidl

Source : `lidl.fr` (~10 000 produits)

```bash
# Scraper 20 produits
python scraper_lidl.py --max-products 20

# Filtrer par mot-cle
python scraper_lidl.py --category "fromage" --max-products 10

# Tout scraper (long ~8h a 3s/requete)
python scraper_lidl.py
```

### Lancer tout

```bash
# Monoprix + Lidl, 50 produits chacun
python run_all.py --max-products 50

# Tout sans limite
python run_all.py

# Un seul retailer
python run_all.py --retailers monoprix --max-products 100
```

## Fichiers de sortie

Les resultats sont dans `scrapers/data/` :

| Fichier | Contenu |
|---------|---------|
| `monoprix_products.json` | Produits Monoprix |
| `lidl_products.json` | Produits Lidl |
| `all_products_YYYYMMDD_HHMMSS.json` | Fusion de tous les retailers (via run_all.py) |

### Format JSON

```json
{
  "name": "Ducros Herbes de Provence 100g",
  "price": 1.75,
  "currency": "EUR",
  "unit_price": "100g",
  "brand": "Ducros",
  "image_url": "https://courses.monoprix.fr/images-v3/.../500x500.jpg",
  "product_url": "https://courses.monoprix.fr/products/ducros-herbes.../MPX_10763",
  "enseigne": "Monoprix",
  "category": "ducros-herbes-de-provence-100g",
  "sku": "MPX_10763",
  "scraped_at": "2026-03-18T14:23:30.495975+00:00"
}
```

## Configuration

Editer `scrapers/config.py` pour modifier :

| Parametre | Valeur par defaut | Description |
|-----------|-------------------|-------------|
| `CRAWL_DELAY` | `3` | Secondes entre chaque requete |
| `REQUEST_TIMEOUT` | `30` | Timeout par requete (secondes) |
| `OUTPUT_DIR` | `"data"` | Dossier de sortie des JSON |
| `LOG_LEVEL` | `logging.INFO` | Niveau de log (DEBUG pour plus de details) |

## Mots-cles utiles pour le filtre `--category`

Le filtre cherche dans l'URL du produit. Exemples :

| Mot-cle | Exemples de produits |
|---------|---------------------|
| `lait` | Lait, chocolat au lait, pains au lait |
| `cafe` | Cafe en grains, capsules, soluble |
| `fromage` | Fromage blanc, fromage rape, brebis |
| `chocolat` | Tablettes, bonbons, pate a tartiner |
| `biere` | Bieres blondes, IPA, sans alcool |
| `eau` | Eau minerale, gazeuse |
| `pate` | Pates, pate a pizza, pate feuilletee |
| `yaourt` | Yaourts natures, fruits, grecs |
| `bio` | Tous les produits bio (Monoprix uniquement) |

## Notes techniques

- **Rate limiting** : 3 secondes entre chaque requete pour respecter les serveurs
- **cloudscraper** : Contourne la protection anti-bot basique (Monoprix, Lidl)
- **JSON-LD** : Les deux sites exposent les donnees produits en schema.org/Product
- **Sitemap** : Decouverte des URLs via les sitemaps XML des sites
- **Carrefour** : Bloque (anti-bot agressif + rendu 100% JS). Placeholder en attente d'alternative

## Estimation des temps de scraping complet

| Retailer | Produits | Temps estime (CRAWL_DELAY=3s) |
|----------|----------|-------------------------------|
| Monoprix | ~26 000 | ~22 heures |
| Lidl | ~10 000 | ~8 heures |

Pour accelerer, reduire `CRAWL_DELAY` dans `config.py` (minimum recommande : 1s).
