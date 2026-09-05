"""Reranker 추상 + bge-reranker-v2-m3 구현 (한국어 강함)."""
from __future__ import annotations
import logging
import threading
from abc import ABC, abstractmethod
from typing import Sequence

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    name: str = ""

    @abstractmethod
    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        """각 doc에 대한 점수 (높을수록 관련). 반환 길이 == len(docs)."""
        ...


class BgeReranker(BaseReranker):
    name = "bge_m3"
    model_id = "BAAI/bge-reranker-v2-m3"

    def __init__(self, model_id: str | None = None):
        from sentence_transformers import CrossEncoder
        from collections import OrderedDict
        self._ce = CrossEncoder(model_id or self.model_id, max_length=512)
        # [PERF] 캐시 키를 (query, tuple(docs)) 가 아닌 (query, doc) 단위로 세분화.
        # 기존엔 전체 docs 목록(순서 포함)을 키로 삼아 검색 결과가 매번 달라져 사실상 항상 miss
        # (CrossEncoder 추론을 매 요청 실행). 개별 (query, doc) 재등장 시 히트하도록 변경.
        self._cache: OrderedDict = OrderedDict()  # (query, doc_text) -> float
        self._cache_max = 10000
        self._lock = threading.Lock()  # 캐시 변이 보호 (to_thread 병렬 호출 대응)

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        if not docs:
            return []
        n = len(docs)
        result = [0.0] * n
        missed_idx: list[int] = []
        missed_docs: list[str] = []

        with self._lock:
            for i, d in enumerate(docs):
                key = (query, d)
                if key in self._cache:
                    result[i] = self._cache[key]
                    self._cache.move_to_end(key)
                else:
                    missed_idx.append(i)
                    missed_docs.append(d)

        # 추론은 락 밖에서 실행(병렬) — CrossEncoder.predict 는 읽기 전용 forward.
        if missed_docs:
            pairs = [(query, d) for d in missed_docs]
            scores = self._ce.predict(pairs, show_progress_bar=False)
            with self._lock:
                for i, d, s in zip(missed_idx, missed_docs, scores):
                    self._cache[(query, d)] = float(s)
                    result[i] = float(s)
                while len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
        return result


class NoOpReranker(BaseReranker):
    name = "none"

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        # 점수 없음 - 입력 순서 보존을 위해 내림차순 임의값
        return [1.0 - i * 0.001 for i in range(len(docs))]


class CohereReranker(BaseReranker):
    name = "cohere"

    def __init__(self, api_key: str, model: str = "rerank-multilingual-v3.0"):
        if not api_key:
            raise ValueError("COHERE_API_KEY 가 필요합니다.")
        try:
            import cohere  # type: ignore
        except ImportError as e:
            raise ImportError("cohere 패키지가 필요합니다. pip install cohere") from e
        # 클라이언트는 connections.py 레지스트리에서 가져옴 (싱글턴)
        from ..connections import connections
        client = connections.cohere()
        self._co = client if client is not None else cohere.Client(api_key=api_key)
        self._model = model
        self._cache = {}

    def rerank(self, query: str, docs: Sequence[str]) -> list[float]:
        if not docs:
            return []
        cache_key = (query, tuple(docs))
        if cache_key in self._cache:
            return list(self._cache[cache_key])

        resp = self._co.rerank(model=self._model, query=query, documents=list(docs))
        # Cohere 응답은 정렬되어 옴. 원래 순서로 점수 매핑.
        scores = [0.0] * len(docs)
        for r in resp.results:
            scores[r.index] = float(r.relevance_score)

        if len(self._cache) >= 1000:
            self._cache.clear()
        self._cache[cache_key] = scores
        return scores


_reranker_cache: dict[str, BaseReranker] = {}
# fail-open 폴백용 단일 NoOp 인스턴스 (매번 새로 만들지 않아도 됨)
_NOOP = NoOpReranker()

# 로컬 bge-m3 로드를 시도하기 전 확보되어야 할 최소 여유 메모리.
# 8GB 단일 박스(KURE 1.3GB + qdrant + backend + ui 동시 로드)에서
# bge-m3(~1.1GB fp32) 추가 로드 시 OS 레벨 OOM 을 차단하기 위한 안전 마진.
# 이보다 여유가 부족하면 로드를 건너뛰고 NoOp(fail-open) 로 폴백한다.
RERANKER_MIN_FREE_MEM_BYTES = int(1.5 * 1024 ** 3)


def _available_memory_bytes() -> int | None:
    """플랫폼별 여유 메모리(RAM) 조회. 알 수 없으면 None."""
    # 1) psutil (가장 정확, 컨테이너/호스트 모두 동작)
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().available)
    except Exception:
        pass
    # 2) Linux /proc/meminfo fallback (Docker/Lighthouse 박스)
    try:
        with open("/proc/meminfo") as fh:
            avail = free = None
            for line in fh:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) * 1024
                elif line.startswith("MemFree:"):
                    free = int(line.split()[1]) * 1024
            return avail if avail is not None else free
    except Exception:
        return None


def get_reranker(name: str | None = None, *, cohere_api_key: str | None = None) -> BaseReranker:
    """Reranker 팩토리 — 실패 시 항상 NoOp(fail-open) 로 폴백해 채팅 다운을 방지.

    - name="none"            → NoOp (RRF 만 사용)
    - name="bge_m3"          → 로컬 CrossEncoder 로드 (여유 메모리 부족/모델 누락 시 NoOp)
    - name="cohere"          → API 클라이언트 (키 누락/패키지 미설치 시 NoOp)
    - 그 외 unknown           → 경고 후 NoOp

    어떤 경우에도 예외를 던지지 않는다(검색·답변은 계속 동작).
    """
    n = (name or "bge_m3").lower()
    if n == "none":
        return _NOOP
    if n in _reranker_cache:
        return _reranker_cache[n]

    inst: BaseReranker | None = None
    try:
        if n in {"bge", "bge_m3", "bge-m3"}:
            free = _available_memory_bytes()
            if free is not None and free < RERANKER_MIN_FREE_MEM_BYTES:
                logger.warning(
                    "[reranker] 여유 메모리 부족(%.2fGB < %.2fGB)으로 로컬 bge_m3 로드를 "
                    "건너뛰고 NoOp(fail-open)로 폴백합니다. RERANKER=none 과 동일하게 동작합니다.",
                    free / (1024 ** 3),
                    RERANKER_MIN_FREE_MEM_BYTES / (1024 ** 3),
                )
                _reranker_cache[n] = _NOOP
                return _NOOP
            inst = BgeReranker()
        elif n == "cohere":
            inst = CohereReranker(api_key=cohere_api_key or "")
        else:
            logger.warning("[reranker] 알 수 없는 reranker '%s' → NoOp(fail-open) 폴백", name)
            inst = NoOpReranker()
    except Exception as exc:  # 모델 로드 실패 / OOM / 키 누락 / 패키지 부재 등
        logger.warning(
            "[reranker] '%s' reranker 활성화 실패(%s: %s). NoOp(fail-open)로 폴백 — "
            "검색·답변은 계속 동작하나 재순위 정밀도는 RRF 만으로 유지됩니다.",
            n, type(exc).__name__, exc,
        )
        _reranker_cache[n] = _NOOP
        return _NOOP

    if inst is None:
        _reranker_cache[n] = _NOOP
        return _NOOP

    _reranker_cache[n] = inst
    logger.info("[reranker] '%s' reranker 활성화 완료.", n)
    return inst
