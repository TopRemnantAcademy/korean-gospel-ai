"""중앙 설정 (Pydantic Settings) - 모든 환경변수는 여기서만 접근."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Literal, Optional

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
    llm_provider: Literal["gemini", "openai", "claude", "ollama", "deepseek", "tencent", "nvidia"] = "gemini"
    llm_fallback_enabled: bool = True
    llm_fallback_chain: str = ""  # 비우면 primary + API 키 있는 provider 순
    llm_provider_timeout_sec: int = 90  # 1개 provider 최대 대기 시간 (초). reasoning 모델(deepseek-v4) 응답 ~78s 수용. 빠른(non-reasoning) 모델 사용 시 30~45로 하향 권장.
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

    # ---- Tencent Cloud Maas (DeepSeek-V4) ----
    tencent_api_key: Optional[str] = None
    tencent_model: str = "deepseek-v4-flash-202605"
    tencent_base_url: str = "https://tokenhub-intl.tencentcloudmaas.com/v1"
    tencent_temperature: float = 0.3        # TencentLLM.chat/stream 기본 temperature (config 구동)
    tencent_max_tokens: int = 1500          # TencentLLM.chat/stream 기본 max_tokens (config 구동)

    # ---- NVIDIA NIM (텍스트 채팅 폴백: Nemotron / DeepSeek-V4-Pro) ----
    nvidia_api_key: Optional[str] = None
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"  # 단일 모델 호환성용
    # ✅ 2026-07-24: 동일 base_url 안에서 여러 모델을 콤마로 나열.
    #   형식: "model" 또는 "model:별도_API_KEY" (별도 키가 필요한 모델은 :key 로 지정)
    #   연결 실패(5xx/429/timeout/무응답) 시 목록 순서대로 즉시 교체 사용.
    #   ⚠️ 이미지 생성 모델(diffusiongemma 등)은 텍스트 채팅 폴백에 넣지 말 것
    #      → 별도 nvidia_image_* 그룹으로 관리.
    nvidia_models: str = "nvidia/nemotron-3-ultra-550b-a55b,deepseek-ai/deepseek-v4-pro"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_enable_thinking: bool = False    # True 시 reasoning 활성 (지연시간 증가 — 채팅에는 비권장)

    @property
    def nvidia_model_list(self) -> list[tuple[str, str]]:
        """NVIDIA 텍스트 채팅 폴백 모델 목록 → [(model, api_key), ...] (첫 번째가 우선).

        ``nvidia_models`` 항목은 ``model`` 또는 ``model:API_KEY`` 형식.
        ``:key`` 가 없으면 ``nvidia_api_key``(공용 키)를 사용.
        """
        default_key = self.nvidia_api_key or ""
        items = [x.strip() for x in self.nvidia_models.split(",") if x.strip()]
        if not items:
            items = [self.nvidia_model]
        # 중복 제거하되 순서 유지
        seen = set()
        out: list[tuple[str, str]] = []
        for item in items:
            if ":" in item:
                model, key = item.split(":", 1)
                model, key = model.strip(), key.strip()
            else:
                model, key = item, default_key
            if model and model not in seen:
                seen.add(model)
                out.append((model, key))
        return out

    # ---- NVIDIA: Google DiffusionGemma (이미지 생성, 별도 키) — 참조용 설정 저장 ----
    # 붙여받은 NVIDIA 코드 스니펫에서 추출한 값만 보관. 이미지 생성 로직은 미구현.
    nvidia_image_api_key: Optional[str] = None
    nvidia_image_model: str = "google/diffusiongemma-26b-a4b-it"
    nvidia_image_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_image_enable_thinking: bool = True     # 스니펫 기본값
    nvidia_image_max_tokens: int = 4096           # 스니펫 기본값
    nvidia_image_temperature: float = 1.0         # 스니펫 기본값
    nvidia_image_top_p: float = 0.95              # 스니펫 기본값

    # ---- Embedding ----
    embedder: Literal["kure", "bge_m3", "e5", "hf_inference", "voyage", "hash"] = "kure"
    embedder_list: str = "kure,bge_m3"  # CSV
    hf_token: Optional[str] = None
    # Windows HF 캐시가 심링크(junction)로 깨져 로드 실패할 때 사용하는
    # KURE 실제 파일 복사본 로컬 경로. 비어 있으면 model_id(nlpai-lab/KURE-v1) 사용.
    kure_model_path: Optional[str] = None
    # bge-m3(다국어) 실제 파일 복사본 로컬 경로. 비어 있으면 model_id(BAAI/bge-m3) 사용.
    # Windows HF 캐시 심링크 깨짐 우회용 (kure_model_path 와 동일 목적).
    bge_m3_model_path: Optional[str] = None
    voyage_api_key: Optional[str] = None

    @property
    def embedders(self) -> list[str]:
        return [e.strip() for e in self.embedder_list.split(",") if e.strip()]

    # ---- Environment ----
    # dev / staging / prod. prod/staging 에서는 embedded Qdrant(local:) 사용 금지 (P1-1).
    app_env: str = "dev"  # env: APP_ENV

    # ---- Vector store ----
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_prefix: str = "gospel"
    qdrant_sparse_enabled: bool = True
    qdrant_grpc: str = ""  # "true" → gRPC 모드 (낮은 레이턴시, port 6334)

    # ---- Reranker ----
    # 로컬/오프라인 기본값은 none. 운영에서 HF 모델 캐시/네트워크가 준비되면 bge_m3 사용.
    reranker: Literal["bge_m3", "none", "cohere"] = "none"
    cohere_api_key: Optional[str] = None

    # ---- Retrieval ----
    retrieval_top_k: int = 20
    rerank_top_n: int = 5
    dense_weight: float = 0.7
    sparse_weight: float = 0.3
    rrf_k: int = 60                # Reciprocal Rank Fusion 상수 (dense+sparse 융합)
    # LLM 쿼리 확장(짧은 쿼리 → 동의어/의도 리라이트) 활성화 스위치.
    # 기본 False: 새로운 LLM 호출 경로가 검색 지연에 미치는 영향을 1차 배포에서
    # 차단하고, 명시적으로 켜야만 주检索链路에 확장 쿼리가 주입된다.
    search_expand_enabled: bool = False

    # ---- 성능 최적화 (RAG 응답 지연 개선) ----
    # 1) 벡터 검색 범위 축소: 채팅처럼 top_k 가 작은 경우 recall_k 를 200 고정 말고
    #    top_k 에 비례시켜 Qdrant 탐색량을 줄인다. (기존 200 → 동적)
    recall_k_floor: int = 80          # recall_k 하한 (기존 200 → 80)
    recall_k_per_topk: int = 3        # recall_k = max(top_k * 이값, floor)
    # 2) 다중 쿼리(확장쿼리)별 recall 분산: 2번째 쿼리부터는 recall_k 를 줄여
    #    전체 Qdrant 호출량을 감축. (1번째=100%, 2번째=60%, 3번째=40%)
    multi_query_recall_decay: float = 0.6
    # 3) Qdrant ef_search 상한 축소 (기존 256 → 128): 탐색 품질 약화 없이 속도 향상
    ef_search_cap: int = 128
    # 4) 상위 K 컨텍스트 토큰 예산 (프롬프트 토큰 감소)
    context_max_tokens: int = 900     # LLM 프롬프트에 주입할 컨텍스트 토큰 상한
    context_top_k: int = 3            # 빌드프롬프트에서 사용할 상위 문서 수
    # 5) LLM max_tokens 축소 (기존 1000 → 700): 첫 토큰(TTFT) 이후 종료도 빨라짐
    chat_max_tokens: int = 700
    # 6) FAQ 정적 캐시 활성화 (자주 묻는 질문 사전 저장)
    faq_cache_enabled: bool = True
    faq_cache_ttl_sec: int = 86400     # 24시간
    faq_min_hits: int = 3             # 이 횟수 이상 반복된 쿼리만 정적 캐시 후보
    # 6b) 생성 답변 캐시 (P4 #1): 정규화 키 + TTL. FAQ 정확캐시와 별도.
    answer_cache_enabled: bool = True
    answer_cache_ttl_sec: int = 600   # 10분
    redis_url: Optional[str] = None   # 설정 시 Redis 공유 캐시(다중 worker 일관성), 미설정 시 프로세스 내 TTL

    # ---- Policy ----
    policy_enabled: bool = True
    policy_rules_path: Optional[str] = None   # None → 기본 후보 경로 사용 (data/eval/policy_rules.yaml, data/policy/policy_rules.yaml)

    # ---- Rate Limiting ----
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60           # IP 분당 최대 요청 수 (/chat 경로에만 적용, 초과 시 15분 차단)
    rate_limit_trust_proxy: bool = True       # 프록시(Cloudflare 등) 뒤 X-Forwarded-For 에서 실제 클라이언트 IP 사용 (P4 #3)

    # ---- Langfuse ----
    langfuse_enabled: bool = True
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # ---- Auth ----
    app_password: str = ""
    admin_api_key: str = "change-me"
    dify_api_key: str = "change-me"
    auth_secret: str = ""
    google_client_id: str = ""  # Google OAuth 2.0 Client ID (비워두면 Google 로그인 비활성화)

    # ---- PortOne 결제 게이트웨이 (V2) ----
    # store_id / api_secret 은 PortOne 콘솔에서 발급. api_secret 는 서버 전용(절대 클라이언트 노출 금지).
    # channel_key 는 결제 수단(카드/간편결제 등)별로 PortOne 콘솔에서 발급 — 미설정 시 결제 생성 실패.
    portone_store_id: str = ""              # PortOne Store ID (store-xxxx)
    portone_api_secret: str = ""            # API Secret (/login/api-secret 로 액세스 토큰 발급)
    portone_channel_key: str = ""           # 결제 채널 키 (PG 방법별, PortOne 콘솔 발급)
    portone_api_base: str = "https://api.portone.io"   # PortOne V2 API 베이스 URL
    portone_webhook_secret: str = ""        # 웹훅 서명 검증용 시크릿 (설정 시 HMAC-SHA256 검증)

    # ---- CORS ----
    # 콤마로 구분된 허용 origin 목록. 프로덕션에서는 실제 도메인으로 교체.
    cors_origins: str = "http://localhost:8501,http://127.0.0.1:8501,http://localhost:8502,http://127.0.0.1:8502,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5000,http://127.0.0.1:5000,http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173,http://localhost:4174,http://127.0.0.1:4174,capacitor://localhost,https://localhost,https://app.gospelai.local,http://app.gospelai.local"

    # ---- EPIC D Feature Flags (.env 한 줄로 ON/OFF, 재배포 불필요) ----
    classify_input_enabled: bool = True          # G-1: LLM 입력 분류 (false = 기본값 사용, Gemini API 쿼터 절약)
    salvation_detection_enabled: bool = True    # D-C14: LLM 구원 신호 감지
    salvation_prompt_enabled: bool = True       # D-C18: 구원 상태별 시스템 프롬프트
    retriever_boost_enabled: bool = True        # D-C16: 구원·다락방 boost matrix
    legalism_check_enabled: bool = False        # D-C23: 응답 속도 우선 — 율법주의는 백그라운드 심사(_bg_judge)로 충분
    gospel_core_fallback_enabled: bool = True   # D-C24: 검색 0건시 gospel_core 자동 노출
    greeting_fastpath_enabled: bool = True       # OPT-SPEED: 순수 인사/잡담은 RAG(분류 LLM+임베딩+Qdrant) 건너뛰고 LLM 즉시 응답. 첫 메시지 병목(TTFT 7~11s) 제거. GREETING_FASTPATH_ENABLED=false 로 비활성.

    # ---- Grounding (환각 차단 검증 / SourceGroundingVerifier) ----
    grounding_verify_enabled: bool = True      # 생성 답변의 근거 귀속 검증 사용
    grounding_verify_mode: str = "monitor"     # "monitor"(백그라운드, 응답 지연 0) | "enforce"(동기, 미통과 시 안전 응답)
    grounding_verify_timeout: float = 4.0      # enforce 모드 호출 타임아웃(초) — 지연 bound

    # ---- Enhanced RAG: 이중 저장(한국어 원문 보존 + 중국어 우선) ----
    rag_bilingual_enabled: bool = True          # 결정: 중국어 사용자 다수 가정 → 중국어 우선 dual-storage 기본 활성 (RAG_BILINGUAL_ENABLED=false 로 비활성)
    rag_enhanced_enabled: bool = False          # P1-2: 채팅 경로에서 enhanced_rag 이중 엔진 게이팅. 기본 off = 단일 retriever만 사용(검색/비용 2배 방지). true 로 재활성 가능(오프라인 Recall 비교 후)

    # ---- 트렌딩 인기 QA: 의미론적 클러스터링 (증분 강화) ----
    # 기본 off: 기존 "정규화+키워드 병합"만으로 충분히 표시됨. on(=true) 시 백그라운드
    # 스케줄러가 당주 고빈도 질문에 bge_m3(다국어) 코사인 Union-Find 를 적용해 횡단 언어
    # 동의어(예: "怎么祷告"↔"기도 어떻게")를 하나의 클러스터 대표 질문으로 병합.
    # 모델/네트워크 미사용 환경에서는 자동 no-op (안전 강등).
    trending_semantic_cluster: bool = False

    token_estimate_per_request: int = 2000

    # ---- INGEST 파이프라인 (문서 재편집 + 청킹) ----
    # 각 단계 .env 한 줄로 ON/OFF. LLM 단계는 DeepSeek 등 chat_with_fallback 경유.
    ingest_normalize_enabled: bool = True        # Stage 1: 구어체 정리 (규칙, 빠름)
    ingest_restructure_enabled: bool = True      # Stage 2: 섹션헤딩+문어체 (LLM, 구어체→문어체)
    ingest_contextual_enabled: bool = True       # Stage 4: 청크 맥락 강화 (LLM, 검색정확도↑)
    ingest_quality_gate_enabled: bool = True     # Stage 7: 품질 검증·차단 (규칙)
    ingest_chunk_target_tokens: int = 350        # 청크 목표 토큰
    ingest_chunk_max_tokens: int = 512           # 청크 최대 토큰 (임베더 한도)
    ingest_chunk_min_tokens: int = 50            # 이 미만은 인접 청크에 병합
    ingest_chunk_overlap: int = 2                # 인접 청크 오버랩 문장 수 (취약점 4: 1→2)
    ingest_restructure_window_chars: int = 3000  # 구조화 LLM 윈도우 크기

    # ---- 기타 ----
    max_upload_size_mb: int = 100               # P4: 대용량 파일 업로드 제한
    data_dir: str = "data/documents"
    log_level: str = "INFO"

    # ---- Swagger / OpenAPI ----
    # 프로덕션에서는 false 로 설정해 /docs·/openapi.json 노출 차단 (env 게이트)
    docs_enabled: bool = True

    # ---- 데이터베이스 ----
    # None → SQLite 파일 (.gospel.db). Postgres 전환 시 postgresql://... URL 설정.
    database_url: Optional[str] = None

    # ---- Web Push (VAPID) ----
    # VAPID 키쌍. 비어 있으면 push_service 가 자동 생성 후 .vapid_keys 에 저장.
    vapid_public_key: Optional[str] = None
    vapid_private_key: Optional[str] = None
    vapid_subject: str = "mailto:admin@example.com"
    # PUSH_ENABLED=true 일 때만 push_scheduler 가 매일 PUSH_HOUR_KST 시(KST) 발송.
    push_enabled: bool = False
    push_hour_kst: int = 7
    # 미디어 "저녁 배치 알림" 발송 시각 (KST). 관리자가 알림 모드를 'batch'로 올리면
    # 이 시각에 묶어서 한 번만 푸시 발송 (알림 폭탄 방지).
    media_notify_evening_hour_kst: int = 21

    # ---- Token Quota (토큰 할당량) ----
    # False(기본) → 무제한 스텁 유지(기존 동작과 동일).
    # True → Subscriber.tokens_daily/monthly 기반 일/월간 할당량 강제.
    token_quota_enabled: bool = False
    token_quota_default: int = 20000            # 일일 기본 할당량(토큰)
    token_quota_monthly: int = 200000           # 월간 기본 할당량(토큰)

    # ---- Email / SMTP (이메일 인증 발송, 2026-07-23) ----
    # email_mode: 'smtp' → 실제 발송 / 'console' → 링크만 로그 출력(발송 안 함, dev/test)
    email_mode: str = "console"
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_tls: bool = True            # STARTTLS 사용
    mail_from: str = "noreply@gospel.example.com"
    mail_from_name: str = "복음 AI"
    # 이메일 인증 정책: 미인증 로그인 차단. 단 email_mode='console' 이면 강제 통과(운영 안전판).
    require_email_verification: bool = True
    email_verify_token_ttl_hours: int = 24
    email_verify_resend_seconds: int = 60

    # ---- Question Quota (일일 질문 수 티어 할당량, 2026-07-23) ----
    # 익명(IP) 1회/일, 로그인 무료 10, standard 50, premium 200, 평생 무한.
    question_quota_enabled: bool = True
    quota_anonymous_daily: int = int(os.getenv("QUOTA_ANONYMOUS_DAILY", "1"))
    quota_free_daily: int = int(os.getenv("QUOTA_FREE_DAILY", "10"))
    quota_standard_daily: int = int(os.getenv("QUOTA_STANDARD_DAILY", "50"))
    quota_premium_daily: int = int(os.getenv("QUOTA_PREMIUM_DAILY", "200"))
    quota_lifetime_daily: int = 999999

    # ---- Welcome / UI ----
    # 오늘의 말씀(환영 구절) 기본 텍스트. GET /mobile/verse/daily 로 노출.
    welcome_verse: str = (
        "요한복음 3:16 — 하나님이 세상을 이처럼 사랑하사 독생자를 주셨으니 "
        "이는 그를 믿는 자마다 멸망하지 않고 영생을 얻게 하려 하심이라"
    )

    # ---- Mobile App Version Gate (2026-08-01) ----
    # 클라이언트가 GET /mobile/app-config 로 조회. versionCode 가
    # mobile_min_version_code 미만이면 강제 업데이트(force_update=true).
    # Android/Capacitor 빌드 시 mobile/version.json 과 버전을 맞춰야 함.
    mobile_min_version_code: int = 1
    mobile_latest_version_code: int = 1
    mobile_latest_version_name: str = "1.0.0"
    mobile_update_url: str = ""  # 강제/권장 업데이트 시 이동할 APK 다운로드 URL(비우면 download.html)

    # ---- Helpers ----
    def collection_name(self, embedder_name: str) -> str:
        return f"{self.qdrant_collection_prefix}_{embedder_name}"

    @property
    def root_dir(self) -> Path:
        return ROOT_DIR


# 싱글턴
settings = Settings()
