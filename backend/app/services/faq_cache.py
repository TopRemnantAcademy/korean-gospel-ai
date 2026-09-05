"""FAQ 정적 캐시 — 자주 묻는 질문 사전 저장.

문제: 동일/유사한 질문이 반복될 때마다 임베딩 → 벡터검색 → LLM 생성 파이프라인을
전부 다시 돌리면 응답 지연이 누적된다. 특히 인기 있는 복음 질문(요 3:16, 구원 확신 등)
은 트래픽의 상당 비중을 차지한다.

해결: 질문 정규화 키를 기준으로 (임베딩/검색 생략) 미리 계산된 답변을 반환한다.
- 최초 miss 시 정상 파이프라인으로 생성하고, 일정 횟수(hits) 이상 반복된 질문만
  정적 캐시에 등록 → "자주 묻는 질문"만 캐싱해 메모리 낭비 방지.
- TTL 만료 시 자연 스탬프. 프로세스 로컬(worker 간 미공유) — 다중 워커 환경에서는
  로드밸런서 레벨 캐시나 Redis 로 확장 가능.

대규모 데이터 환경에서도 hot-path 질문은 O(1) 해시 조회로 즉시 응답한다.
"""
from __future__ import annotations

import logging
import threading
import time
import re
import unicodedata

from ..config import settings

logger = logging.getLogger(__name__)


# ── 질문 정규화 (캐시 키) ──────────────────────────────────────────────────────
def _normalize_query(query: str) -> str:
    """질문 → 정규화 키.

    - NFKC 정규화 (전각/반각, 호환자모 통일)
    - 소문자
    - 한국어 조사/조사류 불용어 제거 (의미 변형 최소화)
    - 공백/구두점 정리
    """
    if not query:
        return ""
    q = unicodedata.normalize("NFKC", query).lower().strip()
    # 자주 반복되는 한국어 조사/어미 제거 (의미 보존)
    # regex alternation 으로 한 번에 치환 — 반복 replace 대신 O(n) 패스
    # [FIX] 의문사(왜/어떻게/무엇/뭐/언제/어디/누구/얼마나)와 단일자 지시어(이/그/저)를
    # 제거 대상에서 뺐다. 이들은 질문의 의미를 결정하는 핵심어라, 제거하면
    # "왜 기도해야 하나요"와 "기도해야 하나요"가 같은 키로 충돌해 엉뚱한 캐시 답변이
    # 서빙됐다. 또한 단일자 "이"는 "이름→름", "그"는 "그리스도→리스도"처럼 단어를
    # 훼손했으므로 제외. (조사류 은/는/가/을/를 등만 유지)
    _JOSA_RE = re.compile(
        r"은|는|가|을|를|에|에서|로|으로|와|과|도|만|까지|부터|께서|한테|에게|"
        r"및|그리고|또는|이랑|랑|하고|의"
    )
    q = _JOSA_RE.sub(" ", q)
    # 영문/숫자/한글 외 제거
    q = re.sub(r"[^\w가-힣\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


# ── 캐시 저장소 ────────────────────────────────────────────────────────────────
# key=정규화질문, value=(만료시각, 답변텍스트, 출처메타, hits)
_cache: dict[str, tuple[float, str, list, int]] = {}
_cache_lock = threading.RLock()
# [PERF] 크기 상한 — 초과 시 가장 오래된 항목(삽입순)부터 제거해 메모리 무한성장 방지
_CACHE_MAX = 10000


def _now() -> float:
    return time.time()


def _estimate_answer_tokens(text: str) -> int:
    """답변 토큰 추정 (chat_pipeline._estimate_tokens 와 동일 휴리스틱)."""
    if not text:
        return 0
    return max(1, int(len(text) * 0.55))


def get_cached_answer(query: str) -> tuple[str, list] | None:
    """정적 FAQ 캐시 조회.

    Returns:
        (answer_text, sources) 또는 None (캐시 미스/비활성)
    """
    if not settings.faq_cache_enabled:
        return None
    key = _normalize_query(query)
    if not key:
        return None
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        expire_at, answer, sources, _hits = item
        if _now() > expire_at:
            del _cache[key]
            return None
        # hit 카운트 증가 (인기 질문 유지/승격 판정용)
        _hits += 1
        _cache[key] = (expire_at, answer, sources, _hits)
        # 승격 임계치(faq_min_hits) 이상 조회된 질문만 정적 캐시에서 바로 응답한다.
        # 그 전(후보 단계)에는 정상 파이프라인으로 생성하되 hit 만 누적 — 모듈 문서/설정
        # 의도(자주 묻는 질문만 캐싱해 메모리 낭비 방지)를 따른다. 이전 코드는 임계치를
        # 무시하고 hit=1 부터 바로 서빙해 faq_min_hits 가 사실상 사문화( dead config )됐다.
        if _hits < settings.faq_min_hits:
            return None
        return answer, sources


def maybe_cache_answer(query: str, answer: str, sources: list) -> None:
    """정상 생성된 답변을 후보로 기록/갱신.

    조건부 등록:
    - faq_cache_enabled 가 켜져 있어야 함
    - 빈 답변/너무 짧은 답변은 저장 안 함
    - 동일 키가 faq_min_hits 회 이상 조회된 경우에만 "정적 캐시"로 승격
    """
    if not settings.faq_cache_enabled:
        return
    key = _normalize_query(query)
    # 답변이 너무 짧으면(토큰 기준) 캐시 가치 없음 — 문자수가 아닌 토큰 추정 사용
    if not key or not answer or _estimate_answer_tokens(answer) < 12:
        return
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            # 첫 등장: hit=1 후보
            _cache[key] = (_now() + settings.faq_cache_ttl_sec, answer, sources, 1)
            # [PERF] 크기 상한 초과 시 오래된 항목(삽입순)부터 제거
            while len(_cache) > _CACHE_MAX:
                _cache.pop(next(iter(_cache)))
        else:
            expire_at, _old_answer, _old_sources, hits = item
            # 이미 캐시된(승격된) 항목이면 답변 갱신 + TTL 리셋
            if hits >= settings.faq_min_hits:
                _cache[key] = (
                    _now() + settings.faq_cache_ttl_sec,
                    answer,
                    sources,
                    hits,
                )
            else:
                # 후보 단계: hit +1, 임계치 도달 시 승격
                new_hits = hits + 1
                _cache[key] = (
                    _now() + settings.faq_cache_ttl_sec,
                    answer,
                    sources,
                    new_hits,
                )


def faq_stats() -> dict:
    """캐시 통계 (모니터링용)."""
    with _cache_lock:
        promoted = sum(1 for v in _cache.values() if v[3] >= settings.faq_min_hits)
        return {
            "total_keys": len(_cache),
            "promoted": promoted,
            "ttl_sec": settings.faq_cache_ttl_sec,
            "min_hits": settings.faq_min_hits,
        }


def clear_faq_cache() -> None:
    """캐시 전체 비우기 (관리자/디버그 용)."""
    with _cache_lock:
        _cache.clear()
