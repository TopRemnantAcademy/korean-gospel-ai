"""Memory service - 사용자 대화 기억.

기능:
- 같은 subscriber_id 의 최근 N개 Interaction 조회
- LLM 컨텍스트에 주입할 요약 생성
- 특정 키워드/시기 검색
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc

from ..db import get_session
from ..models.orm import Interaction
from .tracing import record_user_feedback


DEFAULT_USER = "self"   # 1인 운영 시 기본 ID


def recent_interactions(
    subscriber_id: str = DEFAULT_USER,
    limit: int = 5,
    days: int = 30,
) -> list[dict]:
    """최근 대화 N개. days일 안의 것만."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with get_session() as s:
        rows = (
            s.query(Interaction)
            .filter(Interaction.subscriber_id == subscriber_id)
            .filter(Interaction.created_at >= cutoff)
            .order_by(desc(Interaction.created_at))
            .limit(limit)
            .all()
        )
        out = []
        for r in rows:
            out.append({
                "interaction_id": r.interaction_id,
                "question": r.question,
                "answer": r.answer,
                "cited_versions": r.cited_versions or [],
                "created_at": r.created_at.isoformat(),
                "feedback": r.feedback,
            })
        return out


def _escape_like(text: str) -> str:
    """SQL LIKE 와일드카드 이스케이프."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def all_interactions(
    subscriber_id: Optional[str] = None,
    limit: int = 200,
    search: Optional[str] = None,
) -> list[dict]:
    """전체 대화 (UI 조회용). search 가 있으면 question/answer LIKE."""
    with get_session() as s:
        q = s.query(Interaction)
        if subscriber_id:
            q = q.filter(Interaction.subscriber_id == subscriber_id)
        if search:
            like = f"%{_escape_like(search)}%"
            q = q.filter(
                (Interaction.question.ilike(like, escape="\\"))
                | (Interaction.answer.ilike(like, escape="\\"))
            )
        rows = q.order_by(desc(Interaction.created_at)).limit(limit).all()
        return [{
            "interaction_id": r.interaction_id,
            "subscriber_id": r.subscriber_id,
            "question": r.question,
            "answer": r.answer,
            "cited_versions": r.cited_versions or [],
            "created_at": r.created_at.isoformat(),
            "feedback": r.feedback,
            "elapsed_ms": r.elapsed_ms,
        } for r in rows]


def build_context_for_llm(
    subscriber_id: str = DEFAULT_USER,
    max_pairs: int = 3,
) -> list[dict]:
    """LLM 메시지 history 에 prepend 할 이전 Q/A.
    return: [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}, ...]
    """
    recent = recent_interactions(subscriber_id, limit=max_pairs, days=14)
    # 오래된 순 (LLM 컨텍스트는 시간순)
    recent.reverse()
    history = []
    for it in recent:
        history.append({"role": "user", "content": it["question"]})
        # 답변은 너무 길면 잘라서
        ans = it["answer"]
        if len(ans) > 600:
            ans = ans[:600] + "..."
        history.append({"role": "assistant", "content": ans})
    return history


def stats(subscriber_id: Optional[str] = None) -> dict:
    """대화 통계."""
    with get_session() as s:
        q = s.query(Interaction)
        if subscriber_id:
            q = q.filter(Interaction.subscriber_id == subscriber_id)
        total = q.count()
        # 지난 7일
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent = q.filter(Interaction.created_at >= cutoff).count()
        return {"total": total, "last_7_days": recent}


def delete_interaction(interaction_id: str, subscriber_id: Optional[str] = None) -> bool:
    """interaction_id 삭제. subscriber_id 를 주면 소유자 확인(타인 삭제 방지)."""
    with get_session() as s:
        q = s.query(Interaction).filter(Interaction.interaction_id == interaction_id)
        if subscriber_id:
            q = q.filter(Interaction.subscriber_id == subscriber_id)
        row = q.first()
        if not row:
            return False
        s.delete(row)
        return True



def set_feedback(interaction_id: str, value: int) -> dict:
    """value: +1 / -1 / 0(clear). Langfuse score 동기화."""
    if value not in (1, -1, 0):
        return {"ok": False}
    with get_session() as s:
        row = s.query(Interaction).filter(Interaction.interaction_id == interaction_id).first()
        if not row:
            return {"ok": False}
        row.feedback = value if value != 0 else None
        trace_id = row.trace_id
    langfuse_ok = False
    if value in (1, -1) and trace_id:
        langfuse_ok = record_user_feedback(trace_id, value)
    return {"ok": True, "langfuse_recorded": langfuse_ok}
