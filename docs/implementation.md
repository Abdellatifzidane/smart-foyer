# SmartFoyer — Documentation d'implémentation

Ce document décrit **ce qui a été développé** dans le projet SmartFoyer, étape par étape. L'objectif : qu'une personne qui découvre le projet comprenne directement la chaîne complète, du ticket photographié jusqu'à la comparaison de prix.

---

## Vue d'ensemble

SmartFoyer transforme une **photo de ticket de caisse** en données structurées exploitables, puis compare les prix entre enseignes. Le pipeline est découpé en 4 modules indépendants :

```
Photo ticket
    │
    ▼
[ 1. OCR ]            → texte brut extrait
    │
    ▼
[ 2. NER (LLM) ]      → données structurées (enseigne, total, produits…)
    │
    ▼
[ 3. Matching ]       → comparaison avec le catalogue scrapé
    │
    ▼
Résultat affiché dans l'app
```

L'utilisateur final accède à tout ça via :

```
[ 4. Backend FastAPI ] ⇄ [ 5. App Flutter Web ]
```

---

## Étape 1 — OCR (extraction du texte)

### C'est quoi ?

L'**OCR** (Optical Character Recognition) lit une image et en extrait le texte. C'est la première brique : sans le texte du ticket, on ne peut rien faire.

### Quoi utilisé : **PaddleOCR**

[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) est une bibliothèque open source de Baidu basée sur du deep learning. On l'a choisie pour :

- Excellente qualité (95% de confiance sur le dataset SROIE2019)
- **Support natif du français et de l'anglais**
- Détection automatique de l'orientation (ticket photographié de travers)
- Modèles téléchargés automatiquement la première fois

### Comment c'est implémenté

Un wrapper Python encapsule PaddleOCR pour exposer une API simple :

```python
ocr = ReceiptOCR(lang="fr")
result = ocr.extract("ticket.jpg")
print(result.text)             # texte brut, ligne par ligne
print(result.avg_confidence)   # confiance moyenne (0–1)
```

En sortie, on obtient un objet `OCRResult` qui contient :
- `text` : le texte concaténé
- `lines` : la liste des lignes détectées avec leur score de confiance et leur position (bounding box)

### Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `ocr/__init__.py` | Marqueur de module Python |
| `ocr/paddle_ocr.py` | Classe `ReceiptOCR` + dataclasses `OCRResult`, `OCRLine` |
| `ocr/test_sroie.py` | Script CLI : teste l'OCR sur le dataset SROIE2019 et compare au ground truth |

### Comment tester

```bash
python -m ocr.test_sroie --n 5
```

---

## Étape 2 — NER (extraction structurée via LLM)

### C'est quoi ?

Le texte brut de l'OCR n'est pas exploitable tel quel. Il faut **extraire les entités** : nom de l'enseigne, date, total, produits, prix, quantités. C'est ce qu'on appelle le **NER** (Named Entity Recognition).

### Quoi utilisé : **Ollama + llama3.1:8b**

Plutôt qu'un modèle NER classique (qui demande des centaines de tickets annotés à la main pour l'entraînement), on utilise un **LLM en zero-shot** :

- **Ollama** : moteur d'exécution de LLMs **en local** (gratuit, données privées, pas d'appel à une API cloud).
- **llama3.1:8b** : LLM open source de Meta, 8 milliards de paramètres, ~5 Go sur disque. Tourne en local sur CPU.

### Comment c'est implémenté

On envoie le texte OCR à llama3.1 avec un **prompt structuré** qui demande explicitement un JSON. Ollama supporte un mode `format="json"` qui force le modèle à produire du JSON valide. On parse ensuite ce JSON en objet `Receipt`.

**Schéma JSON renvoyé par le LLM** :

```json
{
  "enseigne": "Intermarché",
  "date": "2025-05-17",
  "total": 22.03,
  "items": [
    { "name": "PANZANI PENNE RIGATE", "price": 1.24, "quantity": 1 },
    { "name": "OEUFS BIO X4", "price": 2.35, "quantity": 1 }
  ]
}
```

### Pourquoi cette approche est extensible

Pour **ajouter un champ** (ex: adresse, mode de paiement, catégorie produit), il suffit de :

1. Ajouter une ligne dans `ner/models.py` :
   ```python
   address: str = ""
   ```
2. Ajouter une ligne dans `ner/prompt.py` :
   ```
   "address": "Store address. String."
   ```

Le pipeline le récupère automatiquement.

### Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `ner/__init__.py` | Marqueur de module |
| `ner/models.py` | Dataclasses `Receipt` et `LineItem` (un seul endroit pour ajouter des champs) |
| `ner/prompt.py` | Prompt système + schéma JSON envoyé au LLM |
| `ner/extractor.py` | Classe `OllamaExtractor` : appelle Ollama et parse le JSON |
| `ner/test_sroie.py` | Pipeline complet OCR → NER sur SROIE2019, avec comparaison aux entités ground truth |

### Comment tester

```bash
ollama serve &           # démarre le service Ollama
ollama pull llama3.1:8b  # télécharge le modèle (une seule fois, ~5 Go)
python -m ner.test_sroie --n 3
```

---

## Étape 3 — Matching sémantique (FAISS + embeddings)

### C'est quoi ?

Le ticket dit `PANZANI PENNE RIGATE`. Le catalogue scrapé dit `Panzani Penne Rigate Pâtes 500g`. Ce sont **les mêmes pâtes**, mais le texte ne match pas exactement. Il faut une comparaison qui comprend le **sens**, pas juste les caractères.

C'est le rôle du **matching sémantique**.

### Quoi utilisé : **sentence-transformers + FAISS**

- **sentence-transformers** (modèle `paraphrase-multilingual-MiniLM-L12-v2`) : convertit chaque texte en un **vecteur de 384 nombres** qui capture son sens. Deux textes au sens proche → vecteurs proches.
- **FAISS** (Facebook AI Similarity Search) : stocke des milliers de vecteurs et trouve les plus proches **en quelques millisecondes**.

### Comment ça fonctionne concrètement

```
1. Pour chaque produit scrapé du catalogue :
   "Panzani Penne Rigate 500g" → vecteur [0.12, -0.34, 0.78, ...]

2. On stocke tous ces vecteurs dans un index FAISS (sur disque).

3. Au moment du scan :
   "PANZANI PENNE RIGATE" → vecteur [0.13, -0.32, 0.77, ...]

4. FAISS retourne les 5 produits du catalogue dont le vecteur est le plus proche.

5. Pour chaque match, on récupère le prix et l'enseigne → on peut comparer.
```

### Comment c'est implémenté

L'index FAISS est **construit une seule fois** à partir des fichiers JSON produits par les scrapers, puis sauvegardé. Au runtime, on le charge en mémoire et on l'interroge.

```python
# Construction (une fois)
index = ProductIndex.build(products, embedder)
index.save("data/index/catalog")

# Utilisation (chaque scan)
matcher = Matcher.from_disk("data/index/catalog")
comparisons = matcher.compare(receipt)
```

### Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `matching/__init__.py` | Marqueur de module |
| `matching/embeddings.py` | Classe `Embedder` (wrapper sentence-transformers) |
| `matching/index.py` | Classe `ProductIndex` : construction, sauvegarde, chargement, recherche FAISS |
| `matching/matcher.py` | Classe `Matcher` : compare un `Receipt` complet et propose des alternatives moins chères |
| `matching/build_index.py` | CLI : construit l'index depuis les fichiers `*_products.json` des scrapers |
| `matching/test_matching.py` | CLI : teste l'index avec des requêtes type ticket |

### Comment tester

```bash
# 1. Scraper des produits (si pas déjà fait)
python scrapers/scraper_monoprix.py --max-products 200
python scrapers/scraper_lidl.py --max-products 200

# 2. Construire l'index
python -m matching.build_index --input scrapers/data

# 3. Tester
python -m matching.test_matching
```

---

## Étape 4 — Backend HTTP (FastAPI)

### Pourquoi un backend ?

Le pipeline Python (OCR + NER + Matching) tourne **localement sur la machine**. Pour qu'une app mobile/web puisse l'utiliser, il faut une **API HTTP** qui expose le pipeline.

### Quoi utilisé : **FastAPI + uvicorn**

- **FastAPI** : framework HTTP Python moderne, simple, performant, génère de la doc automatique.
- **uvicorn** : serveur ASGI qui exécute FastAPI.

### Endpoints exposés

| Méthode | URL | Rôle |
|---|---|---|
| `GET`  | `/` | Health check (le backend est-il vivant ?) |
| `GET`  | `/catalog/stats` | Nombre de produits dans l'index, ventilation par enseigne |
| `POST` | `/scan` | Upload d'une image → renvoie le pipeline complet en JSON |

Le endpoint `/scan` enchaîne :
1. Redimensionnement de l'image si elle est trop grande (limite RAM)
2. OCR via PaddleOCR
3. NER via Ollama
4. Matching via FAISS
5. Retour d'un JSON consolidé

### Particularités

- **CORS activé** : l'app Flutter Web peut appeler le backend depuis n'importe quelle origine.
- **Lazy-loading des modèles** : OCR, embedder et FAISS sont chargés au premier appel, pas au démarrage → démarrage plus rapide.
- **Singletons** : les modèles restent en mémoire entre les requêtes.

### Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `backend/__init__.py` | Marqueur de module |
| `backend/main.py` | App FastAPI avec tous les endpoints |

### Comment lancer

```bash
cd /Users/issomeli/smart-foyer
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

---

## Étape 5 — Application mobile Flutter (web)

### Pourquoi Flutter ?

Flutter permet de viser **iOS + Android + Web** avec une seule base de code. Pour la phase de test on a généré la version **web** (pas besoin de simulateur iOS/Android).

### Architecture de l'app

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ HomeScreen   │──>│ ScanScreen    │──>│ ResultsScreen │
│ "Scanner"    │   │ Upload + load │   │ Receipt + cmp │
└──────────────┘    └──────────────┘    └──────────────┘
        │                  │                    │
        └──────────────────┼────────────────────┘
                           ▼
                    ┌──────────────┐
                    │ ApiClient    │  → HTTP vers FastAPI
                    │ Models       │  → Mapping JSON ↔ Dart
                    └──────────────┘
```

### Écrans

1. **HomeScreen** : page d'accueil, vérifie que le backend est joignable, bouton "Scanner un ticket".
2. **ScanScreen** : sélecteur de fichiers (file_picker), prévisualisation de l'image, bouton "Analyser le ticket", indicateur de chargement (20–40s).
3. **ResultsScreen** : affiche
   - L'en-tête du ticket (enseigne, date, total, confiance OCR)
   - Une bannière verte avec les économies possibles
   - Pour chaque produit : nom, prix, et liste d'alternatives moins chères

### Packages Dart utilisés

- `http` — requêtes HTTP vers le backend
- `file_picker` — sélection d'image (compatible web, iOS, Android)

### Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `smart_foyer_app/pubspec.yaml` | Dépendances Dart |
| `smart_foyer_app/lib/main.dart` | Entrée + thème |
| `smart_foyer_app/lib/api/api_client.dart` | Client HTTP vers le backend |
| `smart_foyer_app/lib/api/models.dart` | Modèles Dart (`Receipt`, `LineItem`, `ItemComparison`, …) |
| `smart_foyer_app/lib/screens/home_screen.dart` | Écran d'accueil |
| `smart_foyer_app/lib/screens/scan_screen.dart` | Écran d'upload |
| `smart_foyer_app/lib/screens/results_screen.dart` | Écran de résultats |

### Comment lancer l'app

```bash
cd /Users/issomeli/smart-foyer/smart_foyer_app
flutter run -d web-server --web-hostname=127.0.0.1 --web-port=5173
```

Ouvrir ensuite `http://127.0.0.1:5173` dans le navigateur.

---

## Comment tout faire tourner ensemble

Trois services doivent tourner en parallèle, dans **3 terminaux séparés** :

**Terminal 1 — Ollama** (le LLM)
```bash
ollama serve
```

**Terminal 2 — Backend Python**
```bash
cd /Users/issomeli/smart-foyer
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Terminal 3 — App Flutter Web**
```bash
cd /Users/issomeli/smart-foyer/smart_foyer_app
flutter run -d web-server --web-hostname=127.0.0.1 --web-port=5173
```

Puis ouvrir `http://127.0.0.1:5173` dans le navigateur.

---

## Récapitulatif des modules ajoutés

```
smart-foyer/
├── ocr/                    ← Étape 1 : extraction de texte (PaddleOCR)
├── ner/                    ← Étape 2 : extraction structurée (Ollama LLM)
├── matching/               ← Étape 3 : comparaison sémantique (FAISS)
├── backend/                ← Étape 4 : API HTTP (FastAPI)
├── smart_foyer_app/        ← Étape 5 : app mobile/web (Flutter)
├── scrapers/               ← (déjà existant) scraping Monoprix + Lidl
├── data/
│   ├── ocr_results/        ← Sorties des tests OCR
│   ├── ner_results/        ← Sorties des tests NER
│   └── index/              ← Index FAISS sauvegardé
└── docs/
    └── implementation.md   ← Ce document
```

---

## Limites actuelles et pistes d'amélioration

### Le matching donne parfois des résultats absurdes

C'est la **principale limite du POC actuel**. Exemple constaté : un ticket Intermarché avec des pâtes Panzani matche avec des "Chaussures homme" chez Lidl.

**Pourquoi ?**

1. **Le catalogue scrapé est trop petit.** Seulement **200 produits au total** (100 Monoprix + 100 Lidl). Pour matcher correctement, il faudrait plusieurs milliers de produits par enseigne.
2. **Le catalogue est pollué par du non-alimentaire.** Lidl mélange alimentaire et hard discount (chaussures, valises, coussins, électroménager…). Sans filtre, ces produits remontent dans les comparaisons.
3. **Quand le produit recherché n'existe pas dans le catalogue**, FAISS retourne quand même le "moins pire" résultat, qui peut être très éloigné sémantiquement.

**Comment l'améliorer** :

```bash
# Scraper beaucoup plus de produits (plusieurs milliers par enseigne)
python scrapers/scraper_monoprix.py --max-products 5000
python scrapers/scraper_lidl.py --max-products 5000

# Reconstruire l'index
python -m matching.build_index --input scrapers/data
```

Et idéalement :
- Filtrer les produits Lidl pour ne garder que l'alimentaire
- Ajouter un scraper pour Intermarché et Carrefour (les enseignes les plus présentes sur les vrais tickets)
- Ajouter une catégorisation des produits pour ne comparer que ce qui est comparable (pâtes avec pâtes, lait avec lait…)

**À retenir** : le pipeline est techniquement fonctionnel. La qualité des résultats dépend de la **quantité et qualité des données** dans le catalogue. C'est un problème de données, pas de code.
