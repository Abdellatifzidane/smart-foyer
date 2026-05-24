"""
Embeddings wrapper
==================
Converts product names (text) into normalized vectors for similarity search.

Default model: paraphrase-multilingual-MiniLM-L12-v2
  - Multilingual (FR + EN + 50+ languages)
  - 384 dimensions
  - ~470 MB download (cached after first use)
  - Fast on CPU
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder:
    """Wraps a sentence-transformers model and returns L2-normalized vectors."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """
        Encode a list of texts into a (n, dim) float32 array.
        Vectors are L2-normalized so inner product == cosine similarity.
        """
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
        )
        return vectors.astype(np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single text into a (1, dim) float32 array."""
        return self.encode([text])
