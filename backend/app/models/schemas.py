"""Pydantic 모델 - 요청/응답 스키마.
/retrieval 은 Dify External Knowledge API 스펙을 정확히 따른다:
  https://docs.dify.ai/en/guides/knowledge-base/connect-external-knowledge-base/external-knowledge-api-documentation
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-25 00:00
# Task: Cross-lingual RAG 지원 — ChatRequest/ChatResponse 에 target_lang 추가 (ko/en/zh)
# Reason: 한국어 코퍼스를 단일 소스로 유지하면서 다국어 질의·응답 지원
# Related: ORDERS Cross-lingual RAG (다른 AI 추천 오더 + 사용자가 ja→zh 로 수정)
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-1 — 분류 모듈용 Enum 4종 + InputClassification 모델 신설
# Reason: ORDERS_COUNSELING.md G-1 — 상담 품질 분류기 기반 데이터 모델
# Related: services/classifier.py (NEW), api/chat.py (MODIFY)
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
from enum import Enum
from typing import Any, Literal, Optional  # ✏️ AI-CHANGE 2026-05-25 [Claude]: Literal 추가 — target_lang 타입 안전성

from pydantic import BaseModel, Field, field_validator


# ===== G-1: 분류 Enum + InputClassification =====
# ✏️ AI-CHANGE 2026-05-26 [Claude]: EPIC G-1 — 4차원 상담 입력 분류기 데이터 모델

class Clarity(str, Enum):
    clear = "clear"
    ambiguous = "ambiguous"


class Tone(str, Enum):
    calm = "calm"
    distressed = "distressed"
    rude = "rude"
    mocking = "mocking"
    hostile = "hostile"


class SpiritualError(str, Enum):
    none = "none"
    ghost_doctrine = "ghost_doctrine"                  # 죽은 자 = 귀신 류
    superstition = "superstition"                      # 미신적 영 해석
    exaggerated_demonology = "exaggerated_demonology"  # 과장된 귀신론·축사 집착
    legalism = "legalism"                              # 행위 중심 율법주의


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"                                  # 자해/폭력/과복용/금단/정신 붕괴


class InputClassification(BaseModel):
    clarity: Clarity = Clarity.clear
    tone: Tone = Tone.calm
    spiritual_error: SpiritualError = SpiritualError.none
    risk_level: RiskLevel = RiskLevel.low
    rationale: str = ""                                # 디버깅용 1문장


# ===== /chat =====
class ChatMessage(BaseModel):
    role: str
    content: str


# ✏️ AI-CHANGE 2026-05-25 [Claude]: 다국어 RAG 지원 언어 코드 — ko(한국어 원본) / en(영어) / zh(중국어 간체)
TargetLang = Literal["ko", "en", "zh"]


class ChatRequest(BaseModel):
    query: str = Field(..., description="사용자 질문 (공백 불가)")
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query must not be empty or whitespace-only")
        return v
    llm_provider: Optional[str] = None       # 런타임에 LLM 스왑
    embedder: Optional[str] = None            # 런타임에 임베더 스왑
    user_id: Optional[str] = None             # Langfuse user 추적용
    debug: bool = False
    # ✏️ AI-CHANGE 2026-05-25 [Claude]: Cross-lingual RAG — 응답 언어. ko=원본, en=영어, zh=중국어(간체)
    target_lang: TargetLang = "ko"


class SourceItem(BaseModel):
    id: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyInfo(BaseModel):
    input_allowed: bool
    input_severity: str = "ok"
    input_flags: list[str] = Field(default_factory=list)
    output_pass: bool = True
    output_score: float = 1.0
    output_notes: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    policy: PolicyInfo
    llm_provider: str
    llm_model: str
    embedder: str
    elapsed_ms: int
    trace_id: Optional[str] = None
    interaction_id: Optional[str] = None
    debug_info: Optional[dict] = None
    # ✏️ AI-CHANGE 2026-05-25 [Claude]: 응답에도 target_lang 노출 — 프론트 캐시 키/디버그용
    target_lang: TargetLang = "ko"


# ===== /retrieval (Dify External Knowledge API) =====
class DifyRetrievalSetting(BaseModel):
    top_k: int = 5
    score_threshold: float = 0.0


class DifyRetrievalRequest(BaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: DifyRetrievalSetting = DifyRetrievalSetting()
    metadata_condition: Optional[dict[str, Any]] = None  # Dify 1.1+


class DifyRecord(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float
    title: str
    content: str


class DifyRetrievalResponse(BaseModel):
    records: list[DifyRecord]


class DifyError(BaseModel):
    error_code: int
    error_msg: str


# ===== /ingest =====
class IngestTextRequest(BaseModel):
    text: str
    title: str = "untitled"
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedders: Optional[list[str]] = None    # None → settings.embedders 전체에 ingest


class IngestResult(BaseModel):
    embedder: str
    chunks: int
    points: int


class IngestResponse(BaseModel):
    title: str
    results: list[IngestResult]


# ===== /eval/ab =====
class EvalABRequest(BaseModel):
    queries: list[str]
    embedders: Optional[list[str]] = None
    top_k: int = 5


class EvalABItem(BaseModel):
    embedder: str
    query: str
    sources: list[SourceItem]


class EvalABResponse(BaseModel):
    items: list[EvalABItem]


class EvalGenerateRequest(BaseModel):
    doc_dir: Optional[str] = None
    max_per_doc: int = 3
    merge: bool = False
    save: bool = True


class EvalGenerateResponse(BaseModel):
    ok: bool
    count: int = 0
    questions: list[dict[str, Any]] = Field(default_factory=list)
    saved_path: Optional[str] = None
    reason: Optional[str] = None


class EvalTuneWeightsRequest(BaseModel):
    embedder: Optional[str] = None
    top_k: int = 5
    dense_grid: Optional[list[float]] = None
    sparse_grid: Optional[list[float]] = None


class EvalTuneWeightsResponse(BaseModel):
    ok: bool
    best: Optional[dict[str, Any]] = None
    current: Optional[dict[str, Any]] = None
    trials: list[dict[str, Any]] = Field(default_factory=list)
    env_hint: Optional[str] = None
    reason: Optional[str] = None


# ===== /auth =====

class SignupReq(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    guest_sub_id: Optional[str] = None   # 기존 guest 대화 승계


class LoginReq(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    sub_id: str
    token: str
    subscription_tier: str
    tokens_bonus: int
    tokens_monthly: int
    tokens_daily: int
    display_name: Optional[str]
    is_new: bool


# ===== /chat (추가 모델) =====

class FeedbackRequest(BaseModel):
    interaction_id: str
    value: int
    user_id: Optional[str] = None


class GreetingResponse(BaseModel):
    greeting: str
    mode_used: str              # "rule" | "llm"
    days_since_last_visit: Optional[int]
    is_first_visit: bool
    subscriber_id: str


# ===== /documents =====

class DraftMetaIn(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    topic_tags: Optional[list[str]] = None
    scripture_refs: Optional[list[str]] = None
    checklist: Optional[dict] = None


class DocMetaIn(BaseModel):
    """document 레벨 메타 (버전 독립) — speaker / series / doc_type."""
    speaker: Optional[str] = None
    series: Optional[str] = None
    doc_type: Optional[str] = None


class BodyPatchIn(BaseModel):
    body: str


class DocumentSummary(BaseModel):
    doc_id: str
    doc_key: str
    doc_type: str
    title: str
    series: Optional[str]
    speaker: Optional[str]
    is_canonical: bool
    latest_version: int
    latest_state: str
    published_version: Optional[int]
    updated_at: str


class VersionDetail(BaseModel):
    version_id: str
    doc_id: str
    version_number: int
    state: str
    title: str
    summary: Optional[str]
    topic_tags: list[str]
    scripture_refs: list[str]
    body_patch: Optional[str]
    jsonl_path: Optional[str] = None
    extracted_text_preview: str
    extraction_quality_score: int
    extraction_warnings: dict
    checklist: dict


class CleanupIn(BaseModel):
    stages: list[int] = Field(default_factory=lambda: [5])   # 용어 추출만
    dry_run: bool = False


class BulkActionIn(BaseModel):
    doc_ids: list[str]
    action: str  # "publish" | "archive"


# ===== /drafts =====

class DraftIn(BaseModel):
    draft_body: Optional[str] = None
    draft_meta: Optional[dict] = None
    device_id: str = "browser"
    operator_id: str = "admin"


# ===== /glossary =====

class ApproveIn(BaseModel):
    is_theology: bool = False
    definition: Optional[str] = None
    category: Optional[str] = None


class MergeIn(BaseModel):
    alias_ids: list[int]


class PatchTermIn(BaseModel):
    definition: Optional[str] = None
    category: Optional[str] = None
    canonical_form: Optional[str] = None
    is_theology_term: Optional[bool] = None


# ===== /memory =====

class FeedbackIn(BaseModel):
    value: int  # +1 / -1 / 0


# ===== /prompts =====

class PromptIn(BaseModel):
    content: str
    note: Optional[str] = None


# ===== /subscribers =====

class UserProfileUpdateReq(BaseModel):
    """일반 사용자가 직접 수정할 수 있는 필드만 포함."""
    display_name: Optional[str] = None
    journey_stage: Optional[str] = None
    faith_stage: Optional[str] = None
    emotional_state: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    current_struggle: Optional[str] = None
    preferred_tone: Optional[str] = None
    is_darakbang_member: Optional[bool] = None
    darakbang_chapter: Optional[str] = None
    consent_data: Optional[bool] = None
    consent_kakao: Optional[bool] = None


class ProfileUpdateReq(BaseModel):
    """운영자용 전체 프로필 수정 (운영자 전용 필드 포함)."""
    display_name: Optional[str] = None
    journey_stage: Optional[str] = None
    faith_stage: Optional[str] = None
    emotional_state: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    current_struggle: Optional[str] = None
    preferred_tone: Optional[str] = None
    is_darakbang_member: Optional[bool] = None
    consent_data: Optional[bool] = None
    consent_kakao: Optional[bool] = None
    # 운영자 전용 필드
    salvation_status: Optional[str] = None
    assume_saved: Optional[bool] = None
    darakbang_role: Optional[str] = None
    darakbang_chapter: Optional[str] = None
    darakbang_verified: Optional[bool] = None


class AssumeSavedReq(BaseModel):
    value: bool
    reason: Optional[str] = None
    also_set_status: Optional[str] = None   # 동시에 salvation_status 변경 (선택)


class GrantTokensReq(BaseModel):
    sub_id: str
    amount: int
    reason: Optional[str] = None
