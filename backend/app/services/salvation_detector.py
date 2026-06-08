"""D-C14: salvation_detector.py — 매 대화마다 구원 신호 감지.

사용자 발화에서 구원 관련 신호를 LLM으로 추출하고 salvation_status 를 누적 업데이트.
LLM 호출 실패(키 없음 포함) 시 graceful skip — 기존 상태 유지.
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: D-C14 — salvation_detector.py 신규 서비스 (구원 신호 감지 + 상태 전환)
# Reason: ORDERS.md EPIC D-C14
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_STATUS_ORDER = ["unknown", "seeker", "uncertain", "assured", "mature"]
_SIGNAL_TYPES = frozenset({"seeking", "doubting", "confessing", "testifying", "resisting", "maturing"})


@dataclass
class SalvationSignal:
    signal_type: Optional[str] = None
    # None | seeking | doubting | confessing | testifying | resisting | maturing
    suggested_status: Optional[str] = None
    # None = 현재 유지 | unknown | seeker | uncertain | assured | mature
    confidence: float = 0.0         # 0.0~1.0
    evidence_quote: Optional[str] = None  # 결정적 발화 구절
    requires_pastor: bool = False   # 사역자 개입 필요 (자살·이단·심각한 의심)


_NULL_SIGNAL = SalvationSignal()


_DETECTION_SYSTEM = (
    "You are a Korean Christian counseling AI. "
    "Detect salvation-related signals in user speech. "
    "Return ONLY valid JSON, no markdown fences, no extra text."
)


def _build_detection_prompt(text: str, current_status: str) -> str:
    return (
        f"다음 사용자 발화에서 구원 신호를 감지하세요.\n\n"
        f"현재 구원 상태: {current_status}\n"
        f"사용자 발화:\n\"\"\"\n{text}\n\"\"\"\n\n"
        "아래 JSON 형식으로만 응답하세요:\n"
        "{\n"
        '  "signal_type": "seeking|doubting|confessing|testifying|resisting|maturing|null",\n'
        '  "suggested_status": "unknown|seeker|uncertain|assured|mature|null",\n'
        '  "confidence": 0.0,\n'
        '  "evidence_quote": "발화에서 결정적 구절 (없으면 null)",\n'
        '  "requires_pastor": false\n'
        "}\n\n"
        "signal_type 정의:\n"
        "- seeking    : '예수님이 누구세요?', '구원이 뭐예요?' 같은 탐구 발화\n"
        "- doubting   : '내가 정말 구원받았을까요?', '확신이 없어요'\n"
        "- confessing : '예수님을 영접했어요', '주님으로 모셨어요'\n"
        "- testifying : '하나님이 저에게 ~해주셨어요' 같은 간증성 발화\n"
        "- resisting  : '기독교는 그렇게 안 믿어요', 신앙에 저항하는 발화\n"
        "- maturing   : '전도', '제자훈련', '양육', '목양' 같은 성숙 단계\n"
        "- null       : 구원 신호 없음\n\n"
        "requires_pastor=true: 자살·자해·이단·심각한 신앙 위기 신호 감지 시."
    )


async def detect_salvation_signal(text: str, current_status: str) -> SalvationSignal:
    """사용자 발화에서 구원 신호 감지. LLM 실패 시 _NULL_SIGNAL 반환."""
    try:
        from .llm.fallback import chat_with_fallback
        from .llm.base import Message

        messages = [Message(role="user", content=_build_detection_prompt(text, current_status))]
        resp, _llm, _ = await chat_with_fallback(
            messages,
            system=_DETECTION_SYSTEM,
            temperature=0.1,
            max_tokens=300,
        )

        raw = resp.text.strip()
        # 마크다운 펜스 제거
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        signal_type = data.get("signal_type")
        if signal_type == "null" or signal_type not in _SIGNAL_TYPES:
            signal_type = None

        suggested_status = data.get("suggested_status")
        if suggested_status == "null" or suggested_status not in _STATUS_ORDER:
            suggested_status = None

        return SalvationSignal(
            signal_type=signal_type,
            suggested_status=suggested_status,
            confidence=float(data.get("confidence", 0.0)),
            evidence_quote=data.get("evidence_quote") or None,
            requires_pastor=bool(data.get("requires_pastor", False)),
        )

    except Exception as e:
        logger.debug("salvation_detector: LLM 호출 skip — %s", e)
        return _NULL_SIGNAL


def _safe_next_status(current: str, suggested: str) -> Optional[str]:
    """한 번에 최대 1단계 상승. 하강은 제한 없음.

    seeker → assured 직행 차단 — uncertain 경유 강제.
    """
    if current not in _STATUS_ORDER or suggested not in _STATUS_ORDER:
        return None

    ci = _STATUS_ORDER.index(current)
    si = _STATUS_ORDER.index(suggested)

    if si == ci:
        return None  # 변화 없음

    if si > ci + 1:
        # 직행 차단 — 한 단계씩만 상승
        return _STATUS_ORDER[ci + 1]

    return suggested  # 하강 or 1단계 상승 허용


async def transition_status(sub_id: str, signal: SalvationSignal) -> None:
    """누적 신호로 salvation_status 업데이트. SalvationJourney 테이블에 기록.

    한 번에 최대 1단계 이동 (seeker → assured 직행 불허).
    """
    if not signal.signal_type or not signal.suggested_status:
        return

    from ..db import get_session
    from ..models.orm import Subscriber, SalvationJourney

    try:
        with get_session() as s:
            sub = s.query(Subscriber).filter(
                Subscriber.subscriber_id == sub_id
            ).first()
            if not sub:
                return

            current = sub.salvation_status or "unknown"
            new_status = _safe_next_status(current, signal.suggested_status)
            if not new_status:
                return

            # 구원 상태 갱신
            sub.salvation_status = new_status
            sub.salvation_confidence = signal.confidence
            sub.salvation_last_signal_at = datetime.now(datetime.UTC)

            # 여정 기록
            s.add(SalvationJourney(
                subscriber_id=sub_id,
                from_status=current,
                to_status=new_status,
                trigger_signal=signal.signal_type,
                trigger_quote=signal.evidence_quote,
                confidence=signal.confidence,
            ))

    except Exception as e:
        logger.warning("transition_status 실패 (sub_id=%s): %s", sub_id, e)
