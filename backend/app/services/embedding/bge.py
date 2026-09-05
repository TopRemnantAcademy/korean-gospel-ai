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
        from ...config import settings

        # Windows HF 캐시 심링크(junction) 깨짐 우회:
        # BGE_M3_MODEL_PATH(실제 파일 복사본 로컬 경로)가 설정돼 있으면 우선 사용.
        effective = (
            model_id
            or getattr(settings, "bge_m3_model_path", None)
            or self.model_id
        )
        self._model = SentenceTransformer(effective)
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
