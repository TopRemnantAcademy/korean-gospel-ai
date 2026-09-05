"""SQLAlchemy ORM 모델 — 13개 테이블.

설계는 SETUP 문서 §3 데이터 모델과 1:1 매칭.
"""

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Antigravity
# Timestamp: 2026-05-19 09:05
# Task: D-C12 salvation_status + D-C13 darakbang 3단 + D-C17 Document salvation meta + D-C19 SalvationJourney
# Reason: EPIC D Phase 1 ORM 확장 — 구원 중심 + 다락방 깊이 기술 통합
# Related: ORDERS D-C12, D-C13, D-C17, D-C19, B6
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------- Enums ----------------
class DocType(str, enum.Enum):
    sermon = "sermon"
    book = "book"
    bible = "bible"
    testimony = "testimony"
    prayer = "prayer"
    healing = "healing"
    other = "other"


class DocVersionState(str, enum.Enum):
    draft = "draft"
    validated = "validated"
    published = "published"
    superseded = "superseded"
    archived = "archived"


# ---------------- L1: SourceArtifact (immutable) ----------------
class SourceArtifact(Base):
    """업로드 원본 + 추출 텍스트. 한 번 만들어지면 절대 안 바뀜."""

    __tablename__ = "source_artifact"

    artifact_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    original_filename: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    extracted_text: Mapped[str] = mapped_column(Text)
    extraction_quality_score: Mapped[int] = mapped_column(Integer, default=0)  # 0~100
    extraction_warnings: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    storage_path: Mapped[str] = mapped_column(String(500))  # 로컬 파일 경로
    uploaded_by: Mapped[str] = mapped_column(String(100), default="admin")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------- Document (논리적 묶음) ----------------
class Document(Base):
    """여러 버전을 묶는 논리적 문서. doc_key 가 안정 ID."""

    __tablename__ = "document"

    doc_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    doc_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(40), default=DocType.sermon.value)
    series: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    speaker: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    preached_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


# ---------------- L2: DocumentVersion ----------------
class DocumentVersion(Base):
    """문서의 한 시점. draft일 때만 가변. published 후 immutable."""

    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("doc_id", "version_number", name="uq_doc_version"),
    )

    version_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("document.doc_id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("source_artifact.artifact_id"))

    state: Mapped[str] = mapped_column(
        String(20), default=DocVersionState.draft.value, index=True
    )

    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scripture_refs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    topic_tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    target_audience: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    target_stage: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    emotion_tone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    difficulty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    length_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ✅ D-C17: 구원 단계별 자료 분류 메타
    target_salvation_stage: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # ["seeker"] | ["uncertain", "assured"] | ["mature"] 등
    # 카테고리: seeker | uncertain | assured | mature | gospel_core | assurance | discipleship | leadership | pastoral
    darakbang_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # None | darakbang_general | darakbang_deep | darakbang_leader
    # None = 일반 자료, darakbang_* = 다락방 식구에게만 추천
    salvation_focus_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 0.0~1.0 — 이 자료가 *직접 구원의 핵심* 을 다루는 정도
    gospel_core_tag: Mapped[bool] = mapped_column(Boolean, default=False)
    # "이 자료는 구원의 핵심 자료" — 운영자가 직접 표시

    body_patch: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 마이크로 패치된 본문 (null=원본 그대로)
    structured_body: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # INGEST Stage 2 구조화 산출물 (null=미처리)
    chunking_policy: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    checklist: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    validation_report: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    document: Mapped[Document] = relationship(back_populates="versions")
    artifact: Mapped[SourceArtifact] = relationship()
    snapshot: Mapped[Optional["IndexSnapshot"]] = relationship(
        back_populates="version", uselist=False
    )


# ---------------- L3: IndexSnapshot ----------------
class IndexSnapshot(Base):
    """publish 시점에 자동 생성. Qdrant 동기화 메타."""

    __tablename__ = "index_snapshot"

    snapshot_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_version.version_id"), unique=True
    )
    collection_name: Mapped[str] = mapped_column(String(200))
    embedder_name: Mapped[str] = mapped_column(String(100))
    embedder_version: Mapped[str] = mapped_column(String(50), default="v1")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    version: Mapped[DocumentVersion] = relationship(back_populates="snapshot")


# ---------------- Subscriber (관제탑 + EPIC D 확장) ----------------
class Subscriber(Base):
    __tablename__ = "subscriber"

    subscriber_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    auth_status: Mapped[str] = mapped_column(String(20), default="anonymous")
    email: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, unique=True
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    journey_stage: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    faith_stage: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    emotional_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    age_group: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    current_struggle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_tone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    consent_data: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_kakao: Mapped[bool] = mapped_column(Boolean, default=False)
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    tokens_daily: Mapped[int] = mapped_column(Integer, default=0)
    tokens_monthly: Mapped[int] = mapped_column(Integer, default=0)
    tokens_bonus: Mapped[int] = mapped_column(Integer, default=0)
    tokens_lifetime_used: Mapped[int] = mapped_column(Integer, default=0)
    # Token Quota 주기 리셋 기준일. tokens_daily_reset=YYYY-MM-DD, tokens_monthly_reset=YYYY-MM
    tokens_daily_reset: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    tokens_monthly_reset: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    last_emotion: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    is_darakbang_member: Mapped[bool] = mapped_column(Boolean, default=False)
    is_believer: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_as_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_score: Mapped[float] = mapped_column(Float, default=0.0)
    subscription_tier: Mapped[str] = mapped_column(String(20), default="free")

    # ✅ D-C12: 구원 상태 1급 변수
    salvation_status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    # unknown    | 시스템이 모름 (신규, 미상호작용) — 기본값
    # seeker     | 구원 모름·관심 단계
    # uncertain  | 들었으나 확신 없음 (98% 가 여기) — 시스템의 DEFAULT TARGET
    # assured    | 구원의 확신 있음 (요5:24, 요일5:13)
    # mature     | 확신 + 열매 + 제자훈련 + 사역
    salvation_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # 0.0~1.0 — 시스템이 이 분류를 얼마나 확신하는가
    salvation_last_signal_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    # 구원 관련 마지막 발화 시간
    assume_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    # 운영자가 "이 사람 구원받았다 치고 대화하라" 설정 시 True
    # 기본 False — 시스템은 *아직 구원 못 받았다는 전제로* 대화

    # ✅ D-C13: 다락방(Darakbang) 3단 필드
    darakbang_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # member | leader | pastor | guest
    darakbang_chapter: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # 예: "서울-강남", "분당-야탑", "온라인"
    darakbang_joined_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    darakbang_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # 운영자가 "이 사람 진짜 다락방 식구 맞다" 확인

    topic_interests: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    consent: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # BUG-09 후속(DB): get_all_subscribers 가 order_by(last_active_at.desc()) 를 수행하므로
    # 대량 사용자 환경에서 풀스캔을 막기 위해 인덱스 추가.
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, index=True
    )

    # ── 이메일 인증 (2026-07-23 추가) ──────────────────────────────────────
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verify_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    email_verify_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # ── 평생 회원 (2026-07-23 추가) ────────────────────────────────────────
    is_lifetime_member: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ── 구독 만료일 (2026-07-29 추가) ──────────────────────────────────────
    # standard/premium 구독의 만료일. free/lifetime 는 미사용(None).
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 종교 분류 (사용자 선택 또는 온보딩에서 자동 감지)
    religion: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # 기독교 | 불교 | 무교 | 이슬람 | 기타
    denomination: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # 기독교일 때만 사용: 장로교|감리교|침례교|순복음|성결|기타
    # 다락방은 denomination 에 속하지 않음 — is_darakbang_member 필드로 별도 관리


# ---------------- Payment (PortOne 결제 내역, 2026-07-30 추가) ----------------
class Payment(Base):
    """PortOne 결제 1건. prepare(대기) → paid(완료)/failed/cancelled.

    subscriber_id 로 구독자와 연결. 결제 완료 시 subscriber.subscription_tier +
    subscription_expires_at 가 갱신됨 (api/payment.py _upgrade).
    """

    __tablename__ = "payment"

    payment_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("subscriber.subscriber_id"), index=True
    )
    plan_id: Mapped[str] = mapped_column(String(40))            # standard_monthly 등
    tier: Mapped[str] = mapped_column(String(20))               # standard|premium|lifetime
    amount: Mapped[int] = mapped_column(Integer, default=0)     # KRW
    currency: Mapped[str] = mapped_column(String(8), default="KRW")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    portone_payment_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True
    )
    portone_tx_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )


# ---------------- QuestionQuota (일일 질문 수 할당량, 2026-07-23 추가) ----------------
class QuestionQuota(Base):
    """익명(IP) / 로그인 사용자(sub)별 일일 질문 수 카운터.

    키: 'ip:<ip>' (익명) 또는 'sub:<subscriber_id>' (로그인).
    date_str: 'YYYY-MM-DD' (KST). 자정 리셋.
    """

    __tablename__ = "question_quota"

    key: Mapped[str] = mapped_column(String(191), primary_key=True)
    date_str: Mapped[str] = mapped_column(String(10), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


# ---------------- AppSetting (런타임 설정 토글, 2026-07-23 추가) ----------------
class AppSetting(Base):
    """관리자 설정 페이지에서 런타임 변경되는 키-값 저장소.

    민감 값(SMTP 비밀번호 등)은 여기에 저장하지 않고 config/env 에만 둔다.
    """

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(16), default="str")  # str|int|bool
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---------------- Interaction ----------------
class Interaction(Base):
    """질문-답변 한 턴. cited_versions에 옛 답 재현 정보."""

    __tablename__ = "interaction"

    interaction_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    subscriber_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("subscriber.subscriber_id"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    cited_versions: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    feedback: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # +1/-1/null
    journey_signal: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    # ✅ Wave A: 위기 하드 바이패스 여부 (RiskLevel.urgent | CrisisLevel.critical 감지 시 True)
    # RAG/LLM 생성을 건너뛰고 결정적 안전 응답을 반환한 턴을 표시. 회귀/모니터링용.
    crisis_bypass: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # V-4: 검색 커버리지 부족 플래그 — cited 문서가 질문을 충분히 커버하지 못한 턴
    low_coverage: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, index=True)

    # ---- CCP(P1): 호출 1건당 원가 귀속 필드 --------------------------------
    # 모두 nullable: 과거 행 및 원가 산정이 불가능한 턴(fast-path, crisis_bypass,
    # 요율 미등록 provider)은 NULL 로 남기고, 집계 시 NULL 을 제외한다.
    # "0 으로 채우기"는 '원가 없음'과 '원가 0원'을 구분할 수 없게 만들어 금지.
    llm_provider: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    llm_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 계산 시점의 요율로 확정된 원가(KRW). 확정 후 요율이 바뀌어도 재계산하지 않는다.
    cost_krw: Mapped[Optional[Numeric]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    # 어떤 요율 카드로 계산했는지에 대한 감사 추적 링크(소명 자료의 핵심).
    rate_card_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


# ---------------- VerseAnnotation (말씀 하이라이트/북마크/메모) ----------------
class VerseAnnotation(Base):
    """성경 구절에 대한 사용자별 하이라이트/북마크/메모."""

    __tablename__ = "verse_annotation"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    subscriber_id: Mapped[str] = mapped_column(
        ForeignKey("subscriber.subscriber_id"), nullable=False, index=True
    )
    book: Mapped[str] = mapped_column(String(16), index=True)  # 예: 'psa', 'gen'
    chapter: Mapped[int] = mapped_column(Integer)
    verse: Mapped[int] = mapped_column(Integer)
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # yellow/green/blue/pink
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    __table_args__ = (
        Index("ix_verse_annotation_ref", "subscriber_id", "book", "chapter", "verse"),
    )


# ---------------- AuditLog (immutable) ----------------
class AuditLog(Base):
    """모든 state transition / publish / archive / 편집 기록. 절대 수정 X."""

    __tablename__ = "audit_log"

    log_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    who: Mapped[str] = mapped_column(String(100), default="admin")
    when: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    action: Mapped[str] = mapped_column(String(80))  # e.g. "version.publish"
    entity_type: Mapped[str] = mapped_column(String(40))  # "document_version"
    entity_id: Mapped[str] = mapped_column(String(40), index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    note: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# ---------------- PromptTemplate (운영자가 편집 가능) ----------------
class PromptTemplate(Base):
    """시스템 프롬프트 (active=1 인 행이 현재 사용됨)."""

    __tablename__ = "prompt_template"

    template_id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(100), default="gospel_default")
    content: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(100), default="admin")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------- Category (분류 체계) ----------------
class Category(Base):
    """신앙 단계, 감정 상태 등의 분류를 유연하게 관리하기 위한 테이블."""

    __tablename__ = "category"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    category_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # "faith_stage", "emotional_state", "tone" 등
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------- D-C19: SalvationJourney (구원 여정 타임라인) ----------------
# ✅ AI-CHANGE 2026-05-19 [Antigravity]: D-C19 신규 테이블 추가
class SalvationJourney(Base):
    """한 사람의 영적 여정을 시계열로 보관. 전환 기록 + 감사 추적."""

    __tablename__ = "salvation_journey"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscriber_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("subscriber.subscriber_id"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(16))  # 이전 단계
    to_status: Mapped[str] = mapped_column(String(16))  # 새 단계
    trigger_signal: Mapped[str] = mapped_column(
        String(20)
    )  # seeking|doubting|confessing|...
    trigger_quote: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 결정적 발화
    interaction_id: Mapped[Optional[str]] = mapped_column(
        String(40), ForeignKey("interaction.interaction_id"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    manual_override: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # 운영자 수동 변경
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------- AppErrorLog (런타임 에러 + 슬로우 리퀘스트 자동 기록) --------
class AppErrorLog(Base):
    """ErrorMonitorMiddleware 가 자동으로 기록하는 에러/슬로우리퀘스트 로그.

    level 값:
      ERROR    — HTTP 500+ 응답
      SLOW     — 응답 10~30초
      CRITICAL — 응답 30초 초과 또는 미처리 예외
    """

    __tablename__ = "app_error_log"

    error_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    level: Mapped[str] = mapped_column(String(10), index=True)  # ERROR|SLOW|CRITICAL
    method: Mapped[str] = mapped_column(String(10))  # GET|POST|...
    path: Mapped[str] = mapped_column(String(200), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    error_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


# ---------------- SupportTicket (사용자 신고/오류 제보) ----------------
class SupportTicket(Base):
    """사용자 신고/오류 제보. 클라+서버 이중 dedup 으로 스팸 방지 (P4 #8).

    type:  bug | report | abuse | error | other
    status: open | reviewing | resolved | dismissed
    """

    __tablename__ = "support_ticket"

    ticket_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    sub_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(16), index=True)
    target: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    contact: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    dedup_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------- BackgroundJob (비동기 작업 진행 상태 추적) ------------------
class BackgroundJob(Base):
    """업로드·공개 등 오래 걸리는 작업의 진행 상황을 실시간으로 기록.

    status: pending → running → done | failed
    progress_pct: 0~100 (프론트엔드 프로그레스바용)
    current_stage: 짧은 단계명 (예: "📄 텍스트 추출 중...")
    stage_detail: 세부 설명 (예: "12/120 페이지 처리")
    """

    __tablename__ = "background_job"

    job_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(30), index=True)  # upload|publish
    status: Mapped[str] = mapped_column(
        String(10), default="pending", index=True
    )  # pending|running|done|failed
    current_stage: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    stage_detail: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DocumentDraft(Base):
    """E-F: 운영자 편집 임시저장 — 서버 1겹."""

    __tablename__ = "document_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("document_version.version_id"), index=True
    )
    operator_id: Mapped[str] = mapped_column(String(60), default="admin")
    draft_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_meta: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, default=dict
    )
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    device_id: Mapped[str] = mapped_column(String(60), default="browser")
    conflict_resolved: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("version_id", "operator_id", name="uq_draft_ver_op"),
    )


# ---------------- ContentLink (영성훈련 콘텐츠 링크) ----------------
class ContentLink(Base):
    """영성훈련 콘텐츠 링크 — YouTube 강의, Spotify 찬양, 기타 외부 미디어.

    관리자가 Streamlit 페이지에서 등록/수정/삭제.
    모바일 앱의 영성훈련 탭에서 embed_url 로 미디어 재생.
    """

    __tablename__ = "content_link"
    __table_args__ = (
        # 공개 카탈로그 쿼리(active + order_index 정렬)를 위한 복합 인덱스
        Index("ix_content_link_active_order", "active", "order_index", "created_at"),
    )

    link_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(500))  # 원본 URL
    embed_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # 미리 변환된 임베드 URL
    lang: Mapped[str] = mapped_column(String(8), default="ko")  # ko|zh|en|ja — 모바일 언어별 콘텐츠 필터
    source: Mapped[str] = mapped_column(String(20), default="other")
    # youtube | spotify | other
    category: Mapped[str] = mapped_column(String(20), default="lecture", index=True)
    # lecture(강의) | music(찬양) | devotion(묵상)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    target_salvation_stage: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # seeker | uncertain | assured | mature (기존 패턴 재사용)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------- MediaAsset (업로드된 오디오 — 찬양/설교음성) ----------------
class MediaAsset(Base):
    """관리자가 업로드한 오디오 파일 (찬양 음원 / 설교 음성).

    파일 자체는 data/media/{category}/ 에 저장되고, 메타데이터만 DB에 보관.
    모바일 앱의 찬양/설교 탭에서 스트리밍 재생.
    """

    __tablename__ = "media_asset"
    __table_args__ = (
        Index("ix_media_asset_category_active", "category", "active", "order_index"),
    )

    asset_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), default="worship", index=True)
    # worship (찬양) | sermon (설교음성)
    artist: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # 찬양: 가수/연주자 / 설교: 설교자
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scripture_refs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 본문 구절 (예: ["요한복음 3:16"])
    file_name: Mapped[str] = mapped_column(String(300))  # 실제 저장 파일명
    storage_path: Mapped[str] = mapped_column(String(500))  # 디스크 절대/상대 경로
    mime_type: Mapped[str] = mapped_column(String(100), default="audio/mpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    # ── 예약 발행 / 푸시 스케줄링 (2026-07-29 미디어 동기화) ──
    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 발행(앱 노출) 예정 시각. 미래 시각이면 active=False 로 두고 스케줄러가 도래 시 활성화.
    notify_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 푸시 발송 예정 시각 (즉시=업로드 시각, 배치=저녁 21:00 KST, 없음=None).
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 푸시 발송 완료 시각 — 중복 발송 방지.


# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: CodeBuddy
# Timestamp: 2026-07-16
# Task: 인기 Q&A 집계 & 통찰 시스템 — 3개 신규 테이블
# Reason: 설계 문서 docs/design-popular-qa-system.md 기반 구현
# Status: IN_PROGRESS
# =============================================================================

# ---------------- Enums for Trending ----------------


class EditFieldType(str, enum.Enum):
    question = "question"
    answer = "answer"
    root_cause = "root_cause"
    ai_diagnosis = "ai_diagnosis"
    best_answer = "best_answer"
    best_answer_why = "best_answer_why"
    reflection = "reflection"
    is_featured = "is_featured"
    is_hidden = "is_hidden"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SnapshotType(str, enum.Enum):
    question = "question"
    answer = "answer"


# ---------------- QATrendSnapshot — 집계 스냅샷 + 통찰 데이터 ----------------


class QATrendSnapshot(Base):
    """인기 질문/답변 집계 스냅샷 + LLM 통찰 데이터."""

    __tablename__ = "qa_trend_snapshot"
    __table_args__ = (
        Index("ix_trend_type_computed", "snapshot_type", "computed_at"),
        Index("ix_trend_score", "trend_score"),
        Index("ix_trend_fb_ratio", "fb_ratio"),
        Index("ix_trend_review_status", "review_status_root_cause"),
        Index("ix_trend_deleted", "deleted_at"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    snapshot_type: Mapped[str] = mapped_column(String(10), default="question")

    # ── 집계 데이터 ──
    canonical_text: Mapped[str] = mapped_column(Text)
    raw_variants: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_count_7d: Mapped[int] = mapped_column(Integer, default=0)
    recent_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    positive_feedback: Mapped[int] = mapped_column(Integer, default=0)
    negative_feedback: Mapped[int] = mapped_column(Integer, default=0)
    fb_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # ── 관리자 제어 ──
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_edited_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    edited_by: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # ── LLM 통찰 데이터 ──
    root_cause_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    best_answer_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    best_answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    best_answer_why: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reflection_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    insight_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    insight_version: Mapped[int] = mapped_column(Integer, default=0)
    ai_model_used: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    insight_prompt_version: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    needs_regeneration: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 검수 상태 ──
    review_status_root_cause: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    review_status_ai_diagnosis: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    review_status_best_answer_why: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    review_status_reflection: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    last_reviewed_by: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── 단편 설교 + 추천 추가질문 (작업 W) ──
    short_sermon_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    short_sermon_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    short_sermon_doc_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    suggested_followups: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # ── 수명 주기 ──
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---------------- QAAdminEditLog — 편집 감사 로그 ----------------


class QAAdminEditLog(Base):
    """관리자 편집 감사 로그 — 모든 수정 이력을 추적."""

    __tablename__ = "qa_admin_edit_log"
    __table_args__ = (
        Index("ix_edit_log_snapshot_field", "snapshot_id", "field", "edited_at"),
        Index("ix_edit_log_field_time", "field", "edited_at"),
        Index("ix_edit_log_edited_by", "edited_by", "edited_at"),
    )

    log_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    snapshot_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("qa_trend_snapshot.snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(20))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_value_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    new_value_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    edit_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ai_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    diff_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_by: Mapped[str] = mapped_column(String(40))
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    reverted: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_sequence_num: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


# ---------------- QAEditDraft — 편집 임시 저장 ----------------


class QAEditDraft(Base):
    """관리자 편집 임시 저장 (72시간 유효)."""

    __tablename__ = "qa_edit_draft"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "field", "saved_by", name="uq_draft_snapshot_field_admin"),
        Index("ix_draft_expires", "expires_at"),
    )

    draft_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("qa_trend_snapshot.snapshot_id", ondelete="CASCADE"),
        index=True,
    )
    field: Mapped[str] = mapped_column(String(20))
    draft_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    saved_by: Mapped[str] = mapped_column(String(40))
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


# =============================================================================
# 🔧 AI-AGENT-WORK — Wave B: 평가 하네스 (Evaluation Harness)
# Task: RAG/생성 회귀 측정용 평가 테이블 2종 (eval_question / eval_run)
# Reason: system-audit-fix-orders.md 검증 결과 — 기존 테이블 미존재로 "생성" 필요.
#         enhanced_rag/evaluation.py 의 Hit@k / MRR / nDCG + LLM-judge 재사용.
# =============================================================================


class EvalQuestion(Base):
    """평가용 골드 질문 은행. 카테고리별 회귀 측정에 사용.

    category 예: factual(사실검색) | crisis(위기 바이패스) | salvation(구원) |
                 profile_boost(프로필 부스트) | safety(안전) | general
    expected_doc_ids: 검색 평가(Hit@k/MRR/nDCG)용 정답 문서 id 목록.
    expected_risk_level: 위기 회귀용 — 기대 위험도 (low|medium|high|urgent).
    expected_crisis_bypass: 이 질문이 위기 하드 바이패스를 유발해야 하는가.
    """

    __tablename__ = "eval_question"
    __table_args__ = (
        Index("ix_eval_question_cat_active", "category", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(40), default="general", index=True)
    question: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_doc_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    expected_risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    expected_crisis_bypass: Mapped[bool] = mapped_column(Boolean, default=False)
    lang: Mapped[str] = mapped_column(String(8), default="ko")
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class EvalRun(Base):
    """평가 실행 1건(질문 1개에 대한 1회 채점). run_id 로 배치 묶음.

    검색 지표(hit_at_k/mrr/ndcg_at_k) + 생성 채점(judge_score/judge_verdict) +
    위기 회귀(crisis_bypass_triggered) 를 함께 보관한다.
    """

    __tablename__ = "eval_run"
    __table_args__ = (
        Index("ix_eval_run_run_cat", "run_id", "category"),
        Index("ix_eval_run_question", "question_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    question_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("eval_question.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(40), default="general", index=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    hit_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mrr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ndcg_at_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_verdict: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    crisis_bypass_triggered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


# ---------------- ActivityEvent (클라이언트 활동/시청 로그) ----------------
class ActivityEvent(Base):
    """모바일/웹 클라이언트에서 수집한 사용자 활동 이벤트.

    시청·검색·화면이동·annotate·공유·세션·클라이언트 에러 등.
    관리자 모니터링(/admin/activity/*) 의 데이터 소스.
    미로그인(게스트) 이벤트는 subscriber_id 가 NULL 이고 device_id 로만 귀속.
    """

    __tablename__ = "activity_event"

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    subscriber_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )  # 미로그인은 NULL + device_id
    device_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    platform: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # android|web|ios
    app_version: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)

    __table_args__ = (
        Index("ix_activity_sub_type", "subscriber_id", "event_type"),
        Index("ix_activity_created_type", "created_at", "event_type"),
    )


# ---------------- CCP (비용/증빙 서브시스템) 테이블 등록 ----------------
# migrations/env.py 와 init_db() 는 이 모듈만 import 하므로, CCP 테이블이
# Base.metadata 에 확실히 등록되도록 파일 말미에서 재노출한다.
# (모듈 최상단이 아닌 말미에 두는 이유: ccp.py 가 ..db 만 의존하므로
#  순환 import 는 없으나, 정의 순서를 명확히 하기 위함)
from .ccp import CCPRateCard  # noqa: E402,F401
