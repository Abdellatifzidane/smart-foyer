"""
Embeddings wrapper
==================
Convertit un nom de produit en vecteur normalisé pour la recherche par
similarité.

Modèle par défaut : **intfloat/multilingual-e5-small**
  - Famille E5, entraînée spécifiquement pour la recherche (retrieval) —
    nettement plus fiable que paraphrase-MiniLM sur des noms de produits
    courts et bruités.
  - Multilingue (FR + 100 langues), 384 dimensions, rapide sur CPU.
  - Particularité E5 : il faut préfixer le texte par "query: " (côté requête)
    ou "passage: " (côté catalogue). On le gère automatiquement ici.

Le modèle est configurable via la variable d'environnement EMBED_MODEL.
"""

from __future__ import annotations

import os

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = os.environ.get(
    "EMBED_MODEL", "intfloat/multilingual-e5-small"
)


class Embedder:
    """Encapsule un modèle sentence-transformers et renvoie des vecteurs
    L2-normalisés (produit scalaire == cosinus)."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        # `get_sentence_embedding_dimension` a été renommé dans les versions
        # récentes de sentence-transformers ; on tolère les deux.
        if hasattr(self.model, "get_embedding_dimension"):
            self.dim = self.model.get_embedding_dimension()
        else:
            self.dim = self.model.get_sentence_embedding_dimension()
        # Les modèles E5 exigent des préfixes "query:"/"passage:".
        self._needs_prefix = "e5" in model_name.lower()

    # ─── Préfixes E5 ───────────────────────────────────────────────
    def _prep(self, texts: list[str], kind: str) -> list[str]:
        if not self._needs_prefix:
            return texts
        prefix = "query: " if kind == "query" else "passage: "
        return [prefix + (t or "") for t in texts]

    def encode(
        self,
        texts: list[str],
        kind: str = "passage",
        batch_size: int = 64,
    ) -> np.ndarray:
        """Encode une liste de textes en tableau (n, dim) float32 normalisé.

        kind : "passage" (produits du catalogue) ou "query" (item scanné).
        """
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self.model.encode(
            self._prep(texts, kind),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
        )
        return vectors.astype(np.float32)

    def encode_one(self, text: str, kind: str = "query") -> np.ndarray:
        """Encode un seul texte en tableau (1, dim). Par défaut traité comme
        une requête (cas d'usage le plus fréquent : recherche)."""
        return self.encode([text], kind=kind)
