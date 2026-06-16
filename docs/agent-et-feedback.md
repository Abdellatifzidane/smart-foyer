# Agent IA (tool-calling) & Feedback — doc développeur

Ce document décrit deux briques ajoutées à SmartFoyer :

1. **L'agent IA conversationnel** réécrit en *tool-calling* (chiffres fiables).
2. Le **système de feedback 👍/👎** pour évaluer OCR, matching et agent.

Il s'adresse au développeur qui reprend le code et veut comprendre **ce qui a
été fait, comment, et où c'est stocké**.

---

## 1. Agent IA — tool-calling

### Le problème résolu

L'ancienne version injectait des agrégats en texte dans le prompt et laissait le
LLM faire l'arithmétique lui-même. Résultat : sur une question précise
(« combien en lait le mois dernier ? »), le modèle **approximait ou se
trompait**.

La nouvelle version utilise le **tool-calling** : le LLM ne calcule plus rien.
Il choisit un *outil*, **Python calcule le chiffre exact** à partir des tickets,
et le LLM se contente de rédiger la réponse autour du résultat. Les nombres sont
donc **fiables par construction**.

### Avec quoi c'est implémenté

| Élément | Choix |
|---|---|
| LLM | **Groq** `llama-3.3-70b-versatile` (modèle existant, supporte le tool-calling — aucun changement d'infra) |
| Format des outils | Schéma OpenAI / Groq (`tools`, `tool_choice="auto"`, `message.tool_calls`) |
| Source de données | **Historique des tickets uniquement** (aucun accès catalogue → moins d'erreurs) |
| Clé | `GROQ_API_KEY` (dans `.env`) |

### Fichiers

| Fichier | Rôle |
|---|---|
| [`backend/chat.py`](../backend/chat.py) | Orchestration : construit le contexte, lance la **boucle de tool-calling**, gère la robustesse (retries, rate limit). |
| [`backend/chat_tools.py`](../backend/chat_tools.py) | **Les outils** (fonctions pures) + le registre qui expose schémas et dispatch. |
| [`backend/test_chat_tools.py`](../backend/test_chat_tools.py) | Tests **hors-ligne** des outils (ni réseau, ni base, ni clé API). |
| [`backend/main.py`](../backend/main.py) | Endpoint `POST /chat` (charge les tickets du user, appelle l'agent). |

### Flux d'une requête

```
Flutter (chat_screen) ─POST /chat─▶ backend/main.py:chat()
        │
        ├─ receipts_store.load_payloads(db, user)   # tickets du user (scopés)
        └─ chat_answer(question, receipts, history) # backend/chat.py
                 │
                 ▼  boucle (max MAX_TOOL_ROUNDS) :
            Groq décide → appelle un outil → run_tool() calcule en Python
            → résultat réinjecté → Groq rédige la réponse finale
```

### Les 7 outils (`backend/chat_tools.py`)

Toutes les fonctions sont **pures** : `fn(receipts, **args) -> dict`.

| Outil | Question type | Sortie clé |
|---|---|---|
| `spending_summary` | « combien dépensé ce mois / chez Lidl / en crèmerie » | total, nb tickets, panier moyen |
| `product_spending` | « combien en lait » | total + quantité pour un mot-clé |
| `compare_enseignes` | « où je dépense le plus » | total + panier moyen par enseigne |
| `savings_summary` | « comment économiser » | économies cumulées + opportunités |
| `top_products` | « quel produit m'a coûté le plus cher » | classement par dépense (ou prix max) |
| `compare_periodes` | « je dépense plus que le mois dernier ? » | écart € + évolution % + tendance |
| `cheapest_place_for_product` | « où acheter X au meilleur prix » | prix/unité le plus bas par enseigne (**d'après l'historique**) |

> ⚠️ `cheapest_place_for_product` se base sur **ce que l'utilisateur a déjà
> payé**, pas sur le catalogue des magasins. Il ne marche donc que pour des
> produits déjà achetés.

### Le registre (source unique de vérité)

Un outil se déclare **une seule fois**, avec le décorateur `@tool` posé sur sa
fonction (schéma + implémentation collés). On en dérive automatiquement :

- `TOOL_SCHEMAS` → la liste envoyée au LLM,
- `run_tool(name, args, receipts)` → le dispatch d'exécution.

Impossible donc d'exposer au LLM un outil sans implémentation (ou l'inverse).

### Ajouter un nouvel outil

```python
@tool(
    description="Ce que fait l'outil (le LLM le lit pour décider).",
    parameters={                       # schéma JSON des arguments
        "type": "object",
        "properties": {"foo": {"type": "string", "description": "..."}},
        "required": ["foo"],
    },
)
def mon_outil(receipts: list[dict], foo: str) -> dict:
    """Docstring : à quelle question il répond, ce qu'il calcule, ses limites."""
    ...
    return {"resultat": ...}
```

C'est tout : `TOOL_SCHEMAS`, `run_tool` et le test d'alignement le prennent en
compte automatiquement. Ajouter un test dans `test_chat_tools.py`.

### Robustesse (déjà gérée)

- **`tool_use_failed`** : llama produit parfois un appel d'outil mal formé →
  Groq renvoie 400. On **réessaie** (`TOOL_CALL_RETRIES`), puis on **dégrade**
  en répondant sans outils plutôt que de planter.
- **Paramètres entiers** : llama renvoie parfois `"5"` (chaîne). Les schémas
  acceptent `["integer", "string"]` et Python convertit (`int()`).
- **Rate limit (429)** : `POST /chat` renvoie un message clair en HTTP 200
  (« service saturé, réessaie ») au lieu d'un 500. Quota free tier Groq :
  100 000 tokens/jour.
- **`run_tool` ne lève jamais** : toute erreur d'outil est renvoyée comme
  résultat, le LLM peut réagir.

### Tester

```bash
# Outils, hors-ligne (rapide, sans clé ni réseau) :
pytest backend/test_chat_tools.py -q

# Agent de bout en bout (nécessite GROQ_API_KEY + réseau) : via l'app, page Chat.
```

---

## 2. Feedback 👍 / 👎

### Ce qu'on évalue

Trois composants, notés séparément par l'utilisateur :

| `target` | Question posée à l'utilisateur | Où dans l'app |
|---|---|---|
| `ocr` | « Texte bien lu ? » | Écran **Résultats** (après l'en-tête du ticket) |
| `matching` | « Correspondances correctes ? » | Écran **Résultats** (sous la liste produits) |
| `agent` | « Réponse utile ? » | Écran **Chat**, sous **chaque** réponse de l'agent |

Comportement : **👍** = envoi immédiat. **👎** = ouvre un champ commentaire
**optionnel** (« qu'est-ce qui n'allait pas ? ») puis envoie. Une fois noté, les
boutons se désactivent (pas de double vote). Une erreur réseau n'interrompt
jamais l'app (SnackBar + boutons réactivés).

### Où c'est stocké

Table **`feedback`** en SQLite ([`backend/db.py`](../backend/db.py)), créée
automatiquement (`Base.metadata.create_all`, pas de migration) :

| Colonne | Contenu |
|---|---|
| `id` | identifiant |
| `user_id` | utilisateur (scopé) |
| `target` | `ocr` \| `matching` \| `agent` |
| `rating` | `up` \| `down` |
| `receipt_id` | référence ticket (pour ocr / matching) |
| `question`, `answer` | la Q/R évaluée (pour l'agent) |
| `comment` | commentaire libre (surtout sur 👎) |
| `created_at` | horodatage |

### Endpoints ([`backend/main.py`](../backend/main.py))

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/feedback` 🔒 | Enregistre une évaluation (valide `target` et `rating`). |
| GET | `/feedback/stats` 🔒 | Agrégats 👍/👎 + **% de satisfaction** par composant + 20 derniers commentaires. |

### Fichiers frontend

| Fichier | Rôle |
|---|---|
| [`lib/widgets/feedback_buttons.dart`](../smart_foyer_app/lib/widgets/feedback_buttons.dart) | Widget réutilisable 👍/👎 (dialog commentaire sur 👎). |
| [`lib/api/api_client.dart`](../smart_foyer_app/lib/api/api_client.dart) | `sendFeedback(...)` et `feedbackStats()`. |
| [`lib/screens/results_screen.dart`](../smart_foyer_app/lib/screens/results_screen.dart) | Pouces OCR + matching. |
| [`lib/screens/chat_screen.dart`](../smart_foyer_app/lib/screens/chat_screen.dart) | Pouce sous chaque réponse agent. |
| [`lib/screens/admin_screen.dart`](../smart_foyer_app/lib/screens/admin_screen.dart) | Onglet **Feedback** : barres de satisfaction + commentaires récents. |

### Consulter les feedbacks

- Dans l'app : **Administration → onglet Feedback**.
- En SQL :

```sql
SELECT target, rating, COUNT(*) FROM feedback GROUP BY target, rating;
```
(base : `data/smartfoyer.db`)
