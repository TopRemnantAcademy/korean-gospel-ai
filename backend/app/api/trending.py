"""트렌딩 & 통찰 API — 사용자용 + 관리자용 엔드포인트.

설계 문서 §6 기반 구현.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import or_

from ..db import get_session, get_session_immediate
from ..models.orm import (
    QATrendSnapshot,
    QAAdminEditLog,
    QAEditDraft,
    Interaction,
)
from ..models.schemas import (
    PatchTrendingReq,
    RevertReq,
    ReviewInsightReq,
    RegenerateReq,
    AskReq,
    BatchRegenerateReq,
    RevertResponse,
    ReviewResponse,
    RegenerateResponse,
    BatchRegenerateResponse,
    InsightStatsResponse,
    InsightQueueResponse,
    EditHistoryResponse,
    TrendingDashboardResponse,
    TrendingCardsResponse,
    InsightResponse,
    TrendingAnswersResponse,
)
from ..services import trending_service
from ..services.edit_diff import compute_diff, truncate_value
from ..services.edit_validator import validate_field, validate_edit_reason

_logger = logging.getLogger("gospel-api.trending")

router = APIRouter(tags=["trending"])

# ── Auth 헬퍼 ──


def _check_admin(authorization: Optional[str] = Header(default=None)) -> None:
    """관리자 인증 확인."""
    from .auth import check_admin as _ca

    _ca(authorization)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════
# 사용자용 API (§6.1)
# ═══════════════════════════════════════════════════════════════════


@router.get("/trending/cards", response_model=TrendingCardsResponse)
def get_trending_cards(
    period: str = Query("7d", pattern="^(7d|30d)$"),
    category: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=20),
    lang: Optional[str] = Query(None, description="언어 분류(zh/ko/en). 모바일 중국어 앱은 zh 전송"),
):
    """통찰 카드 목록 — 사용자 랜딩 화면용.

    lang 이 주어지면 해당 언어로 작성된 질문 클러스터만 노출 (각국 모국어 분리).
    """
    try:
        cards = trending_service.get_top_questions(
            period=period,
            category=category,
            limit=limit,
            include_hidden=False,
            lang=lang,
        )
        return TrendingCardsResponse(
            cards=cards,
            updated_at=_now().isoformat(),
        )
    except Exception:
        _logger.exception("[trending/cards] 오류")
        raise HTTPException(500, "카드 목록 조회 중 오류가 발생했습니다")


@router.get("/trending/answers", response_model=TrendingAnswersResponse)
def get_trending_answers(
    period: str = Query("7d", pattern="^(7d|30d)$"),
    category: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=20),
    min_feedback: int = Query(3, ge=1),
):
    """호평 답변 목록."""
    try:
        items = trending_service.get_top_answers(
            period=period,
            category=category,
            limit=limit,
            min_feedback=min_feedback,
        )
        return TrendingAnswersResponse(
            items=items,
            updated_at=_now().isoformat(),
        )
    except Exception:
        _logger.exception("[trending/answers] 오류")
        raise HTTPException(500, "답변 목록 조회 중 오류가 발생했습니다")


@router.get("/insight/{snapshot_id}", response_model=InsightResponse)
def get_insight(snapshot_id: str):
    """4단계 통찰 데이터 조회."""
    try:
        data = trending_service.get_insight_data(snapshot_id)
        if not data:
            raise HTTPException(404, "스냅샷을 찾을 수 없습니다")
        # 방어: 서비스가 snapshot_id 를 누락해도 경로 파라미터로 보완하여
        # InsightResponse 검증 실패(ValidationError → 500)를 막는다.
        data = {**data, "snapshot_id": snapshot_id}
        return InsightResponse(**data)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("[insight] 오류")
        raise HTTPException(500, "통찰 데이터 조회 중 오류가 발생했습니다")


# ═══════════════════════════════════════════════════════════════════
# 관리자용 API (§6.2)
# ═══════════════════════════════════════════════════════════════════


@router.get("/admin/trending/dashboard", response_model=TrendingDashboardResponse)
def admin_trending_dashboard(
    authorization=Header(default=None),
    period: str = Query("7d", pattern="^(7d|30d)$"),
    category: Optional[str] = Query(None),
):
    """관리자 대시보드 전체 데이터."""
    _check_admin(authorization)

    try:
        questions = trending_service.get_top_questions(period=period, category=category, limit=20, include_hidden=True)
        answers = trending_service.get_top_answers(period=period, category=category, limit=20, min_feedback=1)

        # 개요 통계
        with get_session() as s:
            cutoff_7d = _now() - timedelta(days=7)
            cutoff_30d = _now() - timedelta(days=30)

            total_7d = (
                s.query(Interaction)
                .filter(Interaction.created_at >= cutoff_7d)
                .count()
            )
            total_30d = (
                s.query(Interaction)
                .filter(Interaction.created_at >= cutoff_30d)
                .count()
            )

            total_snaps = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_type == "question",
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .count()
            )

        overview = {
            "total_interactions_7d": total_7d,
            "total_interactions_30d": total_30d,
            "unique_questions": total_snaps,
            "avg_fb_ratio": 0.0,
            "trend_up_count": sum(1 for q in questions if q.get("trend_direction") == "up"),
            "trend_down_count": sum(1 for q in questions if q.get("trend_direction") == "down"),
        }

        return TrendingDashboardResponse(
            overview=overview,
            top_questions=questions,
            top_answers=answers,
            chart_data={},
        )
    except HTTPException:
        raise
    except Exception:
        _logger.exception("[admin/trending] 대시보드 오류")
        raise HTTPException(500, "대시보드 조회 중 오류가 발생했습니다")


@router.patch("/admin/trending/{snapshot_id}")
def admin_patch_trending(
    snapshot_id: str,
    body: PatchTrendingReq,
    authorization=Header(default=None),
):
    """질문/답변/통찰 필드 직접 수정."""
    _check_admin(authorization)

    try:
        with get_session_immediate() as s:
            snap = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_id == snapshot_id,
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .first()
            )
            if not snap:
                raise HTTPException(404, "스냅샷을 찾을 수 없습니다")

            field = body.field.value

            # 이전 값 가져오기
            old_value = _get_field_value(snap, field)

            # 검증
            validation = validate_field(
                field,
                body.new_value,
                old_value=old_value if isinstance(old_value, str) else None,
                current_is_featured=snap.is_featured,
                current_is_hidden=snap.is_hidden,
            )

            if not validation["valid"]:
                raise HTTPException(422, validation["error"])

            new_value = validation["sanitized_value"]

            # No-op
            if validation.get("no_change"):
                return {
                    "ok": True,
                    "snapshot_id": snapshot_id,
                    "field": field,
                    "no_change": True,
                    "warnings": validation.get("warnings", []),
                }

            # edit_reason 검증
            reason_ok = validate_edit_reason(body.edit_reason)
            if not reason_ok["valid"]:
                raise HTTPException(422, reason_ok["error"])

            # 초안 저장 모드
            if body.save_draft:
                _save_draft(s, snapshot_id, field, str(new_value), "admin")
                return {
                    "ok": True,
                    "snapshot_id": snapshot_id,
                    "field": field,
                    "draft_saved": True,
                }

            # 409 충돌 감지 (5분 윈도우, force 제외)
            if not body.force:
                recent = (
                    s.query(QAAdminEditLog)
                    .filter(
                        QAAdminEditLog.snapshot_id == snapshot_id,
                        QAAdminEditLog.field == field,
                        QAAdminEditLog.edited_by != "admin",
                        QAAdminEditLog.reverted == False,  # noqa: E712
                        QAAdminEditLog.edited_at >= _now() - timedelta(minutes=5),
                    )
                    .first()
                )
                if recent:
                    raise HTTPException(
                        409,
                        detail=f"{recent.edited_by}님이 {recent.edited_at.isoformat()}에 이 필드를 수정했습니다",
                    )

            # 값 업데이트
            _set_field_value(snap, field, new_value)
            snap.updated_at = _now()
            snap.edited_at = _now()
            snap.edited_by = "admin"

            # edit_log 기록
            old_str = str(old_value) if old_value is not None else None
            new_str = str(new_value)
            truncated_old, old_hash = truncate_value(old_str)
            truncated_new, new_hash = truncate_value(new_str)

            # 시퀀스 번호
            max_seq = (
                s.query(QAAdminEditLog.edit_sequence_num)
                .filter(
                    QAAdminEditLog.snapshot_id == snapshot_id,
                    QAAdminEditLog.field == field,
                )
                .order_by(QAAdminEditLog.edit_sequence_num.desc())
                .first()
            )
            seq_num = (max_seq[0] + 1) if max_seq and max_seq[0] else 1

            # diff
            diff_result = compute_diff(old_str, new_str)

            log_entry = QAAdminEditLog(
                snapshot_id=snapshot_id,
                field=field,
                old_value=truncated_old,
                new_value=truncated_new,
                old_value_hash=old_hash,
                new_value_hash=new_hash,
                edit_reason=body.edit_reason,
                edited_by="admin",
                edited_at=_now(),
                diff_summary=diff_result.get("summary"),
                edit_sequence_num=seq_num,
            )
            s.add(log_entry)
            s.flush()

            return {
                "ok": True,
                "snapshot_id": snapshot_id,
                "field": field,
                "previous_value": old_str[:200] + "..." if old_str and len(old_str) > 200 else old_str,
                "new_value": new_str[:200] + "..." if len(new_str) > 200 else new_str,
                "edited_by": "admin",
                "edited_at": _now().isoformat(),
                "edit_log_id": log_entry.log_id,
                "diff_summary": diff_result.get("summary"),
                "review_status_updated": True,
                "warnings": validation.get("warnings", []),
            }

    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("[admin/trending/patch] 오류")
        raise HTTPException(500, f"편집 저장 중 오류가 발생했습니다: {e}")


@router.get("/admin/trending/{snapshot_id}/history", response_model=EditHistoryResponse)
def admin_trending_history(
    snapshot_id: str,
    authorization=Header(default=None),
    field: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """편집 이력 조회."""
    _check_admin(authorization)

    try:
        with get_session() as s:
            snap = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_id == snapshot_id,
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .first()
            )

            if not snap:
                raise HTTPException(404, "스냅샷을 찾을 수 없습니다")

            q = s.query(QAAdminEditLog).filter(
                QAAdminEditLog.snapshot_id == snapshot_id
            )

            if field:
                q = q.filter(QAAdminEditLog.field == field)

            total = q.count()
            logs = (
                q.order_by(QAAdminEditLog.edited_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            history = []
            for log in logs:
                old_preview = None
                new_preview = None
                if log.old_value:
                    old_preview = log.old_value[:100] + ("..." if len(log.old_value) > 100 else "")
                if log.new_value:
                    new_preview = log.new_value[:100] + ("..." if len(log.new_value) > 100 else "")

                change_type = "manual_edit"
                if log.ai_version:
                    change_type = "ai_generated"

                history.append({
                    "log_id": log.log_id,
                    "field": log.field,
                    "edited_by": log.edited_by,
                    "edited_at": log.edited_at.isoformat(),
                    "edit_reason": log.edit_reason,
                    "diff_summary": log.diff_summary,
                    "change_type": change_type,
                    "old_value_preview": old_preview,
                    "new_value_preview": new_preview,
                    "ai_version": log.ai_version,
                    "reverted": log.reverted,
                    "edit_sequence_num": log.edit_sequence_num,
                })

            return EditHistoryResponse(
                snapshot_id=snapshot_id,
                question=snap.canonical_text[:100],
                total_edits=total,
                history=history,
                total=total,
                has_more=(offset + limit) < total,
            )
    except HTTPException:
        raise
    except Exception:
        _logger.exception("[admin/trending/history] 오류")
        raise HTTPException(500, "편집 이력 조회 중 오류가 발생했습니다")


@router.post("/admin/trending/{snapshot_id}/revert", response_model=RevertResponse)
def admin_trending_revert(
    snapshot_id: str,
    body: RevertReq,
    authorization=Header(default=None),
):
    """이전 버전으로 롤백."""
    _check_admin(authorization)

    try:
        with get_session_immediate() as s:
            snap = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_id == snapshot_id,
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .first()
            )
            if not snap:
                raise HTTPException(404, "스냅샷을 찾을 수 없습니다")

            # 대상 로그 검증
            target_log = (
                s.query(QAAdminEditLog)
                .filter(QAAdminEditLog.log_id == body.target_log_id)
                .first()
            )

            if not target_log:
                raise HTTPException(422, "대상 로그를 찾을 수 없습니다")
            if target_log.snapshot_id != snapshot_id:
                raise HTTPException(422, "대상 로그가 이 스냅샷에 속하지 않습니다")
            if target_log.reverted:
                raise HTTPException(409, "이미 롤백된 버전입니다")
            if target_log.field != body.field.value:
                raise HTTPException(422, "필드가 일치하지 않습니다")

            # 롤백 실행
            field = body.field.value
            restored_value = target_log.old_value

            # 복원
            _set_field_value(snap, field, restored_value)
            snap.updated_at = _now()

            # 로그 마킹
            target_log.reverted = True

            # 새 로그 (롤백 기록)
            new_log = QAAdminEditLog(
                snapshot_id=snapshot_id,
                field=field,
                old_value=_get_field_value(snap, field) if not restored_value else str(restored_value),
                new_value=restored_value,
                edit_reason=f"롤백: {body.reason[:150]}",
                edited_by="admin",
                edited_at=_now(),
                diff_summary=f"v{target_log.edit_sequence_num} 버전으로 롤백",
            )
            s.add(new_log)
            s.flush()

            return RevertResponse(
                ok=True,
                snapshot_id=snapshot_id,
                field=field,
                restored_from=body.target_log_id,
                restored_value=restored_value[:200] if restored_value else None,
                reverted_at=_now().isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("[admin/trending/revert] 오류")
        raise HTTPException(500, f"롤백 중 오류가 발생했습니다: {e}")


@router.post("/admin/trending/recompute")
def admin_trending_recompute(authorization=Header(default=None)):
    """집계 수동 재실행."""
    _check_admin(authorization)

    try:
        t0 = _now()
        count_q = trending_service.compute_trending_snapshots(snapshot_type="question")
        count_a = trending_service.compute_trending_snapshots(snapshot_type="answer")
        elapsed = int((_now() - t0).total_seconds() * 1000)

        # 통찰 생성 (Top 5에 대해)
        try:
            # 동기 핸들러(스레드풀 실행)에서 안전하게 새 이벤트 루프 생명주기 관리.
            # asyncio.run 은 종료 시 set_event_loop(None) 처리해 스레드에 닫힌
            # 루프가 남는 문제(new_event_loop+set_event_loop+close)를 방지.
            insight_result = asyncio.run(
                __import__("backend.app.services.insight_engine", fromlist=["generate_insights_for_top_questions"])
                .generate_insights_for_top_questions(limit=5)
            )
        except Exception as ie:
            _logger.warning("[admin/trending/recompute] 통찰 생성 실패: %s", ie)
            insight_result = {"generated": 0}

        return {
            "ok": True,
            "computed_at": _now().isoformat(),
            "duration_ms": elapsed,
            "snapshots_updated": count_q + count_a,
            "new_insights_generated": insight_result.get("generated", 0),
            "new_insight_questions": [],
        }
    except Exception as e:
        _logger.exception("[admin/trending/recompute] 오류")
        raise HTTPException(500, f"집계 실행 중 오류가 발생했습니다: {e}")


# ═══════════════════════════════════════════════════════════════════
# 통찰 관리 API (§6.2)
# ═══════════════════════════════════════════════════════════════════


@router.get("/admin/insight/queue", response_model=InsightQueueResponse)
def admin_insight_queue(
    authorization=Header(default=None),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """검수 대기 + 수정 필요 대기 목록."""
    _check_admin(authorization)

    try:
        with get_session() as s:
            # 미검수 항목
            pending_query = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_type == "question",
                    QATrendSnapshot.deleted_at.is_(None),
                    QATrendSnapshot.insight_version > 0,
                )
            )

            if category:
                pending_query = pending_query.filter(QATrendSnapshot.category == category)

            all_pending = pending_query.order_by(QATrendSnapshot.trend_score.desc()).all()

            pending_review = []
            for snap in all_pending:
                unreviewed = []
                for section, status_field in [
                    ("root_cause", snap.review_status_root_cause),
                    ("ai_diagnosis", snap.review_status_ai_diagnosis),
                    ("best_answer_why", snap.review_status_best_answer_why),
                    ("reflection", snap.review_status_reflection),
                ]:
                    if status_field in (None, "pending"):
                        content = getattr(snap, {
                            "root_cause": "root_cause_analysis",
                            "ai_diagnosis": "ai_diagnosis",
                            "best_answer_why": "best_answer_why",
                            "reflection": "reflection_prompt",
                        }[section], None)
                        unreviewed.append({
                            "field": section,
                            "status": status_field or "pending",
                            "char_count": len(content) if content else 0,
                        })

                if unreviewed:
                    # 우선순위
                    pri = "low"
                    if snap.trend_score >= 50:
                        pri = "high"
                    elif snap.trend_score >= 20:
                        pri = "medium"

                    if priority and priority != pri:
                        continue

                    pending_review.append({
                        "snapshot_id": snap.snapshot_id,
                        "question": snap.canonical_text[:100],
                        "generated_at": snap.insight_generated_at.isoformat() if snap.insight_generated_at else None,
                        "insight_version": snap.insight_version,
                        "ai_model_used": snap.ai_model_used,
                        "unreviewed_sections": unreviewed,
                        "priority": pri,
                    })

            # 반려 항목
            rejected_query = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_type == "question",
                    QATrendSnapshot.deleted_at.is_(None),
                )
            )
            rejected = rejected_query.all()

            needs_correction = []
            for snap in rejected:
                for section, status_field in [
                    ("root_cause", snap.review_status_root_cause),
                    ("ai_diagnosis", snap.review_status_ai_diagnosis),
                    ("best_answer_why", snap.review_status_best_answer_why),
                    ("reflection", snap.review_status_reflection),
                ]:
                    if status_field == "rejected":
                        needs_correction.append({
                            "snapshot_id": snap.snapshot_id,
                            "question": snap.canonical_text[:100],
                            "field": section,
                            "flagged_reason": "반려됨",
                            "flagged_at": snap.last_reviewed_at.isoformat() if snap.last_reviewed_at else None,
                            "flagged_by": snap.last_reviewed_by or "system",
                        })

            # 페이지네이션
            total_pending = len(pending_review)
            total_correction = len(needs_correction)

            return InsightQueueResponse(
                pending_review=pending_review[offset : offset + limit],
                needs_correction=needs_correction[:limit],
                total_pending=total_pending,
                total_needs_correction=total_correction,
            )
    except Exception:
        _logger.exception("[admin/insight/queue] 오류")
        raise HTTPException(500, "대기 목록 조회 중 오류가 발생했습니다")


@router.patch("/admin/insight/{snapshot_id}/review", response_model=ReviewResponse)
def admin_insight_review(
    snapshot_id: str,
    body: ReviewInsightReq,
    authorization=Header(default=None),
):
    """통찰 검수 완료/반려."""
    _check_admin(authorization)

    try:
        with get_session_immediate() as s:
            snap = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_id == snapshot_id,
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .first()
            )
            if not snap:
                raise HTTPException(404, "스냅샷을 찾을 수 없습니다")

            section = body.section.value
            status = "approved" if body.approved else "rejected"

            # 상태 업데이트
            status_map = {
                "root_cause": "review_status_root_cause",
                "ai_diagnosis": "review_status_ai_diagnosis",
                "best_answer_why": "review_status_best_answer_why",
                "reflection": "review_status_reflection",
            }
            setattr(snap, status_map[section], status)
            snap.last_reviewed_by = "admin"
            snap.last_reviewed_at = _now()
            snap.updated_at = _now()

            if not body.approved:
                snap.needs_regeneration = True

            # 모든 섹션 검토 여부
            all_statuses = [
                snap.review_status_root_cause,
                snap.review_status_ai_diagnosis,
                snap.review_status_best_answer_why,
                snap.review_status_reflection,
            ]
            all_reviewed = all(s is not None and s != "pending" for s in all_statuses)
            all_approved = all(s == "approved" for s in all_statuses)

            # published_at 설정
            if all_approved and not snap.published_at:
                snap.published_at = _now()

            s.flush()

            return ReviewResponse(
                ok=True,
                snapshot_id=snapshot_id,
                section=section,
                new_status=status,
                rejection_reason=body.rejection_reason if not body.approved else None,
                needs_regeneration=snap.needs_regeneration,
                all_sections_reviewed=all_reviewed,
                ready_for_user=all_approved,
            )
    except HTTPException:
        raise
    except Exception:
        _logger.exception("[admin/insight/review] 오류")
        raise HTTPException(500, "검수 처리 중 오류가 발생했습니다")


@router.post("/admin/insight/{snapshot_id}/regenerate", response_model=RegenerateResponse)
async def admin_insight_regenerate(
    snapshot_id: str,
    body: RegenerateReq,
    authorization=Header(default=None),
):
    """통찰 LLM 재생성."""
    _check_admin(authorization)

    try:
        from ..services.insight_engine import generate_insights

        sections = [s.value for s in body.sections] if body.sections else None
        result = await generate_insights(
            snapshot_id,
            sections=sections,
            additional_instruction=body.additional_instruction,
            model_override=body.model_override,
        )

        if not result.get("ok"):
            raise HTTPException(500, result.get("error", "통찰 생성 실패"))

        return RegenerateResponse(
            ok=True,
            snapshot_id=snapshot_id,
            insight_version=result["insight_version"],
            generated_at=result["generated_at"],
            sections_generated=result["sections_generated"],
            sections_failed=result["sections_failed"],
            model_used=result["model_used"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("[admin/insight/regenerate] 오류")
        raise HTTPException(500, f"통찰 재생성 중 오류가 발생했습니다: {e}")


@router.post("/admin/insight/{snapshot_id}/generate-short-sermon")
async def admin_generate_short_sermon(
    snapshot_id: str,
    authorization=Header(default=None),
):
    """단편 설교 LLM 생성 (작업 W). 저장은 하지 않고 텍스트만 반환 → 관리자가 검토 후 PATCH 저장."""
    _check_admin(authorization)
    try:
        from ..services.insight_engine import generate_short_sermon

        result = await generate_short_sermon(snapshot_id)
        if not result.get("ok"):
            raise HTTPException(500, result.get("error", "단편 설교 생성 실패"))
        return {"ok": True, "snapshot_id": snapshot_id, "text": result["text"]}
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("[admin/insight/generate-short-sermon] 오류")
        raise HTTPException(500, f"단편 설교 생성 중 오류가 발생했습니다: {e}")


@router.post("/admin/insight/{snapshot_id}/ask")
async def admin_insight_ask(
    snapshot_id: str,
    body: AskReq,
    authorization=Header(default=None),
):
    """추가 질문하기 (작업: 인기QA 후속 질문).

    body.question 은 반드시 유저의 질문 + 해당 QA의 내용(위의 내용)을 근거로 한
    후속 질문이어야 하며, 단독적인 하나의 질문이 아니다. 응답은 항상 원본
    질문·답변·통찰 컨텍스트에 묶여 생성된다.
    """
    _check_admin(authorization)
    try:
        from ..services.insight_engine import ask_about_snapshot

        result = await ask_about_snapshot(snapshot_id, body.question)
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "추가 질문 처리 실패"))

        return {
            "ok": True,
            "snapshot_id": snapshot_id,
            "answer": result["answer"],
            "grounded_in": result.get("grounded_in"),
        }
    except HTTPException:
        raise
    except Exception as e:
        _logger.exception("[admin/insight/ask] 오류")
        raise HTTPException(500, f"추가 질문 처리 중 오류가 발생했습니다: {e}")


@router.post("/admin/insight/batch-regenerate", response_model=BatchRegenerateResponse)
async def admin_insight_batch_regenerate(
    body: BatchRegenerateReq,
    authorization=Header(default=None),
):
    """일괄 통찰 재생성."""
    _check_admin(authorization)

    try:
        from ..services.insight_engine import generate_insights

        with get_session() as s:
            query = s.query(QATrendSnapshot).filter(
                QATrendSnapshot.snapshot_type == "question",
                QATrendSnapshot.deleted_at.is_(None),
            )

            if body.filter == "all_pending":
                query = query.filter(
                    QATrendSnapshot.insight_version > 0,
                )
            elif body.filter == "all_rejected":
                # 반려: 4개 검수 차원 중 하나라도 "rejected"인 스냅샷
                # (admin/insight/queue 의 needs_correction 로직과 동일 기준)
                query = query.filter(
                    or_(
                        QATrendSnapshot.review_status_root_cause == "rejected",
                        QATrendSnapshot.review_status_ai_diagnosis == "rejected",
                        QATrendSnapshot.review_status_best_answer_why == "rejected",
                        QATrendSnapshot.review_status_reflection == "rejected",
                    )
                )
            elif body.filter == "needs_regeneration":
                query = query.filter(
                    QATrendSnapshot.needs_regeneration == True,  # noqa: E712
                )

            candidates = query.order_by(QATrendSnapshot.trend_score.desc()).limit(body.max_items).all()

        succeeded = 0
        failed = 0
        errors = []

        sections = [s.value for s in body.sections] if body.sections else None

        for snap in candidates:
            try:
                result = await generate_insights(
                    snap.snapshot_id,
                    sections=sections,
                    model_override=body.model_override,
                )
                if result.get("ok"):
                    succeeded += 1
                else:
                    failed += 1
                    errors.append({"snapshot_id": snap.snapshot_id, "reason": result.get("error", "unknown")})
            except Exception as e:
                failed += 1
                errors.append({"snapshot_id": snap.snapshot_id, "reason": str(e)})

        return BatchRegenerateResponse(
            ok=True,
            total_candidates=len(candidates),
            partial_success=failed > 0 and succeeded > 0,
            succeeded=succeeded,
            failed=failed,
            errors=errors[:10],
        )
    except Exception as e:
        _logger.exception("[admin/insight/batch-regenerate] 오류")
        raise HTTPException(500, f"일괄 재생성 중 오류가 발생했습니다: {e}")


@router.get("/admin/insight/stats", response_model=InsightStatsResponse)
def admin_insight_stats(
    authorization=Header(default=None),
    period: str = Query("all", pattern="^(7d|30d|90d|all)$"),
):
    """통찰 품질 통계."""
    _check_admin(authorization)

    try:
        with get_session() as s:
            base_query = s.query(QATrendSnapshot).filter(
                QATrendSnapshot.snapshot_type == "question",
                QATrendSnapshot.deleted_at.is_(None),
            )

            total = base_query.count()
            with_insight = base_query.filter(QATrendSnapshot.insight_version > 0).count()

            fully_approved = 0
            partially_approved = 0
            pending_review = 0

            all_with_insight = base_query.filter(QATrendSnapshot.insight_version > 0).all()
            for snap in all_with_insight:
                statuses = [
                    snap.review_status_root_cause,
                    snap.review_status_ai_diagnosis,
                    snap.review_status_best_answer_why,
                    snap.review_status_reflection,
                ]
                approved_count = sum(1 for s in statuses if s == "approved")
                pending_count = sum(1 for s in statuses if s in (None, "pending"))

                if approved_count == 4:
                    fully_approved += 1
                elif approved_count > 0:
                    partially_approved += 1

                if pending_count > 0:
                    pending_review += 1

            return InsightStatsResponse(
                total_snapshots=total,
                insight_coverage={
                    "total_with_insight": with_insight,
                    "fully_approved": fully_approved,
                    "partially_approved": partially_approved,
                    "pending_review": pending_review,
                },
                edit_stats={
                    "total_edits_7d": 0,
                    "most_edited_field": "root_cause",
                    "most_edited_field_count": 0,
                    "avg_edits_per_snapshot": 0.0,
                    "ai_regeneration_count_7d": 0,
                },
                model_quality={},
            )
    except Exception:
        _logger.exception("[admin/insight/stats] 오류")
        raise HTTPException(500, "통계 조회 중 오류가 발생했습니다")


# ═══════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ═══════════════════════════════════════════════════════════════════

_FIELD_MAP = {
    "question": "canonical_text",
    "answer": "admin_edited_text",
    "root_cause": "root_cause_analysis",
    "ai_diagnosis": "ai_diagnosis",
    "best_answer": "best_answer_text",
    "best_answer_why": "best_answer_why",
    "reflection": "reflection_prompt",
    "is_featured": "is_featured",
    "is_hidden": "is_hidden",
    # 컬럼명 별칭 (관리자 페이지가 컬럼명 필드를 보낼 때 정상 매핑 — 사전 편집 버그 수정)
    "root_cause_analysis": "root_cause_analysis",
    "best_answer_text": "best_answer_text",
    "reflection_prompt": "reflection_prompt",
    # ── 작업 W: 단편 설교 + 추천 추가질문 ──
    "short_sermon_title": "short_sermon_title",
    "short_sermon_text": "short_sermon_text",
    "short_sermon_doc_id": "short_sermon_doc_id",
    "suggested_followups": "suggested_followups",
}


def _get_field_value(snap: QATrendSnapshot, field: str):
    """필드명 → ORM 컬럼 값."""
    col = _FIELD_MAP.get(field)
    if col:
        return getattr(snap, col)
    return None


def _set_field_value(snap: QATrendSnapshot, field: str, value):
    """필드명 → ORM 컬럼 값 설정."""
    col = _FIELD_MAP.get(field)
    if col:
        setattr(snap, col, value)


def _save_draft(session, snapshot_id: str, field: str, content: str, saved_by: str):
    """편집 초안 저장 (upsert)."""
    existing = (
        session.query(QAEditDraft)
        .filter(
            QAEditDraft.snapshot_id == snapshot_id,
            QAEditDraft.field == field,
            QAEditDraft.saved_by == saved_by,
        )
        .first()
    )

    if existing:
        existing.draft_content = content
        existing.saved_at = _now()
        existing.expires_at = _now() + timedelta(hours=72)
    else:
        draft = QAEditDraft(
            snapshot_id=snapshot_id,
            field=field,
            draft_content=content,
            saved_by=saved_by,
            saved_at=_now(),
            expires_at=_now() + timedelta(hours=72),
        )
        session.add(draft)
    session.flush()
