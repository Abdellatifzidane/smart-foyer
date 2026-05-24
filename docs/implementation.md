# SmartFoyer — Documentation technique de A à Z

Ce document décrit **l'intégralité** de ce qui a été développé dans le projet SmartFoyer, comment chaque pièce fonctionne, comment la lancer, et ce qu'il reste à faire pour atteindre la vision finale (app mobile native + déploiement GCP).

Cible : un développeur qui veut reprendre le projet là où on l'a laissé.

---

## 1. Vision et architecture cible

SmartFoyer est une application mobile qui permet de :
1. Scanner un ticket de caisse (photo)
2. Extraire automatiquement les produits, prix, enseigne, total
3. Comparer les prix avec un catalogue scrapé d'autres enseignes
4. Conserver l'historique des courses
5. Interroger un agent IA conversationnel sur ses dépenses

L'architecture cible (GCP) est décrite dans le [README principal](../README.md). Le POC actuel implémente la même logique en local.

```
┌──────────────┐     ┌──────────────────────────────────┐
│ App Flutter  │ ⇄ │  Backend FastAPI (local)         │
│ Web / Mobile │     │  ┌────────────┐ ┌─────────────┐ │
└──────────────┘     │  │ OCR        │ │ NER (LLM)   │ │
                     │  └────────────┘ └─────────────┘ │
                     │  ┌────────────┐ ┌─────────────┐ │
                     │  │ Matching   │ │ Chat RAG    │ │
                     │  └────────────┘ └─────────────┘ │
                     │  ┌────────────┐ ┌─────────────┐ │
                     │  │ Persistance│ │ Catalogue   │ │
                     │  │ JSON       │ │ FAISS       │ │
                     │  └────────────┘ └─────────────┘ │
                     └──────────────────────────────────┘
                                  │
                  ┌────────────────┴───────────────┐
                  │ Sources externes                │
                  │  - Scrapers Monoprix / Lidl     │
                  │  - LLM Groq (llama-3.3-70b)     │
                  └─────────────────────────────────┘
```

---

## 2. Arborescence du projet

```
smart-foyer/
├── README.md                  ← Pitch projet + roadmap initiale
├── requirements.txt           ← Dépendances Python
│
├── scrapers/                  ← Récupération du catalogue produits
│   ├── config.py              ← USER_AGENT, CRAWL_DELAY, OUTPUT_DIR
│   ├── filters.py             ← Liste de mots-clés non-alimentaires
│   ├── models.py              ← Dataclass Product
│   ├── scraper_monoprix.py    ← Scraping courses.monoprix.fr (JSON-LD)
│   ├── scraper_lidl.py        ← Scraping lidl.fr (sitemap gzip + JSON-LD)
│   └── run_all.py             ← Orchestrateur multi-scrapers
│
├── ocr/                       ← Extraction de texte depuis l'image
│   ├── paddle_ocr.py          ← Wrapper PaddleOCR 3.x
│   └── test_sroie.py          ← Évaluation sur le dataset SROIE2019
│
├── ner/                       ← Extraction structurée via LLM
│   ├── models.py              ← Receipt + LineItem (extensible)
│   ├── prompt.py              ← Prompt système + schéma JSON (exhaustif)
│   ├── extractor.py           ← Wrapper Groq (llama-3.3-70b-versatile)
│   └── test_sroie.py          ← Pipeline OCR + NER sur SROIE2019
│
├── matching/                  ← Comparaison sémantique des produits
│   ├── embeddings.py          ← sentence-transformers (multilingue)
│   ├── index.py               ← Index FAISS (build, save, load, search)
│   ├── matcher.py             ← Compare un Receipt au catalogue
│   ├── build_index.py         ← CLI : construit l'index depuis data/*.json
│   ├── test_matching.py       ← Test avec requêtes exemples
│   └── test_intermarche.py    ← Test sur un ticket Intermarché réel
│
├── backend/                   ← API HTTP (FastAPI)
│   ├── main.py                ← Endpoints : /scan, /history, /chat, ...
│   ├── chat.py                ← Agent RAG : contexte + appel LLM
│   └── seed_demo.py           ← Génère des tickets factices pour démo
│
├── smart_foyer_app/           ← App Flutter (Web pour l'instant)
│   ├── pubspec.yaml
│   └── lib/
│       ├── main.dart                 ← ErrorBoundary global + theme
│       ├── api/
│       │   ├── api_client.dart       ← Client HTTP + ApiException + timeouts
│       │   └── models.dart           ← Modèles Dart (Receipt, ScanResult...)
│       └── screens/
│           ├── home_screen.dart      ← Accueil + 5 boutons + retry backend
│           ├── scan_screen.dart      ← Upload image + analyse
│           ├── results_screen.dart   ← Photo originale + ticket + comparaisons + savings
│           ├── history_screen.dart   ← Liste des tickets (thumbnails) + stats
│           ├── analytics_screen.dart ← Graphiques semaine/mois/catégorie/enseigne
│           ├── chat_screen.dart      ← Agent IA conversationnel
│           └── admin_screen.dart     ← CRUD catalogue + jobs scraping
│
├── data/                      ← Données générées (gitignored)
│   ├── monoprix_products.json    ← ~2800 produits scrapés
│   ├── lidl_products.json        ← ~3200 produits scrapés (food only)
│   ├── index/                    ← Index FAISS + métadonnées
│   ├── receipts/                 ← Tickets scannés (JSON)
│   │   └── images/               ← Photos originales (JPEG/PNG) {id}.jpg
│   ├── ocr_results/              ← Sorties des tests OCR
│   └── ner_results/              ← Sorties des tests NER
│
└── docs/
    ├── implementation.md         ← Ce document
    ├── guide-scrapers.md
    └── scraping-feasibility.md
```

---

## 3. Étape par étape : ce qui a été construit

### 3.1 Scrapers (déjà existants, améliorés)

**Objectif** : construire un catalogue produits/prix pour la comparaison.

**Ce qui a été fait**
- Scraper [Monoprix](../scrapers/scraper_monoprix.py) : utilise le sitemap de `courses.monoprix.fr` et extrait le JSON-LD de chaque page produit. ~26 000 produits disponibles, on en a scrapé ~2800.
- Scraper [Lidl](../scrapers/scraper_lidl.py) : sitemap gzippé. ~10 000 URLs, on en a scrapé ~3200 produits alimentaires (après filtrage).
- **Sauvegarde incrémentale** ajoutée : `save_products` est appelé tous les 100 produits → on peut interrompre à tout moment sans perdre de progression.
- **Filtre alimentaire** : [scrapers/filters.py](../scrapers/filters.py) contient une liste de mots-clés non-alimentaires (chaussures, valise, couette, bougie, etc.). Le filtre normalise les tirets (`siège-auto` → `siège auto`) pour ne rien rater.

**Lancer un scrape**
```bash
source .venv/bin/activate
python scrapers/scraper_monoprix.py --max-products 3000
python scrapers/scraper_lidl.py --max-products 6000
```

**Empêcher la veille du Mac pendant un long scrape**
```bash
# Terminal séparé
caffeinate -i
```

### 3.2 OCR — PaddleOCR

**Objectif** : transformer une photo de ticket en texte brut.

**Choix techniques**
- **PaddleOCR 3.x** (open source, Baidu)
- Modèles français + détection automatique d'orientation activée
- Mise à l'échelle automatique des grandes images (max 1600px) pour économiser la RAM

**Fichiers clés**
- [ocr/paddle_ocr.py](../ocr/paddle_ocr.py) — Classe `ReceiptOCR` + dataclasses `OCRResult` / `OCRLine`
- [ocr/test_sroie.py](../ocr/test_sroie.py) — Évaluation sur SROIE2019

**Tester**
```bash
python -m ocr.test_sroie --n 5
```

**Performance constatée**
- 93-95% de confiance sur photos correctes
- Auto-rotation efficace sur tickets photographiés à 90°
- Encore sensible aux photos très floues / mal éclairées

### 3.3 NER — Ollama + llama3.1:8b

**Objectif** : extraire les entités du ticket (enseigne, total, date, produits, prix).

**Choix techniques**
- **Pas de modèle NER classique** (spaCy, CamemBERT fine-tuné) car nécessite des centaines de tickets annotés à la main.
- **LLM en zero-shot** : Ollama tourne en local, llama3.1:8b est gratuit, données privées.
- Mode `format="json"` d'Ollama → force le modèle à produire du JSON valide.
- Température 0.0 → résultats reproductibles.

**Fichiers clés**
- [ner/models.py](../ner/models.py) — `Receipt` et `LineItem`. **Pour ajouter un champ** : 1 ligne ici + 1 ligne dans `prompt.py`.
- [ner/prompt.py](../ner/prompt.py) — Prompt système avec règles métier : ignorer codes-barres, distinguer "Total Alimentaire" de "TOTAL A PAYER", etc.
- [ner/extractor.py](../ner/extractor.py) — Classe `OllamaExtractor`

**Prérequis**
```bash
# Une seule fois
brew install ollama
ollama pull llama3.1:8b

# À chaque session
ollama serve  # dans un terminal séparé
```

**Tester end-to-end (OCR + NER)**
```bash
python -m ner.test_sroie --n 3
```

### 3.4 Matching — sentence-transformers + FAISS

**Objectif** : trouver dans le catalogue scrapé le produit correspondant à chaque ligne du ticket.

**Choix techniques**
- **Embeddings** : modèle `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, multilingue FR/EN, ~470 MB).
- **FAISS** : `IndexFlatIP` (produit scalaire) avec vecteurs L2-normalisés → équivaut à la similarité cosinus.
- **Seuil de match** : 0.6 (compromis entre recall et précision).
- **Normalisation du texte avant recherche** : passage en minuscules, suppression du tag TVA en fin (` A`, ` B`). Sinon `PANZANI PENNE RIGATE` (uppercase OCR) match moins bien que `panzani penne rigate`.
- **Exclusion des produits prix=0** lors du build de l'index (ruptures de stock du scrape).

**Fichiers clés**
- [matching/embeddings.py](../matching/embeddings.py) — Classe `Embedder`
- [matching/index.py](../matching/index.py) — Construction, sauvegarde, chargement, recherche
- [matching/matcher.py](../matching/matcher.py) — Compare un `Receipt` complet, retourne des `ItemComparison`
- [matching/build_index.py](../matching/build_index.py) — CLI pour (re)construire l'index

**Construire l'index**
```bash
python -m matching.build_index --input data
```

**Tester**
```bash
python -m matching.test_matching                  # requêtes exemples
python -m matching.test_intermarche               # vrai ticket Intermarché
```

### 3.5 Backend FastAPI

**Objectif** : exposer le pipeline en HTTP pour l'app Flutter.

**Endpoints**

| Méthode | URL | Rôle |
|---|---|---|
| GET  | `/`                  | Health check |
| GET  | `/catalog/stats`     | Nombre de produits indexés, par enseigne |
| POST | `/scan`              | Upload image → JSON complet (OCR + NER + matching) |
| GET  | `/history`           | Liste de tous les tickets stockés (résumés) |
| GET  | `/history/stats`     | Agrégations (total, par enseigne, par mois) |
| GET  | `/history/{id}`      | Détails complets d'un ticket |
| POST | `/chat`              | Agent IA : question → réponse |

**Persistance**
- Chaque `/scan` réussi est sauvegardé en `data/receipts/{id}.json` automatiquement.
- L'`id` est un UUID court, retourné dans la réponse pour permettre la navigation.
- Format identique à la réponse `/scan` → on peut recharger un ancien ticket sur l'écran de résultats.

**Particularités techniques**
- **CORS ouvert** (`*`) pour permettre les appels depuis Flutter Web.
- **Lazy loading** des modèles ML (OCR, embedder, FAISS) → démarrage rapide.
- **Singletons** : les modèles restent en mémoire entre les requêtes.
- **Resize automatique** des images > 1600px avant OCR pour limiter la RAM (problème sur MacBook 8 Go).

**Fichiers clés**
- [backend/main.py](../backend/main.py) — App FastAPI
- [backend/chat.py](../backend/chat.py) — Agent RAG

**Lancer**
```bash
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 3.6 Agent IA conversationnel (RAG)

**Objectif** : permettre à l'utilisateur de poser des questions en langage naturel sur ses dépenses ("Combien j'ai dépensé en mai ?", "Mon enseigne préférée ?").

**Approche RAG simplifiée**
1. Charger tous les tickets de `data/receipts/`
2. Calculer des stats (total, par enseigne, par mois, top produits)
3. Injecter ce résumé comme **contexte** dans le prompt système
4. Envoyer (system + contexte + historique + question) à llama3.1:8b
5. Retourner la réponse

**Garde-fous dans le prompt**
- "Réponds UNIQUEMENT en te basant sur les données fournies"
- "N'invente jamais de chiffres"
- "Si l'info n'est pas dans le contexte, dis-le honnêtement"

**Limite de contexte** : on n'envoie que les 25 derniers tickets dans le détail (pour rester rapide). Les stats agrégées couvrent l'ensemble.

**Fichiers clés**
- [backend/chat.py](../backend/chat.py) — Logique RAG
- [smart_foyer_app/lib/screens/chat_screen.dart](../smart_foyer_app/lib/screens/chat_screen.dart) — UI chat

### 3.7 Tickets de démo (seed)

**Pourquoi** : sans 15-20 tickets variés, l'agent IA n'a rien à analyser. Avec 1 ticket scanné en test, ses réponses sont peu impressionnantes.

**Solution**
- [backend/seed_demo.py](../backend/seed_demo.py) génère 15 tickets fictifs réalistes répartis sur 90 jours, sur 5 enseignes (Intermarché, Carrefour, Monoprix, Lidl, Franprix).
- Chaque ticket démo est tagué `"demo": true` → identifiable et purgeable sans toucher aux vrais tickets scannés.

**Commandes**
```bash
python -m backend.seed_demo            # ajoute 15 tickets démo
python -m backend.seed_demo --n 25     # nombre custom
python -m backend.seed_demo --clear    # supprime UNIQUEMENT les démo
```

### 3.8 App Flutter Web

**Choix techniques**
- Flutter cible **web** d'abord (pas d'iOS/Android pour l'instant — pas de simulateur requis pour tester).
- 5 écrans : `HomeScreen`, `ScanScreen`, `ResultsScreen`, `HistoryScreen`, `ChatScreen`.
- 2 packages externes : `http`, `file_picker`.

**Écrans**

| Écran | Description |
|---|---|
| Home | Vérifie le backend, propose 3 actions (scanner, historique, IA) |
| Scan | Upload d'image via file_picker + loading + envoi à `/scan` |
| Results | Détail du ticket : enseigne, total, items, comparaisons FAISS |
| History | Stats agrégées + liste cliquable des tickets |
| Chat | Bulles user/assistant + suggestions + bouton envoyer |

**Lancer**
```bash
cd smart_foyer_app
flutter run -d web-server --web-hostname=127.0.0.1 --web-port=5173
```
Ouvrir `http://127.0.0.1:5173` dans le navigateur.

---

## 4. Comment tout faire tourner ensemble

3 services à lancer en parallèle, dans 3 terminaux séparés :

**Terminal 1 — Ollama (le LLM)**
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

Ensuite : ouvrir `http://127.0.0.1:5173` dans le navigateur.

**Première installation (à faire une seule fois)**
```bash
# Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Ollama
brew install ollama
ollama pull llama3.1:8b

# Flutter
brew install --cask flutter
flutter config --enable-web
cd smart_foyer_app && flutter pub get

# Démo (optionnel)
python -m backend.seed_demo
```

---

## 5. Limitations connues à améliorer

### Qualité des données

| Problème | Cause | Idée d'amélioration |
|---|---|---|
| Comparaison de prix parfois absurde | Catalogue de seulement ~6000 produits sur 36 000 disponibles | Scraper en continu pour atteindre 80% du catalogue de chaque enseigne |
| Lidl pollué par du non-alimentaire | Lidl mélange hard discount + alimentaire. Le filtre par mots-clés ne couvre pas tous les cas | Passer à un classifieur ML léger (catégorisation par embeddings) ou utiliser les catégories Lidl quand disponibles |
| Produits prix=0 | Ruptures de stock au moment du scrape | Re-scraper périodiquement + flag "out_of_stock" |
| Le ticket scanné contient une enseigne non scrapée (Carrefour, Intermarché) | Carrefour a un anti-bot Cloudflare/Datadome | Travailler le scraping avec Playwright + résidentiel proxies, ou utiliser l'API publique si disponible |

### Qualité du pipeline

| Problème | Cause | Idée d'amélioration |
|---|---|---|
| OCR de mauvaise qualité sur photos floues/sombres | Pas de pré-traitement d'image | Pipeline OpenCV : deskew, contrast enhancement, denoise, crop |
| Le LLM confond parfois total et code-barres | Le prompt s'est amélioré mais reste imparfait | Pré-extraction par regex des candidats numeriques + heuristiques avant LLM |
| Items à 0 € dans le NER | Mise en page 2 colonnes mal reconstruite | Utiliser les bounding boxes PaddleOCR pour reconstruire les lignes (regrouper par y, trier par x) |
| Matching faux quand le produit n'existe pas | FAISS retourne toujours un voisin, même mauvais | Seuil dynamique selon la longueur du nom du produit |
| Embedding manque de finesse | Modèle MiniLM générique | Fine-tuner sur paires (ticket, catalogue) — nécessite données labelisées |

### Architecture / production

| Manque | Pourquoi c'est important |
|---|---|
| Pas d'authentification utilisateur | Aujourd'hui tous les tickets sont stockés en commun |
| Pas de base de données | JSON files → ne passe pas l'échelle, pas de requêtes |
| Pas de tests automatisés | Pas de filet pour les régressions |
| Pas de monitoring | Pas de visibilité sur les erreurs en prod |
| Backend non-déployé | Tout tourne en local sur la machine du dev |

---

## 6. Ce qui reste à faire (priorisé)

### Tier 1 — Passer du POC à un MVP utilisable

**A. App mobile native (iOS + Android)**
- Aujourd'hui : Flutter Web fonctionnel
- Cible : `flutter build apk` + `flutter build ios`, distribution TestFlight + APK
- Travaux nécessaires :
  - Tester l'app sur simulateur (`flutter run -d ios`, `flutter run -d android`)
  - Remplacer `file_picker` par `image_picker` (mieux intégré mobile, accès caméra natif)
  - Gérer les permissions caméra (Info.plist iOS, AndroidManifest.xml)
  - Ajuster l'URL du backend (plus de `127.0.0.1` — il faut une URL publique)

**B. Authentification utilisateur (Firebase Auth)**
- Chaque utilisateur a ses propres tickets
- Travaux :
  - Setup Firebase Auth dans le projet Flutter (`firebase_auth` package)
  - Ajouter `firebase_admin` côté backend pour vérifier les JWT
  - Ajouter `user_id` à chaque ticket sauvegardé (`data/receipts/{user_id}/{id}.json`)
  - Écran de login/signup dans Flutter

**C. Base de données persistante (Firestore ou Postgres)**
- Remplacer les fichiers JSON par une vraie base
- Schéma : `users`, `receipts`, `items`, `comparisons`
- Index sur `user_id`, `date` pour les requêtes historiques rapides
- Permet aussi de scaler le matching (catalogue côté DB plutôt qu'en mémoire)

### Tier 2 — Déploiement GCP

**D. Cloud Run pour le backend**
- Dockeriser le backend (`Dockerfile` + `docker-compose.yml`)
- Variables d'env : URL Ollama, modèle, etc.
- Cloud Run avec configuration GPU si nécessaire (PaddleOCR + sentence-transformers tournent sur CPU mais sont lents)

**E. LLM côté cloud**
- Ollama en local n'est pas viable en prod
- Options :
  - Vertex AI (Gemini Pro / Gemini Flash) — cohérent avec l'archi cible
  - Anthropic Claude API (excellent en JSON structuré)
  - Mistral API (alternative française)
- Adapter [ner/extractor.py](../ner/extractor.py) et [backend/chat.py](../backend/chat.py) pour supporter plusieurs backends LLM (pattern Strategy)

**F. Cloud Storage pour les images de tickets**
- Aujourd'hui les images sont supprimées après traitement
- Cible : les conserver pour pouvoir re-traiter en cas de bug, ou afficher dans l'historique

**G. BigQuery pour le catalogue prix**
- L'index FAISS en mémoire ne scale pas au-delà de quelques millions de produits
- Vertex AI Vector Search ou pgvector pour la recherche vectorielle
- BigQuery pour les métadonnées et l'historique

**H. Cloud Functions pour les scrapers**
- Aujourd'hui : on lance les scrapers à la main
- Cible : Cloud Scheduler déclenche un scraping quotidien/hebdomadaire automatique

**I. API Gateway + Firebase Auth**
- L'API Gateway protège les endpoints et vérifie les JWT Firebase

### Tier 3 — Améliorations qualité

**J. Pré-traitement d'image**
- Module `image_preprocess/` à créer
- OpenCV : deskew (redressement), contrast enhancement (CLAHE), denoise, crop sur le ticket
- À placer entre `/scan` upload et l'OCR

**K. Reconstruction layout 2 colonnes**
- Utiliser les `box` des `OCRLine` pour regrouper par ligne (même y) puis trier par x
- Permet au LLM d'avoir des lignes "produit ... prix" propres
- Devrait éliminer les items à 0 €

**L. Tests automatisés**
- Backend : pytest sur les endpoints (mocker Ollama + FAISS)
- Frontend : `flutter test` sur les widgets
- Pipeline OCR/NER : régression sur un golden set de tickets annotés

**M. Catégorisation des produits**
- Tagger chaque produit du catalogue (alimentaire / hygiène / ménager / boissons / etc.)
- Le matching ne propose que des alternatives de la même catégorie
- Approche : zero-shot avec un LLM, ou modèle classifieur simple

**N. Scrapers Carrefour + Intermarché**
- Carrefour : Datadome anti-bot — il faudra des proxies résidentiels + Playwright stealth
- Intermarché : pas testé, à investiguer

### Tier 4 — Features produit

**O. Notifications push**
- Alerte quand un produit récurrent baisse chez une autre enseigne
- Bilan mensuel de dépenses

**P. Listes de courses**
- L'utilisateur peut créer une liste, l'app suggère l'enseigne la moins chère pour la totalité

**Q. Partage / famille**
- Plusieurs utilisateurs sur un même foyer (cf. "SmartFoyer")
- Tickets partagés, vue agrégée

**R. Export comptable**
- CSV / Excel pour l'utilisateur qui veut faire son propre suivi

---

## 7. Notes pour le développeur qui reprend

### Choses non-évidentes à savoir

- **Le venv Python est en 3.9** (le système). Tous les fichiers utilisent `from __future__ import annotations` pour permettre la syntaxe `X | None` malgré 3.9. Ne pas casser ça.
- **Les scrapers écrivent dans `data/` relativement au CWD** — toujours lancer depuis la racine du projet (`/Users/issomeli/smart-foyer`).
- **PaddleOCR télécharge ses modèles dans `~/.paddlex/`** lors du premier appel (~50 Mo).
- **Ollama télécharge llama3.1:8b dans `~/.ollama/`** (~5 Go).
- **L'index FAISS est en mémoire** lors du backend — c'est OK pour 10k produits, à revoir au-delà.
- **CORS est `*`** — à restreindre en prod.
- **Le seuil de matching 0.6** dans [matching/matcher.py](../matching/matcher.py) est paramétrable mais doit être ajusté si on change de modèle d'embedding ou si le catalogue grossit beaucoup.
- **Le LLM côté NER ET côté chat est le même Ollama llama3.1:8b** — un seul instance partagée. C'est lent (~20 s par scan, ~10-30 s par message chat).

### Où ajouter une feature

| Si tu veux... | Modifie... |
|---|---|
| Ajouter un champ extrait du ticket (catégorie, adresse...) | `ner/models.py` + `ner/prompt.py` + UI Flutter |
| Ajouter un nouveau scraper (Franprix, ...) | Copier `scraper_lidl.py`, adapter, ajouter dans `run_all.py`, mentionner dans `filters.py` si besoin |
| Ajouter un type de question à l'agent IA | Améliorer le `SYSTEM_PROMPT` dans `backend/chat.py` et enrichir `_build_context` |
| Améliorer l'UI | `smart_foyer_app/lib/screens/` |
| Ajouter un endpoint backend | `backend/main.py`, créer un module `backend/{feature}.py` si la logique est grosse |
| Changer le LLM | `OLLAMA_MODEL` dans `backend/main.py`, ou créer une abstraction (Strategy pattern) |

### Commandes utiles

```bash
# Re-builder l'index après un nouveau scrape
python -m matching.build_index --input data

# Purger les tickets démo
python -m backend.seed_demo --clear

# Voir le statut du catalogue scrapé
python3 -c "import json; d=json.load(open('data/monoprix_products.json')); print(f'{len(d)} produits')"

# Tester l'agent IA en ligne de commande
curl -s -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"Combien j ai depense ?", "history":[]}' | python3 -m json.tool

# Killer un port occupé
lsof -ti:8000 | xargs kill -9
lsof -ti:5173 | xargs kill -9
```

---

## 8. Récap visuel : ce qui a été fait

```
✅ Scrapers Monoprix + Lidl (avec filtre alimentaire + sauvegarde incrémentale)
✅ OCR PaddleOCR (multi-langue, auto-rotation, resize)
✅ NER Ollama llama3.1:8b (prompt structuré, mode JSON natif)
✅ Matching FAISS + sentence-transformers (multilingue, normalisation OCR)
✅ Backend FastAPI (scan + history + chat + CORS + persistance JSON)
✅ App Flutter Web (5 écrans, fonctionnel)
✅ Persistance des tickets + écran historique + statistiques
✅ Agent IA conversationnel (RAG sur historique)
✅ Tickets de démo réalistes (seed script)
✅ Catalogue final : ~6000 produits alimentaires propres
```

**État actuel** : le POC est **complet de bout en bout**, démontre la valeur, peut être présenté en démo.

**Pour passer en MVP** : voir Tier 1 (mobile native + auth + DB).
**Pour passer en prod** : voir Tier 2 (déploiement GCP).
