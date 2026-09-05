"""자체 한국어 BM25 sparse 인덱스 (ENGINE V2-V1).

embedded Qdrant 가 BM42 sparse 를 지원하지 않으므로, 앱 레벨에서 BM25 인덱스를
메모리에 유지해 dense 검색이 놓치는 *정확어·성경장절·고유명사*를 잡는다.

- 토큰화: Kiwi 형태소 분석기 (명사·동사어간·고유명사·숫자·영문)
- 랭킹: rank_bm25 (BM25Okapi)
- 동기화: publish 시 청크 추가, 서버 시작 시 Qdrant scroll 로 전체 재구축
- 컬렉션(임베더)별 독립 인덱스

쓰레드 안전: 간단한 RLock 으로 add/search/rebuild 직렬화.
"""
from __future__ import annotations

import logging
import heapq
import re
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Kiwi 토크나이저 (싱글턴, lazy) ───────────────────────────────────────────
_kiwi = None
_kiwi_lock = threading.Lock()

# BM25 에 의미있는 품사만 사용
# [FIX #23] "N" (명사 전체) 대신 구체적 태그로 세분화하여 의존명사(NNB,NNBC: '것','수','때' 등) 제외
# NNG=일반명사, NNP=고유명사, NR=수사 — NNB(의존명사), NNBC(단위의존명사)는 노이즈이므로 제외
_KEEP_TAGS = ("NNG", "NNP", "NR", "V", "XR", "SL", "SN", "SH", "MAG")

# 성경 장절 패턴 (요 3:16, 로마서 5:8) — 토큰으로 통째 보존
_VERSE_RE = re.compile(r"[가-힣A-Za-z]{1,8}\s*\d{1,3}:\d{1,3}")


def _get_kiwi():
    global _kiwi
    if _kiwi is None:
        with _kiwi_lock:
            if _kiwi is None:
                from kiwipiepy import Kiwi
                _kiwi = Kiwi()
    return _kiwi


def tokenize(text: str) -> list[str]:
    """한국어 텍스트 → BM25 토큰 리스트.

    형태소 토큰 + 성경 장절(통째) 을 합쳐 반환. 소문자 정규화.
    """
    if not text:
        return []
    tokens: list[str] = []

    # 1) 성경 장절을 통째 토큰으로 (예: "요 3:16" → "요3:16")
    for m in _VERSE_RE.finditer(text):
        tokens.append(re.sub(r"\s+", "", m.group()).lower())

    # 2) 형태소 토큰
    try:
        kiwi = _get_kiwi()
        for tok in kiwi.tokenize(text):
            if tok.tag.startswith(_KEEP_TAGS) and len(tok.form) >= 1:
                tokens.append(tok.form.lower())
    except Exception as e:
        logger.debug("kiwi tokenize 실패, 공백분리 fallback: %s", e)
        tokens.extend(w.lower() for w in re.findall(r"[가-힣A-Za-z0-9]+", text))

    return tokens


# ── BM25 인덱스 (컬렉션별) ───────────────────────────────────────────────────
@dataclass
class _IndexEntry:
    chunk_id: str           # Qdrant point id
    tokens: list[str]
    payload: dict           # title/text/metadata (검색결과 복원용)


class BM25Index:
    """단일 컬렉션의 메모리 BM25 인덱스."""

    def __init__(self):
        self._entries: dict[str, _IndexEntry] = {}
        self._bm25 = None              # rank_bm25.BM25Okapi
        self._dirty = False
        self._lock = threading.RLock()

    def _rebuild_bm25(self):
        from rank_bm25 import BM25Okapi
        if not self._entries:
            self._bm25 = None
            return
        corpus = [e.tokens for e in self._entries.values()]
        self._bm25 = BM25Okapi(corpus)
        self._dirty = False

    def add(self, chunk_id: str, text: str, payload: dict):
        """청크 1개 추가 (중복 id 는 O(1) 교체)."""
        with self._lock:
            toks = tokenize(text)
            self._entries[chunk_id] = _IndexEntry(chunk_id=chunk_id, tokens=toks, payload=payload)
            self._dirty = True

    def add_batch(self, items: list[tuple[str, str, dict]]):
        """[(chunk_id, text, payload), ...] 일괄 추가."""
        with self._lock:
            for cid, text, payload in items:
                self._entries[cid] = _IndexEntry(
                    chunk_id=cid, tokens=tokenize(text), payload=payload
                )
            self._dirty = True

    def remove_by(self, predicate) -> int:
        """predicate(payload)->bool 인 항목 제거. 제거 수 반환."""
        with self._lock:
            before = len(self._entries)
            self._entries = {
                cid: e for cid, e in self._entries.items() if not predicate(e.payload)
            }
            removed = before - len(self._entries)
            if removed:
                self._dirty = True
            return removed

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float, dict]]:
        """BM25 검색 → [(chunk_id, score, payload), ...] (score 내림차순)."""
        # [PERF] Kiwi 토크나이즈(CPU-heavy)는 락 밖에서 실행 — 인덱스 상태와 무관.
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        with self._lock:
            if self._dirty or self._bm25 is None:
                self._rebuild_bm25()
            if self._bm25 is None or not self._entries:
                return []
            scores = self._bm25.get_scores(q_tokens)
            # [PERF] 전체 정렬(O(N log N)) 대신 top-k 힙(O(N log k)) 사용.
            top = heapq.nlargest(top_k, zip(self._entries.values(), scores), key=lambda x: x[1])
            return [
                (e.chunk_id, float(s), e.payload)
                for e, s in top if s > 0
            ]

    def size(self) -> int:
        return len(self._entries)


# ── 전역 레지스트리 (컬렉션별) ───────────────────────────────────────────────
_indices: dict[str, BM25Index] = {}
_registry_lock = threading.Lock()


def get_index(collection: str) -> BM25Index:
    if collection not in _indices:
        with _registry_lock:
            if collection not in _indices:
                _indices[collection] = BM25Index()
    return _indices[collection]


def rebuild_from_qdrant(collection: str, client) -> int:
    """Qdrant 의 모든 포인트를 scroll 로 읽어 BM25 인덱스 재구축. 적재 수 반환."""
    idx = get_index(collection)
    items: list[tuple[str, str, dict]] = []
    try:
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                payload = dict(p.payload or {})
                text = payload.get("text", "")
                if text:
                    items.append((str(p.id), text, payload))
            if offset is None:
                break
    except Exception as e:
        logger.warning("[sparse] %s rebuild 실패: %s", collection, e)
        return 0

    if items:
        idx.add_batch(items)
    logger.info("[sparse] %s BM25 인덱스 재구축: %d개 청크", collection, idx.size())
    return idx.size()
