"""multilingual-e5-large: 다국어 임베딩 (1024-dim). query/passage prefix 필요."""
from __future__ import annotations
from typing import Sequence

import numpy as np

from .base import BaseEmbedder


class E5Embedder(BaseEmbedder):
    name = "e5"
    model_id = "intfloat/multilingual-e5-large"

    def __init__(self, model_id: str | None = None):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_id or self.model_id)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dim(self) -> int:
        return int(self._dim)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        # e5는 passage 앞에 "passage: " prefix 필수
        prefixed = [f"passage: {t}" for t in texts]
        return self._model.encode(
            prefixed, convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )

    def embed_query(self, text: str) -> np.ndarray:
        v = self._model.encode(
            [f"query: {text}"], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        return v[0]
