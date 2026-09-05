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
    role: str = Field(..., max_length=20)
    content: str = Field(..., max_length=10000)


# ✏️ AI-CHANGE 2026-05-25 [Claude]: 다국어 RAG 지원 언어 코드 — ko(한국어 원본) / en(영어) / zh(중국어 간체)
# ✏️ 2026-08-14: "auto" 추가 — 질문 언어를 자동 감지해 답변 언어를 결정(LLM 자연 동작).
#   기존엔 target_lang="ko" 고정이라 영어/중국어 질문에도 한국어로 강제 답변했던 과도 제약 제거.
TargetLang = Literal["ko", "en", "zh", "ja", "auto"]


class ChatRequest(BaseModel):
    query: str = Field(..., max_length=2000, description="사용자 질문 (공백 불가, 최대 2000자)")
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)

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
    # ✏️ 2026-08-14: 기본값 "auto" — 질문 언어를 감지해 자동 결정(질문 언어대로 답변).
    target_lang: TargetLang = "auto"
    # ✏️ FIX: user_context — 프론트(Streamlit)가 saved_user_info 를 전달하는 필드.
    #   과거 스키마 누락으로 매 요청마다 조용히 드롭되던 문제 해결. 선택적 사용자 배경 정보.
    user_context: Optional[str] = Field(default=None, max_length=2000)
    # ✏️ 2026-07-29: 이중언어 병기 답변 — target_lang 이 ko 가 아닐 때 한국어 번역을
    #   함께 생성해 프론트에서 나란히(병기) 표시한다. 기본 False(모바일 등 영향 없음).
    bilingual: bool = False


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
    # ✏️ 2026-07-23: 일일 질문 할당량 잔여 정보 (프론트 표시용)
    quota: Optional[dict] = None
    # ✏️ 2026-07-29: 이중언어 병기 답변 — target_lang != ko 이고 bilingual=True 인 경우
    #   생성된 한국어 번역. 없으면 None.
    answer_parallel: Optional[str] = None


# ===== /retrieval (Dify External Knowledge API) =====
class DifyRetrievalSetting(BaseModel):
    top_k: int = 5
    score_threshold: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DifyRetrievalRequest(BaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: DifyRetrievalSetting = Field(default_factory=DifyRetrievalSetting)
    metadata_condition: Optional[dict[str, Any]] = None  # Dify 1.1+
    target_lang: TargetLang = "ko"


class DifyRecord(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float
    title: str
    content: str


class DifyRetrievalResponse(BaseModel):
    records: list[DifyRecord]
    query_analysis: Optional[dict[str, Any]] = None


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

class SignupReq(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    guest_sub_id: Optional[str] = None   # 기존 guest 대화 승계
    # ── 이용약관/개인정보 동의 (2026-08-18) ──
    # 필수: 가입 시 두 약관 모두 동의해야 함 (기본 False)
    terms_accepted: bool = False
    privacy_accepted: bool = False


class LoginReq(BaseModel):
    email: str
    password: str
    device_id: Optional[str] = None   # 기기 식별자 (세션 관리용, 2026-08-18)
    device_name: Optional[str] = None  # 기기 표시명 (예: "iPhone 15")


class AuthResponse(BaseModel):
    sub_id: str
    token: str
    display_name: Optional[str]
    is_new: bool
    email: Optional[str] = None  # 클라이언트(모바일/웹)가 계정 식별에 사용. Google 로그인 시 필수.
    email_verified: bool = False
    # 이메일 가입 시 인증 메일 발송 후 즉시 로그인하지 않도록 프론트에 안내 플래그 전달.
    email_verification_required: bool = False


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
    validation_report: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    published_at: Optional[str] = None
    dup_hits: list[dict] = Field(default_factory=list)



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


# ===== /memory =====

class FeedbackIn(BaseModel):
    value: int  # +1 / -1 / 0


# ===== /prompts =====

class PromptIn(BaseModel):
    content: str
    note: Optional[str] = None


# ===== /subscribers =====

class UserProfileUpdateReq(BaseModel):
    """일반 사용자가 직접 수정할 수 있는 필드만 포함.

    is_darakbang_member / darakbang_chapter 는 운영자 전용(_OPERATOR_ONLY)이므로
    본 스키마에서 제외되었습니다. 운영자 변경은 ProfileUpdateReq를 사용하세요.
    """
    display_name: Optional[str] = None
    journey_stage: Optional[str] = None
    faith_stage: Optional[str] = None
    emotional_state: Optional[str] = None
    age_group: Optional[str] = None
    gender: Optional[str] = None
    current_struggle: Optional[str] = None
    preferred_tone: Optional[str] = None
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
    email: Optional[str] = None
    # 봇 관리 필드
    flagged_as_bot: Optional[bool] = None
    bot_score: Optional[float] = None
    # 이메일 인증 / 티어 (2026-07-23)
    email_verified: Optional[bool] = None
    subscription_tier: Optional[str] = None  # free | standard | premium | lifetime
    is_lifetime_member: Optional[bool] = None


class AssumeSavedReq(BaseModel):
    value: bool
    reason: Optional[str] = None
    also_set_status: Optional[str] = None   # 동시에 salvation_status 변경 (선택)


# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: CodeBuddy
# Timestamp: 2026-07-16
# Task: 인기 Q&A 집계 & 통찰 시스템 — Pydantic 스키마
# Reason: 설계 문서 §12.12 기반 구현
# Status: IN_PROGRESS
# =============================================================================

# ── Enum ──

class EditField(str, Enum):
    question = "question"
    answer = "answer"
    root_cause = "root_cause"
    ai_diagnosis = "ai_diagnosis"
    best_answer = "best_answer"
    best_answer_why = "best_answer_why"
    reflection = "reflection"
    is_featured = "is_featured"
    is_hidden = "is_hidden"
    # ── 작업 W: 단편 설교 + 추천 추가질문 ──
    short_sermon_title = "short_sermon_title"
    short_sermon_text = "short_sermon_text"
    short_sermon_doc_id = "short_sermon_doc_id"
    suggested_followups = "suggested_followups"


class ReviewStatusEnum(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class InsightSection(str, Enum):
    root_cause = "root_cause"
    ai_diagnosis = "ai_diagnosis"
    best_answer_why = "best_answer_why"
    reflection = "reflection"


# ── 관리자 편집 API ──

class PatchTrendingReq(BaseModel):
    """PATCH /admin/trending/{snapshot_id} 요청."""
    field: EditField
    new_value: str | bool
    edit_reason: Optional[str] = Field(default=None, max_length=200)
    save_draft: bool = False
    force: bool = False


class RevertReq(BaseModel):
    """POST /admin/trending/{snapshot_id}/revert 요청."""
    field: EditField
    target_log_id: str
    reason: str = Field(min_length=10, max_length=500)


class ReviewInsightReq(BaseModel):
    """PATCH /admin/insight/{snapshot_id}/review 요청."""
    section: InsightSection
    approved: bool
    rejection_reason: Optional[str] = Field(default=None, min_length=10, max_length=500)

    @field_validator("rejection_reason")
    @classmethod
    def reject_needs_reason(cls, v, info):
        if info.data.get("approved") is False and not v:
            raise ValueError("반려 시 rejection_reason은 필수입니다 (최소 10자)")
        return v


class RegenerateReq(BaseModel):
    """POST /admin/insight/{snapshot_id}/regenerate 요청."""
    sections: list[InsightSection] = Field(default_factory=lambda: [
        InsightSection.root_cause,
        InsightSection.ai_diagnosis,
        InsightSection.best_answer_why,
        InsightSection.reflection,
    ])
    regenerate_all: bool = False
    model_override: Optional[str] = None
    additional_instruction: Optional[str] = Field(default=None, max_length=500)


class AskReq(BaseModel):
    """POST /admin/insight/{snapshot_id}/ask 요청 (추가 질문하기).

    반드시 유저의 질문과 해당 QA의 내용(위의 내용)을 근거로 한
    후속 질문이어야 하며, 단독적인 하나의 질문이 아니다.
    """
    question: str = Field(min_length=2, max_length=1000)


class BatchRegenerateReq(BaseModel):
    """POST /admin/insight/batch-regenerate 요청."""
    filter: Literal["all_pending", "all_rejected", "needs_regeneration"] = "all_pending"
    sections: list[InsightSection] = Field(default_factory=lambda: [
        InsightSection.root_cause,
        InsightSection.ai_diagnosis,
        InsightSection.best_answer_why,
        InsightSection.reflection,
    ])
    model_override: Optional[str] = None
    max_items: int = Field(default=20, ge=1, le=20)


# ── 응답 스키마 ──

class EditResponse(BaseModel):
    """PATCH /admin/trending/{snapshot_id} 응답."""
    ok: bool = True
    snapshot_id: str
    field: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    edited_by: Optional[str] = None
    edited_at: Optional[str] = None
    edit_log_id: Optional[str] = None
    diff_summary: Optional[str] = None
    review_status_updated: bool = False
    warnings: list[dict] = Field(default_factory=list)
    no_change: bool = False


class RevertResponse(BaseModel):
    """롤백 응답."""
    ok: bool = True
    snapshot_id: str
    field: str
    restored_from: str
    restored_value: Optional[str] = None
    reverted_at: str = ""


class ReviewResponse(BaseModel):
    """PATCH /admin/insight/{snapshot_id}/review 응답."""
    ok: bool = True
    snapshot_id: str
    section: str
    new_status: str
    rejection_reason: Optional[str] = None
    needs_regeneration: bool = False
    all_sections_reviewed: bool = False
    ready_for_user: bool = False


class RegenerateResponse(BaseModel):
    """통찰 재생성 응답."""
    ok: bool = True
    snapshot_id: str
    insight_version: int = 0
    generated_at: str = ""
    sections_generated: list[str] = Field(default_factory=list)
    sections_failed: list[str] = Field(default_factory=list)
    model_used: str = ""


class BatchRegenerateResponse(BaseModel):
    """일괄 재생성 응답."""
    ok: bool = True
    job_id: Optional[str] = None
    total_candidates: int = 0
    partial_success: bool = False
    succeeded: int = 0
    failed: int = 0
    errors: list[dict] = Field(default_factory=list)


class InsightStatsResponse(BaseModel):
    """GET /admin/insight/stats 응답."""
    total_snapshots: int = 0
    insight_coverage: dict = Field(default_factory=dict)
    edit_stats: dict = Field(default_factory=dict)
    model_quality: dict = Field(default_factory=dict)


class InsightQueueResponse(BaseModel):
    """GET /admin/insight/queue 응답."""
    pending_review: list[dict] = Field(default_factory=list)
    needs_correction: list[dict] = Field(default_factory=list)
    total_pending: int = 0
    total_needs_correction: int = 0


class EditHistoryResponse(BaseModel):
    """GET /admin/trending/{id}/history 응답."""
    snapshot_id: str
    question: str = ""
    total_edits: int = 0
    history: list[dict] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False


class TrendingDashboardResponse(BaseModel):
    """GET /admin/trending/dashboard 응답."""
    overview: dict = Field(default_factory=dict)
    top_questions: list[dict] = Field(default_factory=list)
    top_answers: list[dict] = Field(default_factory=list)
    chart_data: dict = Field(default_factory=dict)


class TrendingCardsResponse(BaseModel):
    """GET /trending/cards 응답."""
    cards: list[dict] = Field(default_factory=list)
    updated_at: str = ""


class InsightResponse(BaseModel):
    """GET /insight/{snapshot_id} 응답."""
    snapshot_id: str
    question: str = ""
    question_stats: dict = Field(default_factory=dict)
    insight_sections: dict = Field(default_factory=dict)
    short_sermon: Optional[dict] = None
    suggested_followups: list = Field(default_factory=list)


class TrendingAnswersResponse(BaseModel):
    """GET /trending/answers 응답."""
    items: list[dict] = Field(default_factory=list)
    updated_at: str = ""
