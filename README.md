# SmartFoyer - Gestion Economique Intelligente du Foyer

**SmartFoyer** est une application mobile/web intelligente qui permet aux utilisateurs de scanner leurs tickets de caisse, comparer les prix entre enseignes en temps reel, visualiser leurs depenses et recevoir des conseils personnalises pour optimiser leur budget courses.

## Contexte et Problematique

Les menages francais consacrent en moyenne **500 EUR par mois** aux courses alimentaires. La comparaison manuelle des prix entre enseignes reste fastidieuse et chronophage. SmartFoyer automatise ce processus pour identifier les economies potentielles sur chaque achat.

## Fonctionnalites principales

- **Scanner de tickets** : Photographier un ticket de caisse via l'app Flutter, extraction automatique via OCR + NLP, conservation de la photo originale pour verification visuelle.
- **Pipeline d'extraction robuste** : OCR layout-aware (reconstruit les colonnes produit / prix), prompt LLM exhaustif, isolation des erreurs (une etape qui echoue degrade la reponse au lieu de casser le serveur).
- **Comparaison de prix** : Recherche semantique hybride (embeddings + re-ranking lexical) sur les produits scrapes des enseignes (Lidl, Monoprix, etc.).
- **Recapitulatif d'economies** : Calcul "meme panier ailleurs" : combien aurait coute le ticket si chaque produit etait achete chez le concurrent le moins cher.
- **Historique des tickets** : Liste avec vignette photo, total, enseigne, date. Acces aux details (photo originale + produits extraits + matches).
- **Page Analytics** : Depenses par semaine / par mois / par categorie / par enseigne, avec graphiques (bar charts + camembert).
- **Agent IA Conseiller** : Chatbot RAG pour interroger ses habitudes ("Sur quoi je depense le plus ?", "Combien je depense par semaine ?").
- **Administration** : CRUD catalogue produits, lancement de jobs de scraping (Lidl, Monoprix).

## Demarrage local rapide

Pre-requis : Python 3.12, Flutter 3.11+, une `.env` avec `GROQ_API_KEY=...` a la racine.

```bash
# Backend (Terminal 1)
cd ~/smart-foyer && source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Frontend Web (Terminal 2)
cd ~/smart-foyer/smart_foyer_app
flutter run -d web-server --web-port 5000 --web-hostname 0.0.0.0 \
  --dart-define=BACKEND_URL=http://localhost:8000

# Puis ouvrir http://localhost:5000 dans Chrome
```

Sous WSL, si Chrome (Windows) n'arrive pas a joindre `localhost:8000`, recupere l'IP WSL avec `hostname -I` et passe-la dans `BACKEND_URL=http://<ip-wsl>:8000`.

## Architecture cible (GCP)

```
                            Google Cloud Platform
                    +----------------------------------------------+
                    |                                              |
                    |   Cloud Run              Vertex AI           |
                    |  +----------------+   +--------------+      |
                    |  | Matching Svc   |-->|   FAISS      |      |
                    |  |                |   |(Vector Search)|      |
                    |  +----------------+   +--------------+      |
 +-------------+    |  | OCR Service    |   | NER Model    |      |
 | Flutter App |--->|  +----------------+   | Training     |      |
 +-------------+    |  | Agent IA       |   +--------------+      |
                    |  +----------------+                         |
                    |                          Stockage           |
                    |   Jobs Planifies        +--------------+    |
                    |  +----------------+     | Cloud Storage|    |
                    |  | Cloud Scheduler|     | Firestore    |    |
                    |  | Cloud Functions|---->| BigQuery     |    |
                    |  | (Scrapers)     |     +--------------+    |
                    |  +----------------+                         |
                    +----------------------------------------------+
                                   |
                          +--------+--------+
                          |   Monoprix      |
                          |   Franprix      |
                          |   Carrefour     |
                          |   Lidl ...      |
                          +-----------------+
```

Le POC actuel fait tourner toute la pile **en local** (FastAPI + Flutter web) et stocke les tickets et le catalogue sur disque (`data/`).

## Stack technique

| Composant | POC local | Production cible |
|---|---|---|
| Frontend | Flutter (Web + iOS) | Flutter (App stores) |
| Backend HTTP | FastAPI + Uvicorn | Cloud Run |
| OCR | PaddleOCR 3.x (FR) | Cloud Run |
| NER / LLM | Groq (llama-3.3-70b) | Vertex AI |
| Embeddings | sentence-transformers MiniLM multilingual | Vertex AI |
| Vector Search | FAISS (IndexFlatIP) | Vertex AI Vector Search |
| Persistance tickets | JSON sur disque + image originale | Firestore + Cloud Storage |
| Catalogue produits | JSONL + FAISS sur disque | BigQuery + Vertex AI |
| Scrapers | Python (requests / cloudscraper) | Cloud Scheduler + Cloud Functions |
| Auth | (POC : aucune) | Firebase Auth |
| CI/CD | (manuel) | Cloud Build + Artifact Registry |

## Pipeline de traitement d'un ticket

1. **Photo** : Capture via l'app (camera ou galerie), upload multipart vers `/scan`.
2. **Preprocessing** : Resize si > 1600px de cote (limite RAM).
3. **OCR layout-aware** :
   - PaddleOCR detecte chaque fragment de texte + sa bounding box.
   - Les fragments sont regroupes par bande horizontale (clustering Y) puis tries gauche-droite : les colonnes "produit | prix" arrivent **sur la meme ligne** dans le texte envoye au LLM.
   - Sans cette etape, l'OCR brute fragmentait les colonnes et le LLM ratait la majorite des produits.
4. **NER (LLM)** :
   - Prompt systeme strict : exhaustivite, distinction produits vs reductions / labels comptables, validation de la somme.
   - Reponse JSON structuree (`enseigne`, `date`, `total`, `items[]`).
5. **Matching** : voir section ci-dessous.
6. **Persistance** : JSON dans `data/receipts/{id}.json`, image dans `data/receipts/images/{id}.jpg`.
7. **Reponse** : payload complet avec `pipeline.errors[]` listant les eventuelles etapes degradees.

### Robustesse de la pipeline

Chaque etape est isolee dans un `try/except`. Si l'OCR plante, on continue avec un texte vide ; si le NER plante, on retourne un ticket vide ; si le matching plante, on renvoie quand meme la liste extraite. Le client recoit toujours un HTTP 200 avec un champ `pipeline.errors` qui detaille ce qui a echoue.

Cote Flutter, un `ApiException` typé propage le message d'erreur jusqu'a un SnackBar, et un `ErrorBoundary` global remplace le carre rouge plein ecran par un widget "Cette page a rencontre un probleme — Retour". Une exception ne tue jamais l'app.

## Comparaison de prix (Matching semantique hybride)

1. **Embedding** de la requete (nom du produit scanne) avec `paraphrase-multilingual-MiniLM-L12-v2`.
2. **Recall dense** : top-30 plus proches voisins par cosinus dans FAISS.
3. **Filtrage prix > 0** : les produits sans prix (rupture, scrape rate) sont elimines pour ne jamais afficher de "match a 0,00 EUR".
4. **Re-rank lexical** : Jaccard sur tokens normalises (accents retires, unites detachees, stopwords FR / unites supprimes). Le score final est `0.6 x cosinus + 0.4 x lexical`.
5. **Seuil hybride** (defaut 0.45) : sous ce score, on retourne "aucune correspondance" plutot qu'un faux match (par ex. "Chocolat NoL galette pain d'epice" vs "Beignet chocolat noisette").
6. **Alternatives moins cheres** : parmi le top, ceux d'une enseigne differente et strictement moins chers que le best match, top 3 par prix croissant.

## Agent IA (Architecture RAG)

1. L'utilisateur pose une question en langage naturel.
2. Le backend charge l'historique des tickets, calcule des agregats compacts (total, par enseigne, par mois).
3. Cet etat est injecte en contexte d'un prompt Groq.
4. Le LLM repond en s'appuyant uniquement sur les donnees fournies (pas d'invention).

## Cas d'usage

| Persona | Profil | Objectif |
|---|---|---|
| Marie, 35 ans | Mere de famille, 3-4 tickets/semaine | Reduire le budget courses de 15% |
| Thomas, 28 ans | Jeune actif urbain, 1-2 tickets/semaine | Optimiser ses achats sans effort |
| Sylvie, 55 ans | Retraitee, 2-3 tickets/semaine | Maximiser chaque euro d'economie |

## Roadmap

- [x] Definition des personas et cas d'usage
- [x] Conception des maquettes UI
- [x] Architecture technique GCP (cible)
- [x] Module OCR (PaddleOCR + reconstruction layout-aware)
- [x] Pipeline NLP (Groq llama-3.3 + prompt exhaustif)
- [x] Scraping des catalogues (Lidl, Monoprix)
- [x] Matching semantique hybride (FAISS + re-ranking lexical)
- [x] Agent IA conversationnel (RAG sur historique)
- [x] App Flutter (Scan, Historique, Resultats avec photo, Analytics, Admin, Chat)
- [x] Robustesse end-to-end (pipeline isolee, ErrorBoundary, retries)
- [ ] Authentification utilisateur (Firebase Auth)
- [ ] Deploiement Cloud Run + Vertex AI
- [ ] Build mobile natif (iOS, Android)
- [ ] Monitoring + alerting (Cloud Logging / Sentry)

## Endpoints HTTP principaux

| Methode | URL | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/catalog/stats` | Nombre de produits indexes (FAISS) par enseigne |
| POST | `/scan` | Upload d'une image -> Receipt + comparisons + `pipeline.errors` |
| GET | `/history` | Liste des tickets (resumes, plus recent en premier) |
| GET | `/history/stats` | Agregats : total, par enseigne, par mois, par semaine, par categorie |
| GET | `/history/{id}` | Detail complet d'un ticket |
| GET | `/history/{id}/image` | Photo originale du ticket (JPEG/PNG) |
| POST | `/chat` | Question libre a l'agent IA |
| GET | `/catalog/products` | Liste paginee + filtres (enseigne, recherche) |
| POST | `/catalog/products` | Ajouter manuellement un produit au catalogue |
| PUT | `/catalog/products/{id}` | Modifier un produit |
| DELETE | `/catalog/products/{id}` | Supprimer un produit (tombstone) |
| POST | `/admin/scrape` | Lancer un job de scraping (Lidl ou Monoprix) |
| GET | `/admin/scrape/status` | Etat d'un job |

## Securite et conformite

- Conformite **RGPD** pour la gestion des donnees utilisateur (cible).
- Scraping **ethique** des catalogues de prix (respect des `robots.txt`, throttling).
- Authentification securisee via **Firebase Auth** (cible).

## Equipe

- **Abdellatif Zidane** - [GitHub](https://github.com/Abdellatifzidane)
- **Melissa Issolah**

## License

Ce projet est sous licence MIT.
