"""KURE-v1: 한국어 SOTA 임베딩 (nlpai-lab/KURE-v1, 1024-dim, 2025)."""
from __future__ import annotations
from typing import Sequence

import numpy as np

from .base import BaseEmbedder


class KureEmbedder(BaseEmbedder):
    name = "kure"
    model_id = "nlpai-lab/KURE-v1"

    def __init__(self, model_id: str | None = None):
        from sentence_transformers import SentenceTransformer
        from ...config import settings

        # Windows HF 캐시가 심링크(junction)로 깨져 로드 실패하는 환경 우회:
        # KURE_MODEL_PATH(실제 파일 복사본 로컬 경로)가 설정돼 있으면 우선 사용.
        effective = (
            model_id
            or getattr(settings, "kure_model_path", None)
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
        # KURE는 query/passage 분리 prefix 없음 (그대로 사용)
        v = self._model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return v[0]
