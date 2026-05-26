"""중앙 설정 (Pydantic Settings) - 모든 환경변수는 여기서만 접근."""
from __future__ import annotations
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # korean-gospel-ai/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- LLM ----
    llm_provider: Literal["gemini", "openai", "claude", "ollama", "deepseek"] = "gemini"
    llm_fallback_enabled: bool = True
    llm_fallback_chain: str = ""  # 비우면 primary + API 키 있는 provider 순
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-6"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # ---- Embedding ----
    embedder: Literal["kure", "bge_m3", "e5", "hf_inference", "voyage"] = "kure"
    embedder_list: str = "kure,bge_m3"  # CSV
    hf_token: Optional[str] = None
    voyage_api_key: Optional[str] = None

    @property
    def embedders(self) -> list[str]:
        return [e.strip() for e in self.embedder_list.split(",") if e.strip()]

    # ---- Vector store ----
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_prefix: str = "gospel"
    qdrant_sparse_enabled: bool = True

    # ---- Reranker ----
    reranker: Literal["bge_m3", "none", "cohere"] = "bge_m3"
    cohere_api_key: Optional[str] = None

    # ---- Retrieval ----
    retrieval_top_k: int = 20
    rerank_top_n: int = 5
    dense_weight: float = 0.7
    sparse_weight: float = 0.3

    # ---- Policy ----
    policy_enabled: bool = True
    policy_rules_path: str = "data/eval/policy_rules.yaml"

    # ---- Langfuse ----
    langfuse_enabled: bool = True
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # ---- Auth ----
    app_password: str = ""
    admin_api_key: str = "change-me"
    dify_api_key: str = "change-me"

    # ---- CORS ----
    # 콤마로 구분된 허용 origin 목록. 프로덕션에서는 실제 도메인으로 교체.
    cors_origins: str = "http://localhost:8501,http://localhost:8502,http://localhost:3000"

    # ---- EPIC D Feature Flags (.env 한 줄로 ON/OFF, 재배포 불필요) ----
    salvation_detection_enabled: bool = True    # D-C14: LLM 구원 신호 감지
    salvation_prompt_enabled: bool = True       # D-C18: 구원 상태별 시스템 프롬프트
    retriever_boost_enabled: bool = True        # D-C16: 구원·다락방 boost matrix
    legalism_check_enabled: bool = True         # D-C23: 율법주의·거짓확신 차단
    gospel_core_fallback_enabled: bool = True   # D-C24: 검색 0건시 gospel_core 자동 노출

    # ---- EPIC E: 토큰 쿼터 (E-A) + 봇 차단 (E-B) ----
    token_quota_enabled: bool = True            # False = 무제한 (개발·시범 모드)
    rate_limit_enabled: bool = True             # False = rate limit 비활성 (개발 모드)
    tokens_daily_guest: int = 5000              # 비가입자 일일 무료 풀
    tokens_monthly_member: int = 100_000        # 가입자 월간 풀
    tokens_monthly_supporter: int = 500_000     # 후원자 월간 풀
    tokens_monthly_darakbang: int = 200_000     # 다락방 멤버 월간 풀
    tokens_bonus_on_signup: int = 20_000        # 가입 보너스 (1회)
    token_estimate_per_request: int = 2000      # 요청 사전 차감 견적

    # ---- 기타 ----
    data_dir: str = "data/documents"
    log_level: str = "INFO"

    # ---- Helpers ----
    def collection_name(self, embedder_name: str) -> str:
        return f"{self.qdrant_collection_prefix}_{embedder_name}"

    @property
    def root_dir(self) -> Path:
        return ROOT_DIR


# 싱글턴
settings = Settings()
