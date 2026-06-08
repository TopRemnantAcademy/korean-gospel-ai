"""Hugging Face Inference API Embedder - Serverless KURE-v1 (1024-dim).

Fly.io 256MB RAM 제약을 극복하기 위해 로컬 로딩 없이 외부 API를 호출하여 임베딩 추출.
"""
from __future__ import annotations
import logging
from typing import Sequence

import httpx
import numpy as np

from .base import BaseEmbedder
from ...config import settings

log = logging.getLogger("gospel-embedding-hf")


class HfInferenceEmbedder(BaseEmbedder):
    name = "hf_inference"
    model_id = "nlpai-lab/KURE-v1"

    def __init__(self, model_id: str | None = None):
        self._model_id = model_id or self.model_id
        # connections.py 레지스트리에서 HF 설정 가져옴
        from ...connections import connections
        _cfg = connections.hf_inference()
        self._token = settings.hf_token
        self._api_url = (
            _cfg["url"] if _cfg
            else f"https://api-inference.huggingface.co/pipeline/feature-extraction/{self._model_id}"
        )
        self._headers = _cfg["headers"] if _cfg else {"Authorization": f"Bearer {self._token}"}
        self._dim = 1024  # KURE-v1 고정 차원

    @property
    def dim(self) -> int:
        return self._dim

    def _call_api(self, texts: list[str]) -> list:
        if not self._token:
            raise ValueError(
                "Hugging Face Token is missing. Please set HF_TOKEN in your environment/secrets."
            )

        # options.wait_for_model=True는 첫 로드 시 모델 부팅을 대기하도록 강제함 (cold start 방지)
        payload = {"inputs": texts, "options": {"wait_for_model": True}}

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(self._api_url, headers=self._headers, json=payload)
                if response.status_code != 200:
                    log.error(f"HF Inference API Error [{response.status_code}]: {response.text}")
                    response.raise_for_status()
                return response.json()
        except Exception as e:
            log.exception(f"Failed to fetch embeddings from HF Inference API: {e}")
            raise

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim))
        
        # API 호환성을 위해 list[str] 타입으로 보장
        text_list = list(texts)
        res = self._call_api(text_list)
        
        # JSON 결과 파싱 및 numpy 변환
        arr = np.array(res, dtype=np.float32)
        
        # 1D로 반환된 경우 (문서가 단 1개인 경우) 2D로 reshape
        if arr.ndim == 1:
            arr = np.expand_dims(arr, axis=0)
            
        # L2 정규화 (sentence-transformers 기본값과 매칭)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        # 0 나누기 방지
        norms = np.where(norms == 0, 1.0, norms)
        return arr / norms

    def embed_query(self, text: str) -> np.ndarray:
        res = self._call_api([text])
        arr = np.array(res, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[0]
        
        norm = np.linalg.norm(arr)
        if norm == 0:
            norm = 1.0
        return arr / norm
