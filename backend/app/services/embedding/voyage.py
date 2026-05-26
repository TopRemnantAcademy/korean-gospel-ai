"""Voyage AI Embedder - voyage-3-lite (512-dim).

한국어 벤치마크 및 검색 효율이 높은 상용 API 임베딩 지원.
"""
from __future__ import annotations
import logging
from typing import Sequence

import httpx
import numpy as np

from .base import BaseEmbedder
from ...config import settings

log = logging.getLogger("gospel-embedding-voyage")


class VoyageEmbedder(BaseEmbedder):
    name = "voyage"
    model_id = "voyage-3-lite"

    def __init__(self, model_id: str | None = None):
        self._model_id = model_id or self.model_id
        self._api_key = settings.voyage_api_key
        self._api_url = "https://api.voyageai.com/v1/embeddings"
        self._dim = 512  # voyage-3-lite 고정 차원

    @property
    def dim(self) -> int:
        return self._dim

    def _call_api(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        if not self._api_key:
            raise ValueError(
                "Voyage AI API Key is missing. Please set VOYAGE_API_KEY in your environment/secrets."
            )

        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {
            "input": texts,
            "model": self._model_id,
        }
        if input_type:
            payload["input_type"] = input_type  # "document" or "query"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self._api_url, headers=headers, json=payload)
                if response.status_code != 200:
                    log.error(f"Voyage API Error [{response.status_code}]: {response.text}")
                    response.raise_for_status()
                
                data = response.json().get("data", [])
                # index 순서대로 정렬하여 반환 보장
                data_sorted = sorted(data, key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in data_sorted]
        except Exception as e:
            log.exception(f"Failed to fetch embeddings from Voyage API: {e}")
            raise

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim))
        
        res = self._call_api(list(texts), input_type="document")
        arr = np.array(res, dtype=np.float32)
        
        # L2 정규화
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return arr / norms

    def embed_query(self, text: str) -> np.ndarray:
        res = self._call_api([text], input_type="query")
        arr = np.array(res[0], dtype=np.float32)
        
        norm = np.linalg.norm(arr)
        if norm == 0:
            norm = 1.0
        return arr / norm
