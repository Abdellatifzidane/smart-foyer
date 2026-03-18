# Analyse de Faisabilite du Scraping - Retailers France

> Date d'analyse : 18 Mars 2026
> Objectif : Evaluer la faisabilite technique et la conformite du scraping des prix produits sur les sites de grande distribution en France.

---

## Tableau Recapitulatif

| Enseigne | robots.txt | Produits accessibles | API bloquee | Sitemap | Anti-bot | Faisabilite |
|----------|-----------|---------------------|-------------|---------|----------|-------------|
| Carrefour | Permissif | Oui | Non | Non fourni | Faible | ✅ FAISABLE |
| Lidl | Restrictif | Partiel (via sitemap) | Oui (`/user-api/*`) | Oui | Moyen | ⚠️ PARTIEL |
| E.Leclerc | Tres restrictif | Non (`/catalogue` bloque) | Partiellement | Oui | Moyen | ❌ NON FAISABLE |
| Monoprix | Restrictif | Oui (pages directes) | Oui (Demandware) | Oui | Moyen | ⚠️ PARTIEL |
| Franprix | Inaccessible (403) | N/A | N/A | N/A | Tres fort (WAF) | ❌ NON FAISABLE |
| Auchan | Tres restrictif | Non (`/categories/*` bloque) | Oui (`/api*`) | Oui | Fort | ❌ NON FAISABLE |
| Intermarche | Indisponible (502) | N/A | N/A | N/A | Inconnu | ❓ A RETESTER |
| Casino / Geant Casino | Inaccessible (403) | N/A | N/A | N/A | Tres fort | ❌ NON FAISABLE |
| Picard | Restrictif | Partiel (via sitemap) | Oui (Demandware) | Oui | Moyen | ⚠️ PARTIEL |
| Cora | Restrictif | Non (pattern NW bloque) | Oui (`/api*`) | Oui | Moyen (crawl-delay: 3s) | ❌ NON FAISABLE |
| G20 | Bloque tout (`Disallow: /`) | Non | N/A | Non fourni | Fort | ❌ NON FAISABLE |
| Systeme U (coursesu.com) | Inaccessible (403 Cloudflare) | N/A | N/A | N/A | Tres fort (Cloudflare WAF) | ❌ NON FAISABLE |
| Biocoop | Restrictif | Partiel (`/catalog/` bloque) | Non mentionne | Oui | Faible | ⚠️ PARTIEL |
| Naturalia | Tres restrictif | Non (`/catalog/` + `/api/` bloques) | Oui (`/api/`) | Oui | Moyen | ❌ NON FAISABLE |

---

## Analyse Detaillee par Enseigne

### ✅ Carrefour (carrefour.fr) — FAISABLE

**robots.txt : Permissif**

Chemins bloques :
- `/set-store`, `/get-store` (selection magasin)
- `/webview` (vue mobile)
- `/g`, `/b` (chemins internes)

**Ce qui est autorise :**
- Pages produits
- Pages catalogue/categories
- Pas de blocage API explicite
- Pas de crawl-delay

**Verdict :** Les pages produits et catalogues ne sont pas explicitement bloques. C'est le site le plus accessible pour le scraping. Attention cependant aux CGU et aux protections anti-bot cote serveur.

---

### ⚠️ Lidl (lidl.fr) — PARTIELLEMENT FAISABLE

**robots.txt : Restrictif sur les parametres**

Chemins bloques :
- `/user-api/*`, `/cqe/*` (API)
- `*search?q=*` (recherche)
- `*?offset=*` (pagination)
- `*idsOnly=*`, `*productsOnly=*`, `*id=*`, `*pageId=*` (filtres)
- `*sort=*` (tri)

**Ce qui est autorise :**
- Pages produits statiques (URLs directes)
- Sitemap disponible : `https://www.lidl.fr/static/sitemap.xml`

**Verdict :** La navigation dynamique (recherche, pagination, filtres) est bloquee. Le sitemap reste exploitable pour decouvrir les URLs produits individuels. Scraping possible mais limite au contenu statique.

---

### ❌ E.Leclerc (e.leclerc) — NON FAISABLE

**robots.txt : Tres restrictif**

Chemins bloques :
- `/catalogue` (catalogue complet)
- `*/offers`, `/of/` (offres et prix)
- `/recherche` (recherche)
- `/api/rest/mabaya-api/` (API produits)

**Verdict :** Le catalogue, les offres et la recherche sont explicitement bloques. Aucune voie legale de scraping des prix.

---

### ⚠️ Monoprix (monoprix.fr) — PARTIELLEMENT FAISABLE

**robots.txt : Restrictif (Demandware/Salesforce Commerce Cloud)**

Chemins bloques :
- `/on/demandware.store/`, `/dw/shop/v` (API Demandware)
- `/search/`, `/Search-Show?` (recherche)
- `?prefn`, `?prefv`, `?srule=`, `?q=`, `?pid=`, `?cid=` (filtres/parametres)

**Ce qui est autorise :**
- Pages produits directes (sans parametres)
- Sitemap : `https://www.monoprix.fr/sitemap_index.xml`

**Verdict :** Les pages produits individuelles sont accessibles si on decouvre les URLs via le sitemap. La recherche et le filtrage sont bloques.

---

### ❌ Franprix (franprix.fr) — NON FAISABLE

**robots.txt : Inaccessible (HTTP 403)**

- Detection de bot active (header `Ws-Action: bot`)
- WAF (Web Application Firewall) en place
- Toute requete automatisee est bloquee avant d'atteindre le contenu

**Verdict :** Protection anti-bot agressive. Scraping impossible sans contournement (non ethique).

---

### ❌ Auchan (auchan.fr) — NON FAISABLE

**robots.txt : Tres restrictif**

Chemins bloques :
- `/categories/*` (catalogue)
- `/recherche*` (recherche)
- `/api*` (tous les endpoints API)
- `/*sort=*`, `/*ref=*`, `/*keywords=*` (parametres dynamiques)
- `/boutique/*` (sauf `/boutique/promos$`)

**Verdict :** Catalogue, recherche et API entierement bloques. Seule la page promos est autorisee.

---

### ❓ Intermarche (intermarche.com) — A RETESTER

**robots.txt : Indisponible (HTTP 502 Bad Gateway)**

Le serveur etait en erreur au moment de l'analyse. A reverifier ulterieurement.

---

### ❌ Casino / Geant Casino — NON FAISABLE

**robots.txt : Inaccessible (HTTP 403)**

- `casino.fr` : Acces bloque
- `geantcasino.fr` : Redirige vers `petitcasino.casino.fr`, egalement bloque (403)
- Protection active contre les requetes automatisees

**Verdict :** Anti-scraping agressif au niveau infrastructure.

---

### ⚠️ Picard (picard.fr) — PARTIELLEMENT FAISABLE

**robots.txt : Restrictif (Demandware)**

Chemins bloques :
- `*Search-Show*`, `/recherche` (recherche)
- `*BzvReviews-*` (avis Bazaarvoice)
- `*?prefn1=*`, `*sortFilter=*`, `*srule=*` (filtres/tri)
- `/on/demandware.store/` (API)

**Ce qui est autorise :**
- Pages produits directes
- Sitemap : `https://www.picard.fr/sitemap_0.xml`

**Verdict :** Meme schema que Monoprix (Demandware). Pages produits accessibles via sitemap uniquement.

---

### ❌ Cora (cora.fr) — NON FAISABLE

**robots.txt : Restrictif avec crawl-delay**

Chemins bloques :
- `/api*` (API complete)
- `/*sortby=*` (tri)
- `/recherche*` (recherche)
- `/*/NW-*/NW-*` (pattern produits)
- **Crawl-delay : 3 secondes**

**Verdict :** API et pattern produits explicitement bloques. Le crawl-delay ajoute une contrainte supplementaire.

---

### ❌ G20 (g20.fr) — NON FAISABLE

**robots.txt : Bloque tout**

```
User-agent: *
Disallow: /
```

Seul Googlebot a un acces partiel. Tous les autres bots sont completement bloques.

**Verdict :** Aucun scraping autorise.

---

### ❌ Systeme U / Courses U (coursesu.com) — NON FAISABLE

**robots.txt : Inaccessible (403 Cloudflare)**

- Protection Cloudflare WAF active
- Requetes automatisees bloquees avant d'atteindre le serveur

**Verdict :** Infrastructure anti-bot robuste.

---

### ⚠️ Biocoop (biocoop.fr) — PARTIELLEMENT FAISABLE

**robots.txt : Restrictif (Magento)**

Chemins bloques :
- `/catalog/`, `/catalogsearch/` (catalogue et recherche)
- `/search/` (recherche)
- `/*?` (tous les parametres de requete)
- `/brand/` (marques)

**Ce qui est autorise :**
- Pages produits directes potentiellement accessibles
- Sitemap : `https://www.biocoop.fr/sitemap.xml`

**Verdict :** Catalogue bloque mais les pages produits individuelles pourraient etre accessibles via le sitemap.

---

### ❌ Naturalia (naturalia.fr) — NON FAISABLE

**robots.txt : Tres restrictif (Magento)**

Chemins bloques :
- `/catalog/` (catalogue)
- `/api/` (API explicitement bloquee)
- `/*?` (tous les parametres)
- `/index.php/`

**Verdict :** Double blocage catalogue + API. Plus restrictif que Biocoop.

---

## Synthese et Recommandations

### Enseignes exploitables pour le MVP

| Priorite | Enseigne | Strategie |
|----------|----------|-----------|
| 1 | **Carrefour** | Scraping direct des pages produits |
| 2 | **Monoprix** | Decouverte via sitemap + scraping pages produits |
| 3 | **Lidl** | Decouverte via sitemap + scraping pages statiques |
| 4 | **Picard** | Decouverte via sitemap + scraping pages produits |
| 5 | **Biocoop** | Decouverte via sitemap (a valider) |

### Enseignes non exploitables (sans partenariat)

E.Leclerc, Franprix, Auchan, Casino, Cora, G20, Systeme U, Naturalia

### Alternatives pour les enseignes bloquees

1. **APIs ouvertes / Open Data** : Verifier si des APIs publiques existent (ex: Open Food Facts pour les donnees produits)
2. **Partenariats data** : Contacter les enseignes pour des accords de partage de donnees
3. **Agregateurs tiers** : Utiliser des services comme Prixing, Qui-est-le-moins-cher, ou des flux de donnees commerciaux
4. **Prospectus numeriques** : Scraper les catalogues promotionnels (souvent moins proteges que les sites e-commerce)
5. **Google Shopping API** : Exploiter les donnees de prix indexees par Google

### Bonnes pratiques de scraping ethique

- Respecter les regles `robots.txt` de chaque site
- Implementer un `crawl-delay` raisonnable (minimum 2-3s entre requetes)
- Identifier le bot avec un `User-Agent` transparent (ex: `SmartFoyer-Bot/1.0`)
- Ne pas surcharger les serveurs (limiter les requetes concurrentes)
- Mettre en cache les resultats pour eviter les requetes repetitives
- Se conformer au **RGPD** : ne collecter que les donnees de prix (pas de donnees personnelles)
