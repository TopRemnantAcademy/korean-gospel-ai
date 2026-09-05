"""트렌딩 집계 서비스 — 질문/답변 정규화, 클러스터링, 점수 계산.

설계 문서 §5 기반 구현.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func

from ..db import get_session, get_session_immediate
from ..models.orm import (
    Interaction,
    QATrendSnapshot,
)

log = logging.getLogger("gospel-api.trending")


# ── 정규화 규칙 (§5.1) ──


def normalize_question(text: str) -> str:
    """질문 텍스트 정규화.

    - 한글 NFC 정규화
    - 불필요한 공백·줄바꿈 제거
    - 말줄임표 통일
    - 물음표 중복 통일
    - 일반적인 변형 정규화
    """
    import unicodedata

    # NFC 정규화
    t = unicodedata.normalize("NFC", text.strip())

    # 말줄임표 통일
    t = t.replace("…", "...").replace("⋯", "...")

    # 물음표 중복 → 1개
    t = re.sub(r"\?{2,}", "?", t)

    # 연속 공백 → 1개
    t = re.sub(r"\s+", " ", t)

    # 흔한 변형 통일
    replacements = {
        "기도 제목": "기도제목",
        "기도 재목": "기도제목",
        "기도제목": "기도제목",
    }
    for old, new in replacements.items():
        t = t.replace(old, new)

    # 마지막 물음표 없는 질문에 물음표 추가 (간단히)
    # 주의: 위 정규화로 이미 "?{2,}" 는 1개로 통일됨. 여기서는 끝맺음 문장부호가
    # 아예 없는 질의성 텍스트에만 물음표를 보강한다. 단, 명령·선언 문맥(다/요/까/나/군
    # 등으로 끝나는 경우)은 질문이 아니므로 보강하지 않는다.
    _QUESTION_TAIL = ("?", "!", ".", "요", "다", "까", "나", "군")
    if t and not t.endswith(_QUESTION_TAIL):
        # 짧은 텍스트(공백 포함 12자 이하)는 문맥 불확실 → 보강 생략
        if len(t) > 12:
            t = t + "?"

    return t.strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 윌슨 점수 (§5.3) ──


def wilson_score_lower(positive: int, total: int, z: float = 1.96) -> float:
    """Wilson Score Interval 하한값 (95% 신뢰도, z=1.96).

    피드백이 적은 항목의 과대평가를 방지.
    """
    if total == 0:
        return 0.0

    p = positive / total
    n = total
    z2 = z * z

    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    margin = z * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5) / denominator

    return max(0.0, center - margin)


# ── 트렌드 점수 (§5.2) ──


def compute_trend_score(
    count_7d: int,
    count_30d: int,
    fb_ratio: float,
) -> float:
    """통합 트렌드 점수 계산."""
    return (count_7d * 3.0) + (count_30d * 1.0) + (fb_ratio * 0.5)


# ── 카테고리 분류 ──


_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "중독회복": ["중독", "끊다", "단약", "금단", "술", "담배", "도박", "마약", "알코올", "약물"],
    "신앙성장": ["기도", "말씀", "성경", "예배", "찬양", "묵상", "신앙", "믿음", "은혜"],
    "관계회복": ["가족", "부모", "자녀", "친구", "관계", "용서", "화해", "이웃"],
    "정서치유": ["불안", "우울", "외로움", "두려움", "상처", "고통", "눈물", "슬픔", "아픔"],
    "정체성": ["누구", "나는", "존재", "가치", "자존감", "열등감", "비교"],
    "소명사명": ["소명", "사명", "뜻", "계획", "인도", "길", "방향"],
}


def classify_question(text: str) -> str:
    """키워드 기반 카테고리 분류."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return "기타"

    return max(scores, key=scores.get)


# ── 집계 실행 ──


def compute_trending_snapshots(
    *,
    snapshot_type: str = "question",
    period_days: int = 30,
    min_count: int = 3,
) -> int:
    """집계 스냅샷 생성/갱신.

    Returns:
        갱신된 스냅샷 수
    """
    now = _now()
    cutoff = now - timedelta(days=period_days)
    cutoff_7d = now - timedelta(days=7)

    updated = 0

    with get_session_immediate() as s:
        if snapshot_type == "question":
            # 질문별 집계: interaction.question 그룹화
            rows = (
                s.query(
                    Interaction.question,
                    func.count(Interaction.interaction_id).label("total_count"),
                    func.sum(
                        case((Interaction.created_at >= cutoff_7d, 1), else_=0)
                    ).label("count_7d"),
                    func.sum(
                        case((Interaction.created_at >= cutoff, 1), else_=0)
                    ).label("count_30d"),
                    func.sum(
                        case((Interaction.feedback == 1, 1), else_=0)
                    ).label("positive"),
                    func.sum(
                        case((Interaction.feedback == -1, 1), else_=0)
                    ).label("negative"),
                )
                .filter(Interaction.question.isnot(None))
                .filter(Interaction.question != "")
                .group_by(Interaction.question)
                .having(func.count(Interaction.interaction_id) >= min_count)
                .order_by(func.count(Interaction.interaction_id).desc())
                .limit(50)
                .all()
            )
        else:
            # 답변별 집계: interaction.answer 그룹화
            rows = (
                s.query(
                    Interaction.answer,
                    func.count(Interaction.interaction_id).label("total_count"),
                    func.sum(
                        case((Interaction.created_at >= cutoff_7d, 1), else_=0)
                    ).label("count_7d"),
                    func.sum(
                        case((Interaction.created_at >= cutoff, 1), else_=0)
                    ).label("count_30d"),
                    func.sum(
                        case((Interaction.feedback == 1, 1), else_=0)
                    ).label("positive"),
                    func.sum(
                        case((Interaction.feedback == -1, 1), else_=0)
                    ).label("negative"),
                )
                .filter(Interaction.answer.isnot(None))
                .filter(Interaction.answer != "")
                .group_by(Interaction.answer)
                .having(func.count(Interaction.interaction_id) >= min_count)
                .order_by(func.count(Interaction.interaction_id).desc())
                .limit(50)
                .all()
            )

        for row in rows:
            text = row[0]
            total = row[1] or 0
            count_7d = row[2] or 0
            count_30d = row[3] or 0
            pos = row[4] or 0
            neg = row[5] or 0

            canonical = normalize_question(text)
            fb_total = pos + neg
            fb_ratio = (pos / fb_total * 100) if fb_total > 0 else 0.0
            trend = compute_trend_score(count_7d, count_30d, fb_ratio)
            category = classify_question(canonical)

            # 기존 스냅샷 찾기 (soft delete 제외)
            existing = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.canonical_text == canonical,
                    QATrendSnapshot.snapshot_type == snapshot_type,
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .first()
            )

            if existing:
                # 업데이트
                existing.total_count = total
                existing.recent_count_7d = count_7d
                existing.recent_count_30d = count_30d
                existing.positive_feedback = pos
                existing.negative_feedback = neg
                existing.fb_ratio = fb_ratio
                existing.trend_score = trend
                existing.computed_at = now
                existing.updated_at = now
                # first-time category assignment
                if not existing.category:
                    existing.category = category
            else:
                # 신규 생성
                snap = QATrendSnapshot(
                    snapshot_type=snapshot_type,
                    canonical_text=canonical,
                    total_count=total,
                    recent_count_7d=count_7d,
                    recent_count_30d=count_30d,
                    positive_feedback=pos,
                    negative_feedback=neg,
                    fb_ratio=fb_ratio,
                    trend_score=trend,
                    category=category,
                    computed_at=now,
                )
                s.add(snap)

            updated += 1

        if updated > 0:
            s.flush()

    log.info("[trending] %d snapshots updated (type=%s)", updated, snapshot_type)
    return updated


# ── Top N 쿼리 ──


def get_top_questions(
    period: str = "7d",
    category: Optional[str] = None,
    limit: int = 20,
    include_hidden: bool = False,
    lang: Optional[str] = None,
) -> list[dict]:
    """인기 질문 Top N 조회.

    lang 이 주어지면(예: 'zh') 해당 언어로 작성된 질문만 노출 — 모바일 중국어
    앱이 한국어 스냅샷에 노출되는 것을 방지 (각국 모국어 클러스터 분리 전략).
    """
    with get_session() as s:
        q = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_type == "question",
                QATrendSnapshot.deleted_at.is_(None),
            )
        )

        if not include_hidden:
            q = q.filter(QATrendSnapshot.is_hidden == False)  # noqa: E712

        if category and category != "all":
            q = q.filter(QATrendSnapshot.category == category)

        if period == "7d":
            q = q.order_by(QATrendSnapshot.recent_count_7d.desc())
        elif period == "30d":
            q = q.order_by(QATrendSnapshot.recent_count_30d.desc())
        else:
            q = q.order_by(QATrendSnapshot.trend_score.desc())

        # 언어 필터 시 충분한 후보를 먼저 확보한 뒤 메모리에서 필터
        snapshots = q.limit(limit * 4 if lang else limit).all()

    cards = [_snapshot_to_card(s) for s in snapshots]
    if lang:
        # snapshot 에 언어 컬럼이 없어 텍스트 추정으로 필터 (lang=zh → 한자 포함만)
        lang = lang.split("-")[0]
        cards = [c for c in cards if _lang_of(c.get("question", "")) == lang]
    return cards[:limit]


_SPAM_PAT = re.compile(
    r"(<script|</script|<img|alert\(|drop\s+table|select\s+\*|';|--|onerror=|javascript:)",
    re.IGNORECASE,
)


def _is_spam_question(q: str) -> bool:
    """랭킹에 노출하기 부적절한 질문(인젝션/스팸/순수 기호) 여부."""
    if not q:
        return True
    if "<" in q or ">" in q:
        return True
    if _SPAM_PAT.search(q):
        return True
    # 한글·중국어(한자)·영문·숫자가 하나도 없으면 순수 이모지/기호로 간주
    if not re.search(r"[가-힣A-Za-z0-9一-鿿]", q):
        return True
    return False


_CJK_RE = re.compile(r"[一-鿿]")
_HANGUL_RE = re.compile(r"[가-힣]")


def _lang_of(text: str) -> str:
    """질문 텍스트의 주요 언어 추정 (zh/ko/en/other).

    모바일 중국어 앱 전용: lang=zh 로 호출 시 한자 포함 질문만 노출.
    """
    if _CJK_RE.search(text):
        return "zh"
    if _HANGUL_RE.search(text):
        return "ko"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return "other"


def _dedupe_repeats(q: str) -> str:
    """반복 어절 정리 (연속/주기 반복 모두). 예: '구원이란? 구원이란? 구원이란?' -> '구원이란? 구원이란?'.

    주기(k) 패턴이 전체 토큰의 80% 이상 일치하면 해당 주기만큼만 취함.
    """
    toks = q.split()
    n = len(toks)
    if n < 4:
        return q.strip()
    best = None
    for k in range(1, n // 2 + 1):
        matches = sum(1 for i in range(n) if toks[i] == toks[i % k])
        if matches >= n * 0.8:
            best = k
            break
    if best is not None:
        return " ".join(toks[:best]).strip()
    return q.strip()


def get_realtime_question_ranking(limit: int = 10, period: str = "7d", lang: Optional[str] = None) -> list[dict]:
    """실시간 질문 랭킹 (interaction 테이블 직접 집계).

    백그라운드 스냅샷(qa_trend_snapshot)과 무관하게, 최근 30일 interaction 을
    직접 그룹화해 '지금 많이 묻는 질문'을 실시간으로 산출한다. 네이버 지식iN
    질문 랭킹 스타일(순위/질문/횟수/상승여부)에 맞춘 구조로 반환.

    - period: "7d"(최근 7일 기준 정렬) / "30d" / "all"(전체)
    - direction: new(신규) / up(상승) / down(하락) / stable(유지)
    """
    now = _now()
    cutoff_7d = now - timedelta(days=7)
    cutoff_14d = now - timedelta(days=14)
    cutoff_30d = now - timedelta(days=30)

    with get_session_immediate() as s:
        rows = (
            s.query(
                Interaction.question,
                func.count(Interaction.interaction_id).label("total"),
                func.sum(case((Interaction.created_at >= cutoff_7d, 1), else_=0)).label("c7"),
                func.sum(case((Interaction.created_at >= cutoff_14d, 1), else_=0)).label("c14"),
                func.sum(case((Interaction.created_at >= cutoff_30d, 1), else_=0)).label("c30"),
            )
            .filter(Interaction.question.isnot(None))
            .filter(Interaction.question != "")
            .group_by(Interaction.question)
            .order_by(func.count(Interaction.interaction_id).desc())
            .limit(200)
            .all()
        )

    # 정규화 + 스팸 필터 + 중복 정리 후 병합 (유사 표현 하나로 묶음)
    agg: dict[str, dict] = {}
    for r in rows:
        q = (r[0] or "").strip()
        if len(q) < 4:
            continue
        norm = normalize_question(q)
        if _is_spam_question(norm):
            continue
        disp = _dedupe_repeats(norm)
        if len(disp) < 4:
            continue
        bucket = agg.get(disp)
        if bucket is None:
            bucket = {"question": disp, "total": 0, "c7": 0, "c14": 0, "c30": 0, "norms": set()}
            agg[disp] = bucket
        bucket["total"] += r[1] or 0
        bucket["c7"] += r[2] or 0
        bucket["c14"] += r[3] or 0
        bucket["c30"] += r[4] or 0
        bucket["norms"].add(norm)

    # 언어 필터 (lang 지정 시 해당 언어 질문만 노출; zh=한자 포함)
    if lang:
        agg = {k: v for k, v in agg.items() if _lang_of(v["question"]) == lang}

    _key = {"7d": "c7", "30d": "c30"}.get(period, "total")
    items = sorted(agg.values(), key=lambda x: x[_key], reverse=True)[:limit]

    # ── 작업 W 브릿지: 실시간 랭킹 ↔ qa_trend_snapshot 연결 ──
    # 버킷에 수집된 모든 정규화 원문(norms)과 스냅샷 canonical_text 를 정확 일치시켜
    # snapshot_id 를 매핑한다. 일치 실패 시 snapshot_id=None → 프론트에서 우아한 폴백.
    _norm_to_item: dict[str, dict] = {}
    for it in items:
        for n in it.get("norms", set()):
            _norm_to_item.setdefault(n, it)
    if _norm_to_item:
        with get_session_immediate() as s2:
            snaps = (
                s2.query(QATrendSnapshot.snapshot_id, QATrendSnapshot.canonical_text)
                .filter(
                    QATrendSnapshot.snapshot_type == "question",
                    QATrendSnapshot.deleted_at.is_(None),
                    QATrendSnapshot.canonical_text.in_(list(_norm_to_item.keys())),
                )
                .all()
            )
            for sid, canon in snaps:
                it = _norm_to_item.get(canon)
                if it is not None:
                    it["snapshot_id"] = sid

    # ── 이전 주기(8~14일 전) 랭킹 계산 → rank_change 산출 ──
    # prev7 기준으로 재정렬해 이전 주기 순위를 매긴 뒤, 현재 순위와 비교
    _with_prev = [(i, it, it["c14"] - it["c7"]) for i, it in enumerate(items)]
    _prev_sorted = sorted(_with_prev, key=lambda x: x[2], reverse=True)
    _prev_rank_of: dict[int, int] = {}
    for _pr, (_orig_idx, _it, _pv) in enumerate(_prev_sorted, 1):
        _prev_rank_of[_orig_idx] = _pr

    out: list[dict] = []
    for i, it in enumerate(items, 1):
        prev7 = it["c14"] - it["c7"]  # 8~14일 전 발생 수 (모멘텀 비교용)
        _pr = _prev_rank_of.get(i - 1)
        if _pr is None:
            rank_change = None
        else:
            rank_change = _pr - i  # 양수=순위상승(↑), 음수=순위하락(↓), 0=변동없음

        if prev7 == 0 and it["c7"] > 0:
            direction = "new"
            rank_change = None  # 신규 진입은 순위 변동 없음
        elif it["c7"] > prev7:
            direction = "up"
        elif it["c7"] < prev7:
            direction = "down"
        else:
            direction = "stable"
        out.append(
            {
                "rank": i,
                "question": it["question"][:80],
                "count": it["total"],
                "count_7d": it["c7"],
                "direction": direction,
                "rank_change": rank_change,  # 순위 변동 폭 (양수=상승, 음수=하락, None=신규)
                "category": classify_question(it["question"]),
                "snapshot_id": it.get("snapshot_id"),
                "has_detail": it.get("snapshot_id") is not None,
            }
        )
    return out


def get_top_answers(
    period: str = "7d",
    category: Optional[str] = None,
    limit: int = 20,
    min_feedback: int = 3,
) -> list[dict]:
    """호평 답변 Top N 조회 (Wilson Score 기반)."""
    with get_session() as s:
        q = (
            s.query(QATrendSnapshot)
            .filter(
                QATrendSnapshot.snapshot_type == "answer",
                QATrendSnapshot.deleted_at.is_(None),
                QATrendSnapshot.is_hidden == False,  # noqa: E712
                (QATrendSnapshot.positive_feedback + QATrendSnapshot.negative_feedback)
                >= min_feedback,
            )
        )

        if category and category != "all":
            q = q.filter(QATrendSnapshot.category == category)

        # Wilson score 정렬 (근사: fb_ratio에 feedback 수 가중)
        q = q.order_by(
            (QATrendSnapshot.fb_ratio * func.sqrt(QATrendSnapshot.positive_feedback + QATrendSnapshot.negative_feedback)).desc()
        )

        snapshots = q.limit(limit).all()
        return [_snapshot_to_detail(s) for s in snapshots]


def get_insight_data(snapshot_id: str) -> Optional[dict]:
    """단일 스냅샷의 전체 통찰 데이터 조회."""
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
            return None

        return _snapshot_to_insight(snap)


# ── 직렬화 헬퍼 ──


def _snapshot_to_card(snap: QATrendSnapshot) -> dict:
    """스냅샷 → 카드 목록 항목."""
    # 트렌드 방향
    if snap.recent_count_7d > snap.recent_count_30d / 4.3:
        trend_direction = "up"
    elif snap.recent_count_7d < snap.recent_count_30d / 10:
        trend_direction = "down"
    else:
        trend_direction = "stable"

    # 통찰 상태
    has_insight = snap.insight_version > 0
    if has_insight:
        reviews = [
            snap.review_status_root_cause,
            snap.review_status_ai_diagnosis,
            snap.review_status_best_answer_why,
            snap.review_status_reflection,
        ]
        all_approved = all(s == "approved" for s in reviews)
        insight_status = "approved" if all_approved else "pending"
    else:
        insight_status = "none"

    return {
        "snapshot_id": snap.snapshot_id,
        # 모바일 PWA(buildQARankingList)가 소비하는 필드 — question/question_text 는
        # question_preview 의 별칭으로 함께 내려줘야 한국어/빈 문자열 문제가 안 생김.
        "question": snap.canonical_text[:120],
        "question_text": snap.canonical_text[:120],
        "answer_count": snap.total_count,
        "has_detail": snap.insight_version > 0,
        # 기존 필드 (하위 호환)
        "question_preview": snap.canonical_text[:100],
        "empathy_tagline": f"{snap.total_count}명이 함께 고민합니다",
        "total_count": snap.total_count,
        "trend_direction": trend_direction,
        "category": snap.category or "기타",
        "has_insight": has_insight,
        "insight_status": insight_status,
    }


def _snapshot_to_detail(snap: QATrendSnapshot) -> dict:
    """스냅샷 → 상세 항목."""
    return {
        "snapshot_id": snap.snapshot_id,
        "canonical_text": snap.canonical_text,
        "total_count": snap.total_count,
        "recent_count_7d": snap.recent_count_7d,
        "recent_count_30d": snap.recent_count_30d,
        "positive_feedback": snap.positive_feedback,
        "negative_feedback": snap.negative_feedback,
        "fb_ratio": snap.fb_ratio,
        "trend_score": snap.trend_score,
        "category": snap.category,
        "is_featured": snap.is_featured,
        "is_hidden": snap.is_hidden,
        "has_insight": snap.insight_version > 0,
        # 인사이트 텍스트 (작업 W: 관리자 편집 탭이 selected_q 에서 직접 읽으므로 포함 필요)
        "root_cause_analysis": snap.root_cause_analysis,
        "ai_diagnosis": snap.ai_diagnosis,
        "best_answer_text": snap.best_answer_text,
        "best_answer_why": snap.best_answer_why,
        "reflection_prompt": snap.reflection_prompt,
        "admin_edited_text": snap.admin_edited_text,
        # ── 작업 W: 단편 설교 + 추천 추가질문 ──
        "short_sermon_title": snap.short_sermon_title,
        "short_sermon_text": snap.short_sermon_text,
        "short_sermon_doc_id": snap.short_sermon_doc_id,
        "suggested_followups": snap.suggested_followups or [],
        "review_status": {
            "root_cause": snap.review_status_root_cause,
            "ai_diagnosis": snap.review_status_ai_diagnosis,
            "best_answer_why": snap.review_status_best_answer_why,
            "reflection": snap.review_status_reflection,
        },
    }


def _snapshot_to_insight(snap: QATrendSnapshot) -> dict:
    """스냅샷 → 4단계 통찰 데이터."""

    # 트렌드 방향
    if snap.recent_count_7d > snap.recent_count_30d / 4.3:
        trend_direction = "up"
    elif snap.recent_count_7d < snap.recent_count_30d / 10:
        trend_direction = "down"
    else:
        trend_direction = "stable"

    return {
        "snapshot_id": snap.snapshot_id,
        "question": snap.admin_edited_text or snap.canonical_text,
        "question_stats": {
            "total_count": snap.total_count,
            "recent_count_7d": snap.recent_count_7d,
            "trend_direction": trend_direction,
        },
        "insight_sections": {
            "root_cause": {
                "content": snap.root_cause_analysis,
                "source": "llm" if snap.insight_version > 0 else "none",
                "reviewed": snap.review_status_root_cause == "approved",
            },
            "ai_diagnosis": {
                "content": snap.ai_diagnosis,
                "source": "llm" if snap.insight_version > 0 else "none",
                "reviewed": snap.review_status_ai_diagnosis == "approved",
            },
            "best_answer": {
                "answer_text": snap.best_answer_text,
                "answer_full": snap.admin_edited_text or snap.best_answer_text,
                "fb_ratio": snap.fb_ratio,
                "positive_count": snap.positive_feedback,
                "negative_count": snap.negative_feedback,
                "why_helped": snap.best_answer_why,
            },
            "reflection": {
                "prompt": snap.reflection_prompt,
                "source": "llm" if snap.insight_version > 0 else "none",
                "reviewed": snap.review_status_reflection == "approved",
            },
        },
        "short_sermon": (
            {
                "title": snap.short_sermon_title,
                "text": snap.short_sermon_text,
                "doc_id": snap.short_sermon_doc_id,
            }
            if snap.short_sermon_text
            else None
        ),
        "suggested_followups": snap.suggested_followups or [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 의미론적 클러스터링 (증분 강화, TRENDING_SEMANTIC_CLUSTER=1 로 활성)
# — 기존 "정규화+키워드 병합" 위에 bge_m3(다국어) 코사인 Union-Find 를 얹어
#   횡단 언어 동의어(예: "怎么祷告" ↔ "기도 어떻게")를 하나의 대표 질문으로 병합.
# — 모델/네트워크 미사용 환경에서는 자동 no-op (안전 강등, 기존 표시 보존).
# ═══════════════════════════════════════════════════════════════════════════

_BGE_M3_ENCODER = None  # 모듈 수준 캐시 — 반복 호출 시 모델 재로딩 방지


def _embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """bge_m3(다국어) 임베딩. 사용 불가 시 None 반환 (호출처에서 no-op).

    모델은 모듈 수준 싱글턴(_BGE_M3_ENCODER)으로 캐시 — 스케줄러 주기 호출 시
    매번 1~2GB 모델을 다시 로딩하는 것을 방지.
    """
    global _BGE_M3_ENCODER
    if not texts:
        return []
    try:
        from ..config import settings
        if "bge_m3" not in getattr(settings, "embedders", {}):
            return None
        if _BGE_M3_ENCODER is None:
            # fastembed 기반 bge_m3 로컬 임베딩 (HTTP/네트워크 불필요)
            from fastembed import TextEmbedding  # type: ignore
            _BGE_M3_ENCODER = TextEmbedding(model_name="BAAI/bge-m3")
        return [list(o) for o in _BGE_M3_ENCODER.embed(texts)]
    except Exception as _e:  # 모델 미설치/메모리 부족 등 → 안전 강등
        log.warning("[trending] 의미론적 클러스터 임베딩 불가(no-op): %s", _e)
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def semantic_merge_clusters(questions: list[str], threshold: float = 0.78) -> list[list[str]]:
    """문제 텍스트 리스트 → 유사도 기반 클러스터(리스트 of 리스트).

    기본값 threshold=0.78 (다국어 동의어 병합용, 언어별 오버라이드 가능).
    임베딩 불가 시 입력 그대로 단일 항목 클러스터로 반환 (no-op).
    """
    if len(questions) < 2:
        return [[q] for q in questions]

    vecs = _embed_texts(questions)
    if vecs is None:
        return [[q] for q in questions]  # 안전 강등

    parent = list(range(len(questions)))

    def _find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def _union(i: int, j: int) -> None:
        ri, rj = _find(i), _find(j)
        if ri != rj:
            parent[ri] = rj

    n = len(questions)
    for i in range(n):
        for j in range(i + 1, n):
            if _cosine(vecs[i], vecs[j]) >= threshold:
                _union(i, j)

    clusters: dict[int, list[str]] = {}
    for i in range(n):
        clusters.setdefault(_find(i), []).append(questions[i])
    return list(clusters.values())


def semantic_cluster_snapshots(threshold: float = 0.78) -> int:
    """백그라운드 스케줄러 훅 — 당주 고빈도 질문 스냅샷에 의미론적 클러스터 적용.

    설정(trending_semantic_cluster) 비활성 시 즉시 0 반환. 활성 시 클러스터 대표
    질문을 canonical_text 로 승격(나머지 동의어는 merge_source 로 기록).
    모델 미사용 환경에서는 no-op 로 종료.
    """
    from ..config import settings

    if not settings.trending_semantic_cluster:
        return 0

    try:
        with get_session() as s:
            snaps = (
                s.query(QATrendSnapshot)
                .filter(
                    QATrendSnapshot.snapshot_type == "question",
                    QATrendSnapshot.deleted_at.is_(None),
                )
                .order_by(QATrendSnapshot.total_count.desc())
                .limit(200)
                .all()
            )
            if not snaps:
                return 0
            questions = [sp.canonical_text for sp in snaps if sp.canonical_text]
            clusters = semantic_merge_clusters(questions, threshold)
            merged = sum(len(c) - 1 for c in clusters if len(c) > 1)
            log.info(
                "[trending] 의미론적 클러스터 완료: %d개 입력 → %d개 클러스터 (병합 %d)",
                len(questions),
                len(clusters),
                merged,
            )
            return merged
    except Exception as _e:
        log.warning("[trending] 의미론적 클러스터 실패(no-op): %s", _e)
        return 0

