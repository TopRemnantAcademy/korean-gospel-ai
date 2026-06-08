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
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(datetime.UTC)


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

    artifact_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
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

    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", cascade="all, delete-orphan")


# ---------------- L2: DocumentVersion ----------------
class DocumentVersion(Base):
    """문서의 한 시점. draft일 때만 가변. published 후 immutable."""
    __tablename__ = "document_version"
    __table_args__ = (UniqueConstraint("doc_id", "version_number", name="uq_doc_version"),)

    version_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(ForeignKey("document.doc_id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("source_artifact.artifact_id"))

    state: Mapped[str] = mapped_column(String(20), default=DocVersionState.draft.value, index=True)

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

    body_patch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 마이크로 패치된 본문 (null=원본 그대로)
    structured_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # INGEST Stage 2 구조화 산출물 (null=미처리)
    chunking_policy: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    checklist: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    validation_report: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    document: Mapped[Document] = relationship(back_populates="versions")
    artifact: Mapped[SourceArtifact] = relationship()
    snapshot: Mapped[Optional["IndexSnapshot"]] = relationship(back_populates="version", uselist=False)


# ---------------- L3: IndexSnapshot ----------------
class IndexSnapshot(Base):
    """publish 시점에 자동 생성. Qdrant 동기화 메타."""
    __tablename__ = "index_snapshot"

    snapshot_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_version.version_id"), unique=True)
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

    subscriber_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    auth_status: Mapped[str] = mapped_column(String(20), default="anonymous")
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, unique=True)
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
    last_emotion: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    is_darakbang_member: Mapped[bool] = mapped_column(Boolean, default=False)
    is_believer: Mapped[bool] = mapped_column(Boolean, default=True)  # ⚠️ 구버전 호환용 유지 — EPIC D 이후 salvation_status 로 대체

    # ✅ D-C12: 구원 상태 1급 변수
    salvation_status: Mapped[str] = mapped_column(String(16), default="unknown")
       # unknown    | 시스템이 모름 (신규, 미상호작용) — 기본값
       # seeker     | 구원 모름·관심 단계
       # uncertain  | 들었으나 확신 없음 (98% 가 여기) — 시스템의 DEFAULT TARGET
       # assured    | 구원의 확신 있음 (요5:24, 요일5:13)
       # mature     | 확신 + 열매 + 제자훈련 + 사역
    salvation_confidence: Mapped[float] = mapped_column(Float, default=0.0)
       # 0.0~1.0 — 시스템이 이 분류를 얼마나 확신하는가
    salvation_last_signal_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
       # 구원 관련 마지막 발화 시간
    assume_saved: Mapped[bool] = mapped_column(Boolean, default=False)
       # 운영자가 "이 사람 구원받았다 치고 대화하라" 설정 시 True
       # 기본 False — 시스템은 *아직 구원 못 받았다는 전제로* 대화

    # ✅ D-C13: 다락방(Darakbang) 3단 필드
    darakbang_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
       # member | leader | pastor | guest
    darakbang_chapter: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
       # 예: "서울-강남", "분당-야탑", "온라인"
    darakbang_joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    darakbang_verified: Mapped[bool] = mapped_column(Boolean, default=False)
       # 운영자가 "이 사람 진짜 다락방 식구 맞다" 확인

    topic_interests: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    consent: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # ✅ E-A: 토큰 쿼터 3 bucket (bonus > monthly > daily 순 소진)
    tokens_daily: Mapped[int] = mapped_column(Integer, default=0)
       # 비가입자 일일 무료 풀 — 매일 자정 리셋
    tokens_daily_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tokens_monthly: Mapped[int] = mapped_column(Integer, default=0)
       # 가입자 월간 풀 — 매월 1일 리셋
    tokens_monthly_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tokens_bonus: Mapped[int] = mapped_column(Integer, default=0)
       # 가입 보너스·이벤트·운영자 수동 지급 — 리셋 없음
    tokens_lifetime_used: Mapped[int] = mapped_column(Integer, default=0)
       # 누적 사용 토큰 (분석용)

    # 구독 / 무료체험 상태
    subscription_tier: Mapped[str] = mapped_column(String(20), default="guest")
       # guest | member | supporter
       # guest : 무료체험 중 또는 체험 종료(trial_expires_at 으로 구분)
       # member: 유료 회원 → 제한 없음
       # supporter: 후원 회원 → 제한 없음
    subscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    subscription_source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # ✅ 무료체험 만료일 — first_seen_at + 3일로 자동 설정
    trial_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
       # None → 아직 만료일 미설정 (= 무제한 체험, 운영자 직접 등록 사용자)
       # 미래값 → 체험 중
       # 과거값 → 체험 종료, 결제 필요

    # 종교 분류 (사용자 선택 또는 온보딩에서 자동 감지)
    religion: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
       # 기독교 | 불교 | 무교 | 이슬람 | 기타
    denomination: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
       # 기독교일 때만 사용: 장로교|감리교|침례교|순복음|성결|기타
       # 다락방은 denomination 에 속하지 않음 — is_darakbang_member 필드로 별도 관리

    # ✅ E-B: 봇 의심 점수
    bot_score: Mapped[float] = mapped_column(Float, default=0.0)
       # 0.0~1.0, 누적 행동 신호로 산정
    flagged_as_bot: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------- Interaction ----------------
class Interaction(Base):
    """질문-답변 한 턴. cited_versions에 옛 답 재현 정보."""
    __tablename__ = "interaction"

    interaction_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    subscriber_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("subscriber.subscriber_id"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    cited_versions: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    feedback: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # +1/-1/null
    journey_signal: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


# ---------------- AuditLog (immutable) ----------------
class AuditLog(Base):
    """모든 state transition / publish / archive / 편집 기록. 절대 수정 X."""
    __tablename__ = "audit_log"

    log_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
    who: Mapped[str] = mapped_column(String(100), default="admin")
    when: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    action: Mapped[str] = mapped_column(String(80))           # e.g. "version.publish"
    entity_type: Mapped[str] = mapped_column(String(40))      # "document_version"
    entity_id: Mapped[str] = mapped_column(String(40), index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    note: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


# ---------------- PromptTemplate (운영자가 편집 가능) ----------------
class PromptTemplate(Base):
    """시스템 프롬프트 (active=1 인 행이 현재 사용됨)."""
    __tablename__ = "prompt_template"

    template_id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid)
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
    category_type: Mapped[str] = mapped_column(String(50), index=True) # "faith_stage", "emotional_state", "tone" 등
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
    from_status: Mapped[str] = mapped_column(String(16))    # 이전 단계
    to_status: Mapped[str] = mapped_column(String(16))      # 새 단계
    trigger_signal: Mapped[str] = mapped_column(String(20))  # seeking|doubting|confessing|...
    trigger_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 결정적 발화
    interaction_id: Mapped[Optional[str]] = mapped_column(
        String(40), ForeignKey("interaction.interaction_id"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)  # 운영자 수동 변경
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
    level: Mapped[str] = mapped_column(String(10), index=True)   # ERROR|SLOW|CRITICAL
    method: Mapped[str] = mapped_column(String(10))              # GET|POST|...
    path: Mapped[str] = mapped_column(String(200), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    error_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


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
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending|running|done|failed
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
    version_id: Mapped[str] = mapped_column(String(40), ForeignKey("document_version.version_id"), index=True)
    operator_id: Mapped[str] = mapped_column(String(60), default="admin")
    draft_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    device_id: Mapped[str] = mapped_column(String(60), default="browser")
    conflict_resolved: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint('version_id', 'operator_id', name='uq_draft_ver_op'),
    )


class GlossaryTerm(Base):
    """E-E: 자동 용어집 — 신학 용어 + 고유명사 통합 관리."""
    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    canonical_form: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(30), default="other")
    # person | place | doctrine | scripture | event | other
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_terms: Mapped[list] = mapped_column(JSON, default=list)
    frequency_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_doc_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    operator_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_theology_term: Mapped[bool] = mapped_column(Boolean, default=False)
    # True → D3 가드 화이트리스트 자동 등재
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
