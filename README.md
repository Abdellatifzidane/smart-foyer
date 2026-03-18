# SmartFoyer - Gestion Economique Intelligente du Foyer

**SmartFoyer** est une application mobile intelligente qui permet aux utilisateurs de scanner leurs tickets de caisse, comparer les prix entre enseignes en temps reel, et recevoir des conseils personnalises pour optimiser leur budget courses.

## Contexte et Problematique

Les menages francais consacrent en moyenne **500 EUR par mois** aux courses alimentaires. La comparaison manuelle des prix entre enseignes reste fastidieuse et chronophage. SmartFoyer automatise ce processus pour identifier les economies potentielles sur chaque achat.

## Fonctionnalites principales

- **Scanner de tickets** : Photographier et analyser automatiquement les tickets de caisse via OCR + NLP
- **Comparaison de prix** : Matching semantique des produits et recherche vectorielle pour trouver les meilleurs prix entre enseignes (Carrefour, Lidl, Monoprix, Franprix, Leclerc...)
- **Historique des depenses** : Visualisation des depenses par categorie, enseigne et periode avec graphiques d'evolution
- **Agent IA Conseiller** : Chatbot RAG pour poser des questions sur ses habitudes de consommation ("Sur quoi je depense le plus ?", "Quels produits acheter ailleurs ?", "Combien je depense par semaine ?")
- **Jobs automatises** : Scraping continu des catalogues de prix et re-entrainement periodique des modeles ML

## Architecture technique

```
                            Google Cloud Platform
                    ┌──────────────────────────────────────────────┐
                    │                                              │
                    │   Cloud Run              Vertex AI           │
                    │  ┌─────────────────┐   ┌──────────────┐     │
                    │  │ Matching Service │──>│    FAISS      │     │
                    │  │                 │   │ (Vector Search)│     │
                    │  ├─────────────────┤   ├──────────────┤     │
 ┌────────────┐     │  │  OCR Service    │   │ NER Model     │     │
 │ Flutter App │──>API│ ├─────────────────┤   │ Training      │     │
 └────────────┘  GW │  │  Agent IA       │   └──────────────┘     │
                    │  └─────────────────┘                        │
                    │                          Stockage            │
                    │   Jobs Planifies        ┌──────────────┐    │
                    │  ┌─────────────────┐    │Cloud Storage  │    │
                    │  │ Cloud Scheduler  │    │Firestore      │    │
                    │  │ Cloud Functions  │───>│BigQuery       │    │
                    │  │ (Scrapers)       │    └──────────────┘    │
                    │  └─────────────────┘                        │
                    └──────────────────────────────────────────────┘
                                   │
                          ┌────────┴────────┐
                          │   Monoprix      │
                          │   Franprix      │
                          │   Carrefour     │
                          │   Lidl ...      │
                          └─────────────────┘
```

## Stack technique

| Composant | Service GCP |
|---|---|
| Frontend Mobile | Flutter |
| Backend (Hebergement) | Cloud Run |
| Base de donnees Tickets | Cloud Firestore + Cloud Storage |
| Base de donnees Prix / Produits / Magasins | BigQuery |
| Stockage Modeles ML | Cloud Storage (GCS) |
| OCR | Developpement from scratch |
| NLP / ML | Vertex AI (NER + Zero-shot LLM) |
| Agent IA | Cloud Run + LLM open source (RAG) |
| Scraping Jobs | Cloud Scheduler + Cloud Functions |
| API Gateway | API Gateway |
| Authentification | Firebase Auth |
| Monitoring | Cloud Monitoring + Cloud Logging |
| CI/CD | Cloud Build + Artifact Registry |

## Pipeline de traitement d'un ticket

1. **Photo** : Prise de vue du ticket de caisse via l'app Flutter
2. **OCR** : Extraction du texte present dans le ticket
3. **NLP Parse** : NER (Name Entity Recognition) + Zero-shot LLM pour structurer les donnees (produit, prix, enseigne, date)
4. **Validation** : Correction optionnelle par l'utilisateur
5. **Stockage** : Enregistrement structure dans Firestore + photo dans Cloud Storage

## Comparaison de prix (Matching semantique)

1. **Embedding** : Generation des vecteurs d'embeddings pour le produit scanne
2. **Vector Search** : Recherche approximative via FAISS parmi les produits indexes
3. **Score de confiance** : Validation avec un seuil de similarite
4. **Affichage** : Resultats recuperes depuis BigQuery avec prix par enseigne

## Agent IA (Architecture RAG)

1. L'utilisateur pose une question en langage naturel
2. Le systeme appelle les tools pertinents (BigQuery, historique...)
3. Recuperation des donnees contextuelles
4. LLM reformule une reponse personnalisee

## Cas d'usage

| Persona | Profil | Objectif |
|---|---|---|
| Marie, 35 ans | Mere de famille, 3-4 tickets/semaine | Reduire le budget courses de 15% |
| Thomas, 28 ans | Jeune actif urbain, 1-2 tickets/semaine | Optimiser ses achats sans effort |
| Sylvie, 55 ans | Retraitee, 2-3 tickets/semaine | Maximiser chaque euro d'economie |

## Roadmap

- [x] Definition des personas et cas d'usage
- [x] Conception des maquettes UI
- [x] Architecture technique GCP
- [ ] Developpement du module OCR
- [ ] Pipeline NLP (NER + extraction structuree)
- [ ] Mise en place du scraping des catalogues
- [ ] Matching semantique et recherche vectorielle (FAISS)
- [ ] Developpement de l'Agent IA (RAG)
- [ ] Integration Flutter + API Gateway
- [ ] Tests, monitoring et deploiement

## Securite et conformite

- Conformite **RGPD** pour la gestion des donnees utilisateur
- Scraping **ethique** des catalogues de prix
- Authentification securisee via **Firebase Auth**

## Equipe

- **Abdellatif Zidane** - [GitHub](https://github.com/Abdellatifzidane)
- **Melissa Issolah**

## License

Ce projet est sous licence MIT.
