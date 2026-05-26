"""Embedding 추상 인터페이스. 모든 임베더는 동일 시그니처를 가짐 → A/B 테스트 용이."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np


class BaseEmbedder(ABC):
    """모든 임베딩 모델이 구현해야 하는 인터페이스."""

    name: str = ""              # 식별자 (예: "kure_v1")
    model_id: str = ""          # HuggingFace 모델 ID

    @property
    @abstractmethod
    def dim(self) -> int:
        ...

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """N x dim 행렬 반환."""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> np.ndarray:
        """1D 벡터 (dim,) 반환. query/passage prefix 처리도 여기서."""
        ...
