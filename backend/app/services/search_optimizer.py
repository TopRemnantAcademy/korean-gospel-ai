"""검색 쿼리 옵티마이저 — 쿼리 분해·재작성·타입 추론.

V2 엔진 핵심:
  - 쿼리 타입 분류 (키워드·성경구절·의미질문·복합)
  - 다중 쿼리 생성 (Query Expansion / HyDE)
  - 동적 하이브리드 가중치 계산
  - 메타데이터 필터 최적화

쿼리가 들어오면 이 모듈이 먼저 분석한 뒤 retriever에 적절한 파라미터 전달.
"""
from __future__ import annotations
import asyncio
import copy
import json
import logging
import re
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 짧은 쿼리 확장 결과 캐시 (TTL 1시간) — 단어 수 적은 쿼리는 반복률이 높음
_EXPANSION_TTL_SEC = 3600.0
_EXPANSION_MAX = 2  # 원본 포함 최대 3개(expanded) 유지
_EXPANSION_CACHE_MAX = 2000  # 캐시 상한 — TTL 만료 대기만으론 무한 성장(메모리 누수) 방지
_expansion_cache: dict[str, tuple[float, list[str]]] = {}
_expansion_lock = threading.RLock()


def _cache_expansion(query: str, vals: list[str]) -> None:
    """확장 결과를 상한이 있는 TTL 캐시에 기록 (무한 성장 방지)."""
    with _expansion_lock:
        _expansion_cache[query] = (time.time(), list(vals))
        if len(_expansion_cache) <= _EXPANSION_CACHE_MAX:
            return
        # 상한 초과: 만료 항목 먼저 제거, 그래도 많으면 가장 오래된 것부터 제거
        now = time.time()
        for k in [k for k, (ts, _) in _expansion_cache.items() if now - ts > _EXPANSION_TTL_SEC]:
            del _expansion_cache[k]
        if len(_expansion_cache) > _EXPANSION_CACHE_MAX:
            oldest = sorted(_expansion_cache, key=lambda k: _expansion_cache[k][0])
            for k in oldest[: len(_expansion_cache) - _EXPANSION_CACHE_MAX]:
                del _expansion_cache[k]

_EXPAND_SYSTEM = (
    "You are a Korean Christian semantic search query rewriter. "
    "Given a short user query, generate up to 2 alternative phrasings that "
    "express the SAME intent using different words, so a hybrid retriever can "
    "recall more relevant passages. Return ONLY a JSON array of strings, "
    "no markdown fences, no extra text. If the query is already unambiguous, "
    "return an empty array []."
)


@dataclass
class QueryAnalysis:
    """쿼리 분석 결과 — retriever에 전달."""
    original: str
    query_type: str  # keyword | bible_verse | semantic | mixed
    expanded_queries: list[str]  # 리라이트된 다중 쿼리
    dense_weight: float  # 0.0 ~ 1.0
    sparse_weight: float  # 1.0 - dense_weight
    preferred_filters: dict  # 미리 추론한 필터 힌트
    confidence: float  # 분석 신뢰도 0.0 ~ 1.0


# 성경 구절 패턴 (한국어 약어·정식명 모두 지원)
_BIBLE_PATTERNS = [
    re.compile(r"[가-힣]{1,4}\s*\d{1,3}:\d{1,3}"),  # 요 3:16
    re.compile(r"[가-힣]{1,4}\s*\d+장"),  # 요한복음 3장
    re.compile(r"창세기|출애굽기|레위기|민수기|신명기|여호수아|사사기|룻기|"
               r"사무엘상|사무엘하|열왕기상|열왕기하|역대상|역대하|에스라|"
               r"느헤미야|에스더|욥기|시편|잠언|전도서|아가|이사야|예레미야|"
               r"예레미야애가|에스겔|다니엘|호세아|요엘|아모스|오바댜|요나|"
               r"미가|나훔|하박국|스바냐|학개|스가랴|말라기|마태복음|"
               r"마가복음|누가복음|요한복음|사도행전|로마서|고린도전서|"
               r"고린도후서|갈라디아서|에베소서|빌립보서|골로새서|"
               r"데살로니가전서|데살로니가후서|디모데전서|디모데후서|"
               r"디도서|빌레몬서|히브리서|야고보서|베드로전서|베드로후서|"
               r"요한일서|요한이서|요한삼서|유다서|요한계시록"),
]

# 구원·믿음 관련 키워드 — semantic 검색에 유리
_SALVATION_TERMS = {
    "구원", "믿음", "은혜", "의롭다", "칭의", "거듭남", "구원받다", "구원의 확신",
    "영생", "죄사함", "십자가", "속죄", "화목제", "중보", "부활", "승천",
    "하나님", "예수", "그리스도", "성령", "삼위일체", "복음", "회개",
}

# 키워드 검색에 유리한 용어 (고유명사·전문용어)
_KEYWORD_INDICATORS = {
    "다락방", "열방", "선교", "제자훈련", "목회", "설교", "말씀", "기도",
    "가정교회", "셀", "리더", "멤버", "훈련", "워크숍", "세미나", "컨퍼런스",
}


def _count_terms(text: str, terms: set[str]) -> int:
    """텍스트에 포함된 용어 개수 카운트 (단어 경계 일치)."""
    cnt = 0
    for t in terms:
        if t in text:
            cnt += 1
    return cnt


_HANGUL_RE = re.compile(r"[가-힣]")


def _word_count(text: str) -> int:
    """한국어·영문 혼용 쿼리의 단어 수 추정.

    띄어쓰기가 거의 없는 한국어 쿼리는 `len(text.split())` 이 1로 오판되어
    쿼리 타입/가중치 분류가 틀어지므로, 공백 토큰 수와 한글 음절 기반 추정
    (평균 어절 3음절 가정) 중 큰 값을 사용한다.
    """
    if not text:
        return 0
    spaced = len(text.split())
    hangul = len(_HANGUL_RE.findall(text))
    return max(spaced, hangul // 3)


def _contains_bible_pattern(text: str) -> bool:
    """성경 구절 패턴 포함 여부."""
    for p in _BIBLE_PATTERNS:
        if p.search(text):
            return True
    return False


def _expand_query_with_llm(query: str) -> list[str]:
    """짧은 쿼리에 대해 LLM 기반 동의어/의도 리라이트를 생성.

    설계 원칙 (검색 주链路 안전성 최우선)
    ------------------------------------
    - 동기 함수 `analyze_query` 내부에서 호출되므로 LLM(async) 을 직접 await 할 수 없다.
    - 실행 중 event loop 가 이미 있으면(비동기 검색 컨텍스트) LLM 호출을 건너뛴다
      (fail-open → 원본 쿼리만 사용). 검색 주链路가 LLM 지연/실패로 블록되면 안 됨.
    - 실행 중 loop 가 없으면(오프라인/동기 스크립트) asyncio.run + wait_for(timeout) 로
      동기 차단 호출한다. 타임아웃/예외는 모두 흡수 → 빈 리스트 반환.
    - 결과는 TTL 캐시에 보관(단어 수 적은 쿼리 반복률 높음).

    매개변수
    --------
    query: 원본 사용자 쿼리(이미 strip 됨).

    반환
    ----
    확장 쿼리 문자열 리스트(원본 제외, 최대 _EXPANSION_MAX 개). 실패 시 [].
    """
    # 1) 캐시 조회 (TTL 체크는 락 내에서 원자적 수행)
    with _expansion_lock:
        cached = _expansion_cache.get(query)
        if cached is not None:
            ts, vals = cached
            if time.time() - ts <= _EXPANSION_TTL_SEC:
                return list(vals)
            del _expansion_cache[query]

    # 2) 실행 중 event loop 가 있으면 LLM 호출 생략 (비동기 컨텍스트 방어)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return []
    except RuntimeError:
        # loop 이 아예 없으면 동기 실행 경로로 진행
        pass

    expansions: list[str] = []
    try:
        from .llm.fallback import chat_with_fallback
        from .llm.base import Message

        async def _call() -> list[str]:
            resp, _llm, _tried = await asyncio.wait_for(
                chat_with_fallback(
                    [Message(role="user", content=query)],
                    system=_EXPAND_SYSTEM,
                    temperature=0.2,
                    max_tokens=200,
                ),
                timeout=3.0,
            )
            raw = (resp.text or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)
            if isinstance(data, list):
                out = []
                for item in data:
                    if isinstance(item, str):
                        s = item.strip()
                        if s and s != query and s not in out:
                            out.append(s)
                return out[:_EXPANSION_MAX]
            return []

        expansions = asyncio.run(_call())
    except Exception as e:  # 모든 실패는 검색 주链路에 영향 없이 흡수
        logger.debug("query 확장 skip (fail-open): %s", e)
        expansions = []

    # 3) 캐시 기록
    _cache_expansion(query, expansions)
    return expansions


def _parse_expansion(raw: str, query: str) -> list[str]:
    """LLM 원시 응답을 확장 쿼리 리스트로 파싱 (공용 헬퍼).

    - 마크다운 펜스(```) 제거
    - JSON 배열 내 문자열만 추출, 원본/중복 제외
    - 최대 `_EXPANSION_MAX` 개 반환
    파싱 실패 시 빈 리스트 반환(호출자에서 fail-open 처리).
    """
    s = (raw or "").strip()
    if not s:
        return []
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str):
            item = item.strip()
            if item and item != query and item not in out:
                out.append(item)
    return out[:_EXPANSION_MAX]


async def _expand_query_async(query: str) -> list[str]:
    """짧은 쿼리에 대해 LLM 기반 동의어/의도 리라이트를 생성 (비동기 경로).

    설계 원칙 (검색 주链路 안전성 최우선)
    ------------------------------------
    - 비동기 검색 컨텍스트(retriever.retrieve) 내부에서 직접 await 호출된다.
      실행 중 event loop 가 있으므로 asyncio.run 을 쓰지 않고 그대로 await 한다.
    - 타임아웃/예외는 모두 흡수 → 빈 리스트 반환. LLM 지연·실패가 검색을 블록하면 안 됨.
    - 결과는 TTL 캐시에 보관(단어 수 적은 쿼리 반복률 높음).

    매개변수
    --------
    query: 원본 사용자 쿼리(이미 strip 됨).

    반환
    ----
    확장 쿼리 문자열 리스트(원본 제외, 최대 _EXPANSION_MAX 개). 실패 시 [].
    """
    # 1) 캐시 조회 (TTL 체크는 락 내에서 원자적 수행)
    with _expansion_lock:
        cached = _expansion_cache.get(query)
        if cached is not None:
            ts, vals = cached
            if time.time() - ts <= _EXPANSION_TTL_SEC:
                return list(vals)
            del _expansion_cache[query]

    expansions: list[str] = []
    try:
        from .llm.fallback import chat_with_fallback
        from .llm.base import Message

        resp, _llm, _tried = await asyncio.wait_for(
            chat_with_fallback(
                [Message(role="user", content=query)],
                system=_EXPAND_SYSTEM,
                temperature=0.2,
                max_tokens=200,
            ),
            timeout=3.0,
        )
        expansions = _parse_expansion(resp.text or "", query)
    except Exception as e:  # 모든 실패는 검색 주链路에 영향 없이 흡수
        logger.debug("query 확장 skip (fail-open): %s", e)
        expansions = []

    # 2) 캐시 기록
    _cache_expansion(query, expansions)
    return expansions


async def analyze_query_async(query: str) -> "QueryAnalysis":
    """`analyze_query` 의 비동기 대응 버전.

    retriever.retrieve (async) 내부에서 await 로 호출된다. LLM 확장은
    `_expand_query_async` 를 직접 await 하므로 '실행 중 loop → 무시' 문제가 없다.
    내부 확장 실패 시에도 원본 쿼리만으로 구성된 QueryAnalysis 를 반환(fail-open).
    """
    from ..config import settings

    q = query.strip()
    if not q:
        return QueryAnalysis(
            original=query, query_type="semantic",
            expanded_queries=[query], dense_weight=0.7, sparse_weight=0.3,
            preferred_filters={}, confidence=0.5,
        )

    salvation_hits = _count_terms(q, _SALVATION_TERMS)
    keyword_hits = _count_terms(q, _KEYWORD_INDICATORS)
    has_bible = _contains_bible_pattern(q)
    word_count = _word_count(q)

    # 쿼리 타입 결정 + 가중치 (동기 버전과 동일 로직)
    if has_bible and word_count <= 4:
        q_type = "bible_verse"
        dense_w = 0.4
        sparse_w = 0.6
        conf = 0.95
    elif keyword_hits >= 3 and salvation_hits <= 1:
        q_type = "keyword"
        dense_w = 0.3
        sparse_w = 0.7
        conf = 0.85
    elif salvation_hits >= 2 and keyword_hits <= 1:
        q_type = "semantic"
        dense_w = 0.8
        sparse_w = 0.2
        conf = 0.8
    else:
        q_type = "mixed"
        dense_w = 0.7
        sparse_w = 0.3
        conf = 0.7

    expanded = [q]  # 원본은 항상 포함

    if has_bible:
        for p in _BIBLE_PATTERNS:
            for m in p.finditer(q):
                verse = m.group()
                if verse not in expanded:
                    expanded.append(verse)

    if word_count <= 3 and q_type in ("semantic", "mixed"):
        # LLM 확장은 settings.search_expand_enabled 가 켜진 경우에만 실제 호출된다.
        # 기본 False → 확장 쿼리 미주입(원본만). 실패/비활성 시에도 원본으로 폴백.
        if getattr(settings, "search_expand_enabled", False):
            for eq in await _expand_query_async(q):
                if eq not in expanded:
                    expanded.append(eq)

    filters = {}
    if salvation_hits >= 2:
        filters["gospel_core_tag"] = True

    return QueryAnalysis(
        original=query,
        query_type=q_type,
        expanded_queries=expanded,
        dense_weight=dense_w,
        sparse_weight=sparse_w,
        preferred_filters=filters,
        confidence=conf,
    )


def analyze_query(query: str) -> QueryAnalysis:
    """단일 쿼리 → 다중 검색 전략으로 분석.

    쿼리의 특성에 따라 dense/sparse 가중치를 동적으로 결정하고,
    검색 품질을 높이기 위한 확장 쿼리도 생성.

    반환: QueryAnalysis 객체
    """
    from ..config import settings

    q = query.strip()
    if not q:
        return QueryAnalysis(
            original=query, query_type="semantic",
            expanded_queries=[query], dense_weight=0.7, sparse_weight=0.3,
            preferred_filters={}, confidence=0.5,
        )

    salvation_hits = _count_terms(q, _SALVATION_TERMS)
    keyword_hits = _count_terms(q, _KEYWORD_INDICATORS)
    has_bible = _contains_bible_pattern(q)
    word_count = _word_count(q)

    # 쿼리 타입 결정 + 가중치
    if has_bible and word_count <= 4:
        # 성경 구절 단독 검색 — sparse가 강력
        q_type = "bible_verse"
        dense_w = 0.4
        sparse_w = 0.6
        conf = 0.95
    elif keyword_hits >= 3 and salvation_hits <= 1:
        # 키워드 중심 — sparse 우선
        q_type = "keyword"
        dense_w = 0.3
        sparse_w = 0.7
        conf = 0.85
    elif salvation_hits >= 2 and keyword_hits <= 1:
        # 구원·신학 의미 중심 — dense 우선
        q_type = "semantic"
        dense_w = 0.8
        sparse_w = 0.2
        conf = 0.8
    else:
        # 혼합형 — 기본 7:3 비율
        q_type = "mixed"
        dense_w = 0.7
        sparse_w = 0.3
        conf = 0.7

    # 쿼리 확장 (최대 3개)
    expanded = [q]  # 원본은 항상 포함

    # 1) 성경 구절이면 구절 번호만 버전으로도 검색
    if has_bible:
        for p in _BIBLE_PATTERNS:
            for m in p.finditer(q):
                verse = m.group()
                if verse not in expanded:
                    expanded.append(verse)

    # 2) 짧은 쿼리는 의미 확장 (LLM 기반 동의어/의도 리라이트)
    #    비동기 버전과 동일하게 search_expand_enabled 게이트를 준수 —
    #    동기 경로(/retrieval)가 플래그 무시하고 LLM 을 호출하던 불일치 제거.
    if word_count <= 3 and q_type in ("semantic", "mixed") and getattr(settings, "search_expand_enabled", False):
        for eq in _expand_query_with_llm(q):
            if eq not in expanded:
                expanded.append(eq)

    # 3) 구원 관련 용어가 있으면 구원 핵심 태그 필터 힌트
    filters = {}
    if salvation_hits >= 2:
        filters["gospel_core_tag"] = True

    return QueryAnalysis(
        original=query,
        query_type=q_type,
        expanded_queries=expanded,
        dense_weight=dense_w,
        sparse_weight=sparse_w,
        preferred_filters=filters,
        confidence=conf,
    )


def merge_duplicate_candidates(candidates: list) -> list:
    """다중 쿼리로 검색한 중복 후보를 점수 합산으로 병합.

    Reciprocal Rank Fusion의 변형 — 여러 쿼리에서 상위에 나올수록 높은 점수.
    """
    if not candidates:
        return []

    scores: dict[str, float] = {}
    points: dict[str, object] = {}

    for rank, item in enumerate(candidates):
        cid = item.id
        points[cid] = item
        # RRF 스타일 점수 (rank 0이 가장 높음)
        rr_score = 1.0 / (rank + 60)
        scores[cid] = scores.get(cid, 0.0) + rr_score

    if not scores:
        return []

    # 점수 순 정렬
    sorted_ids = sorted(scores.keys(), key=lambda x: -scores[x])

    # 원본 객체에 병합 점수 반영
    result = []
    for cid in sorted_ids:
        item = points[cid]
        # 원본 점수와 RRF 점수를 가중 평균
        final_score = item.score * 0.5 + scores[cid] * 10.0 * 0.5
        # 점수 업데이트한 새 객체 생성
        new_item = copy.copy(item)
        new_item.score = final_score
        result.append(new_item)

    return result
