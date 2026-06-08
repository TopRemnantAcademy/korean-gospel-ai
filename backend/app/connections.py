"""API 연결 레지스트리 — 모든 외부 서비스 클라이언트를 한 곳에서 관리.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-29
# Task: API 연결 중앙화 — 모든 외부 SDK 클라이언트를 이 파일에서만 초기화
#       각 서비스 구현체는 자체적으로 SDK를 초기화하지 않고 여기서 가져다 씀
# =============================================================================

외부 API 연결 목록:
  LLM     : Gemini (Google), DeepSeek, OpenAI, Anthropic/Claude, Ollama(로컬)
  VectorDB: Qdrant (embedded / server / memory)
  Embed   : HuggingFace Inference API, Voyage AI
  Rerank  : Cohere
  Trace   : Langfuse

사용법:
    from ..connections import connections as conn

    client  = conn.gemini()          # google.genai.Client
    client  = conn.deepseek()        # AsyncOpenAI (DeepSeek base_url + timeout)
    client  = conn.openai_client()   # AsyncOpenAI (api.openai.com)
    client  = conn.anthropic()       # AsyncAnthropic
    qclient, is_server = conn.qdrant()  # (QdrantClient, bool)
    lf      = conn.langfuse()        # Langfuse | None
    co      = conn.cohere()          # cohere.Client | None
    hf_cfg  = conn.hf_inference()   # {"url": str, "headers": dict} | None
    vo_cfg  = conn.voyage()          # {"url": str, "headers": dict} | None
    status  = conn.status()          # 전체 연결 상태 dict
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from .config import settings

logger = logging.getLogger(__name__)

# ─── 내부 레지스트리 ──────────────────────────────────────────────────────────
_registry: dict[str, Any] = {}
_lock = threading.Lock()
_SENTINEL = object()  # 초기화 시도했으나 실패한 항목 마킹용


def _get(key: str):
    """레지스트리에서 값 조회. 없거나 _SENTINEL이면 None 반환."""
    v = _registry.get(key, None)
    return None if v is _SENTINEL else v


def _set(key: str, value: Any):
    _registry[key] = value


def _once(key: str, factory):
    """Thread-safe 1회 초기화."""
    if key in _registry:
        return _get(key)
    with _lock:
        if key in _registry:
            return _get(key)
        try:
            result = factory()
            _set(key, result)
        except Exception as e:
            logger.warning("[conn] %s 초기화 실패: %s", key, e)
            _set(key, _SENTINEL)
            result = None
    return result


# ─── LLM ─────────────────────────────────────────────────────────────────────

def gemini():
    """Google Gemini SDK 클라이언트 (google.genai.Client).
    GOOGLE_API_KEY 없으면 None.
    """
    if not settings.google_api_key:
        return None

    def _factory():
        from google import genai  # type: ignore
        return genai.Client(api_key=settings.google_api_key)

    return _once("gemini", _factory)


def deepseek():
    """DeepSeek 전용 AsyncOpenAI 클라이언트.
    DEEPSEEK_API_KEY 없으면 None.
    기본 600s read timeout → llm_provider_timeout_sec + 5s 로 제한.
    """
    if not settings.deepseek_api_key:
        return None

    def _factory():
        import httpx
        from openai import AsyncOpenAI  # type: ignore
        # connect=5s: 서버 자체에 연결 안 되면 즉시 실패 (무응답 빠른 감지)
        # read=None: 응답이 느려도 완성될 때까지 무한 대기 (폴백 발동 안 함)
        return AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0),
        )

    return _once("deepseek", _factory)


def openai_client():
    """OpenAI 전용 AsyncOpenAI 클라이언트.
    OPENAI_API_KEY 없으면 None.
    """
    if not settings.openai_api_key:
        return None

    def _factory():
        from openai import AsyncOpenAI  # type: ignore
        return AsyncOpenAI(api_key=settings.openai_api_key)

    return _once("openai", _factory)


def anthropic():
    """Anthropic AsyncAnthropic 클라이언트.
    ANTHROPIC_API_KEY 없으면 None.
    """
    if not settings.anthropic_api_key:
        return None

    def _factory():
        from anthropic import AsyncAnthropic  # type: ignore
        return AsyncAnthropic(api_key=settings.anthropic_api_key)

    return _once("anthropic", _factory)


def ollama_base_url() -> str:
    """Ollama 로컬 호스트 URL (API key 불필요)."""
    return (settings.ollama_host or "http://localhost:11434").rstrip("/")


# ─── VectorDB ────────────────────────────────────────────────────────────────

def qdrant() -> tuple:
    """(QdrantClient | None, is_server: bool).

    3가지 모드:
      local:./path  → embedded (Docker 불필요, 프로세스당 1개 인스턴스만 허용)
      memory:       → 인메모리 (테스트용)
      http://...    → 서버 모드 (Qdrant Cloud 등, 다중 접속 허용)

    ※ embedded 모드: 프로세스당 1개 인스턴스만 허용.
       초기화 실패(잠금 충돌 등) 시 (None, False) 반환 후 재시도 가능.
       vector_store._make_client() 와 동일한 수동 캐시를 공유.
    """
    # 순환 임포트 방지 위해 지연 임포트
    from .services.vector_store import _make_client
    return _make_client()


def qdrant_mode() -> str:
    """Qdrant 연결 모드 문자열 반환 (초기화 시도 없이 config만 보고 판단)."""
    url = (settings.qdrant_url or "").strip()
    if url.startswith("local:"):
        return "embedded/local"
    if url in {"memory:", ":memory:", "memory"}:
        return "memory"
    return "server"


# ─── Embedder HTTP APIs ───────────────────────────────────────────────────────

def hf_inference() -> Optional[dict]:
    """HuggingFace Inference API 설정.
    HF_TOKEN 없으면 None.
    반환: {"url": str, "headers": dict, "model_id": str}
    """
    if not settings.hf_token:
        return None
    model_id = "nlpai-lab/KURE-v1"
    return {
        "model_id": model_id,
        "url": f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_id}",
        "headers": {"Authorization": f"Bearer {settings.hf_token}"},
    }


def voyage() -> Optional[dict]:
    """Voyage AI 설정.
    VOYAGE_API_KEY 없으면 None.
    반환: {"url": str, "headers": dict}
    """
    if not settings.voyage_api_key:
        return None
    return {
        "url": "https://api.voyageai.com/v1/embeddings",
        "headers": {"Authorization": f"Bearer {settings.voyage_api_key}"},
    }


# ─── Reranker ────────────────────────────────────────────────────────────────

def cohere():
    """Cohere 클라이언트.
    COHERE_API_KEY 없으면 None.
    """
    if not settings.cohere_api_key:
        return None

    def _factory():
        import cohere as _cohere  # type: ignore
        return _cohere.Client(api_key=settings.cohere_api_key)

    return _once("cohere", _factory)


# ─── Tracing ─────────────────────────────────────────────────────────────────

def langfuse():
    """Langfuse 클라이언트.
    LANGFUSE_ENABLED=false 또는 키 없으면 None.
    """
    if not settings.langfuse_enabled:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None

    def _factory():
        from langfuse import Langfuse  # type: ignore
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )

    return _once("langfuse", _factory)


# ─── 전체 상태 조회 ────────────────────────────────────────────────────────────

def status() -> dict:
    """모든 외부 API 연결 상태를 한 번에 반환.

    ※ qdrant embedded 모드는 프로세스당 1개 인스턴스만 허용 → status()에서 새 인스턴스
      생성을 시도하지 않고 이미 초기화된 레지스트리 / config 기반으로 상태 판단.

    각 항목:
      "ok"          → 키/URL 설정됨 & (캐시 초기화 성공 또는 아직 미호출)
      "active"      → 레지스트리에 살아있는 인스턴스 존재
      "missing"     → API 키 / URL 미설정
      "error"       → 초기화 시도했으나 실패
      "disabled"    → 기능 플래그로 비활성화
    """
    def _state(key: str, has_key: bool) -> str:
        if not has_key:
            return "missing"
        if key in _registry:
            return "error" if _registry[key] is _SENTINEL else "active"
        return "ok"  # 키는 있으나 아직 lazy init 전 → 설정상 문제없음

    # qdrant: vector_store 수동 캐시 확인 (init 유발 없이 상태만 조회)
    _q_url = (settings.qdrant_url or "").strip()
    _q_has_url = bool(_q_url)
    try:
        from .services import vector_store as _vs
        if _vs._client_instance is not None:
            _q_status = "active"
        else:
            _q_status = "ok" if _q_has_url else "missing"
    except Exception:
        _q_status = "ok" if _q_has_url else "missing"

    return {
        # ── LLM ──
        "gemini":    _state("gemini",    bool(settings.google_api_key)),
        "deepseek":  _state("deepseek",  bool(settings.deepseek_api_key)),
        "openai":    _state("openai",    bool(settings.openai_api_key)),
        "anthropic": _state("anthropic", bool(settings.anthropic_api_key)),
        "ollama":    "ok",  # 로컬, 항상 설정됨 (실제 응답은 런타임에)
        # ── VectorDB ──
        "qdrant":      _q_status,
        "qdrant_mode": qdrant_mode(),
        # ── Embedder ──
        "hf_inference": "ok" if settings.hf_token else "missing",
        "voyage":        "ok" if settings.voyage_api_key else "missing",
        # ── Reranker ──
        "cohere": _state("cohere", bool(settings.cohere_api_key)),
        # ── Tracing ──
        "langfuse": (
            "disabled" if not settings.langfuse_enabled
            else _state("langfuse", bool(settings.langfuse_public_key and settings.langfuse_secret_key))
        ),
        # ── 현재 활성 provider ──
        "active_llm":             settings.llm_provider,
        "active_embedder":        settings.embedder,
        "active_reranker":        settings.reranker,
        "fallback_chain_enabled": settings.llm_fallback_enabled,
        "provider_timeout_sec":   settings.llm_provider_timeout_sec,
    }


def log_status():
    """서버 시작 시 연결 상태 로깅."""
    s = status()
    lines = ["[connections] API 연결 상태:"]
    groups = {
        "LLM":      ["gemini", "deepseek", "openai", "anthropic", "ollama"],
        "VectorDB": ["qdrant", "qdrant_mode"],
        "Embedder": ["hf_inference", "voyage"],
        "Reranker": ["cohere"],
        "Tracing":  ["langfuse"],
        "Active":   ["active_llm", "active_embedder", "active_reranker",
                     "fallback_chain_enabled", "provider_timeout_sec"],
    }
    for group, keys in groups.items():
        for k in keys:
            v = s.get(k, "?")
            icon = "✅" if v in ("ok", True) else ("⚠️" if v in ("missing", "disabled") else "❌")
            lines.append(f"  {icon} {group}/{k}: {v}")
    logger.info("\n".join(lines))


# ─── 편의 싱글턴 ─────────────────────────────────────────────────────────────
# `from ..connections import connections` 로 임포트 후 conn.gemini() 등으로 사용
class _ConnectionRegistry:
    gemini = staticmethod(gemini)
    deepseek = staticmethod(deepseek)
    openai_client = staticmethod(openai_client)
    anthropic = staticmethod(anthropic)
    ollama_base_url = staticmethod(ollama_base_url)
    qdrant = staticmethod(qdrant)
    hf_inference = staticmethod(hf_inference)
    voyage = staticmethod(voyage)
    cohere = staticmethod(cohere)
    langfuse = staticmethod(langfuse)
    status = staticmethod(status)
    log_status = staticmethod(log_status)


connections = _ConnectionRegistry()
