"""BAAI/bge-m3: 다국어 SOTA 임베딩 (한국어도 강함, 1024-dim)."""
from __future__ import annotations
from typing import Sequence

import numpy as np

from .base import BaseEmbedder


class BgeM3Embedder(BaseEmbedder):
    name = "bge_m3"
    model_id = "BAAI/bge-m3"

    def __init__(self, model_id: str | None = None):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_id or self.model_id)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dim(self) -> int:
        return int(self._dim)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def embed_query(self, text: str) -> np.ndarray:
        v = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return v[0]
