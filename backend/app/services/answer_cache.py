"""P4 #1 — 생성 답변 캐시 (정규화 키 + TTL).

FAQ 정적 캐시(faq_cache.py, 정확 일치)와 별도로, LLM 이 생성한 답변을
정규화된 질의 키로 TTL 캐싱한다. 기본은 프로세스 내 TTL 캐시(스레드 안전),
REDIS_URL 이 설정되면 Redis 공유 캐시로 승격(다중 worker 일관성).

⚠️ 공유 공개 캐시: 키는 (정규화 질의 + 언어) 이므로 사용자 맞춤(profile) 차이는
   반영되지 않는다. 공개 Gospel Q&A 특성상 수용 가능하나, 개인화가 중요한
   경로에서는 answer_cache_enabled=False 로 끈다.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from typing import Optional

from ..config import settings

_lock = threading.RLock()
_mem: dict[str, tuple[float, dict]] = {}  # key -> (expire_ts, payload)


def normalize_query(q: str) -> str:
    """의미-유사 근사 정규화: NFKC/NFC, 소문자, 공백 정리, 구두점/기호 제거."""
    q = unicodedata.normalize("NFC", q or "")
    q = q.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[^\w\s가-힣]", "", q)
    return q.strip()


def _redis_client():
    url = getattr(settings, "redis_url", None)
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_timeout=1, decode_responses=True)
    except Exception:
        return None


def get_answer(key: str) -> Optional[dict]:
    """캐시 hit 시 payload dict 반환, miss/expire 시 None."""
    r = _redis_client()
    if r is not None:
        try:
            raw = r.get(key)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    with _lock:
        item = _mem.get(key)
        if not item:
            return None
        exp, payload = item
        if exp < time.time():
            _mem.pop(key, None)
            return None
        return payload


def set_answer(key: str, payload: dict, ttl: Optional[int] = None) -> None:
    """캐시 저장. ttl 미지정 시 settings.answer_cache_ttl_sec 사용."""
    ttl = ttl if ttl is not None else settings.answer_cache_ttl_sec
    r = _redis_client()
    if r is not None:
        try:
            r.setex(key, ttl, json.dumps(payload, ensure_ascii=False))
            return
        except Exception:
            pass
    with _lock:
        _mem[key] = (time.time() + ttl, payload)
