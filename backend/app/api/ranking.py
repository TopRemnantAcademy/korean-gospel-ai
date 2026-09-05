"""실시간 질문 랭킹 API (공개).

네이버 지식iN 질문 랭킹처럼 '지금 많이 묻는 질문'을 실시간으로 노출한다.
인증 없이 누구나 조회 가능 (트렌딩 카드와 동일 정책).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query

from ..services import trending_service

log = logging.getLogger("gospel-api.ranking")
router = APIRouter(tags=["ranking"])

# 热门问答种子集（单一真源）. lang 별로 curated 시드를 보관.
# 실제 인터랙션이 부족한 언어는 시드로兜底合并하여 항상 해당 언어 콘텐츠를 보장.
_SEED_FILES = {
    "zh": "popular_questions_zh.json",
    "ko": "popular_questions_ko.json",
}
_SEED_DIR = Path(__file__).resolve().parents[3] / "data"


def _load_seed(lang: str) -> list[dict]:
    fname = _SEED_FILES.get(lang)
    if not fname:
        return []
    path = _SEED_DIR / fname
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("questions", []) if isinstance(data, dict) else data
    except Exception:  # pragma: no cover - 种子缺失不影响真实排行
        log.exception("인기질문 시드 로드 실패: %s", path)
        return []


def _merge_seed(rankings: list[dict], limit: int, lang: str) -> list[dict]:
    """해당 언어 실시간 랭킹이 부족하면 curated 시드로 채운다(중복 제거)."""
    if len(rankings) >= limit:
        return rankings[:limit]
    seeds = _load_seed(lang)
    have = {(r.get("question") or "").strip().lower() for r in rankings}
    out = list(rankings)
    for s in seeds:
        if len(out) >= limit:
            break
        q = (s.get("question") or "").strip()
        if not q or q.lower() in have:
            continue
        have.add(q.lower())
        out.append({
            "rank": len(out) + 1,
            "question": q,
            "count": 0,
            "count_7d": 0,
            "direction": "new",
            "rank_change": None,
            "category": s.get("category", "信仰"),
            "snapshot_id": None,
            "has_detail": False,
            "is_seed": True,
        })
    return out


@router.get("/ranking/questions")
def get_question_ranking(
    limit: int = Query(10, ge=1, le=30),
    period: str = Query("7d", pattern="^(7d|30d|all)$"),
    lang: str = Query(None),
):
    """실시간 질문 랭킹을 반환한다.

    - limit: 1~30 (기본 10)
    - period: 7d(최근 7일) / 30d / all(전체)
    - lang=zh: 真实中文交互不足时以策展中文种子兜底合并
    """
    try:
        rankings = trending_service.get_realtime_question_ranking(limit=limit, period=period, lang=lang)
    except Exception:
        log.exception("[ranking/questions] 집계 오류")
        rankings = []
    if lang in _SEED_FILES:
        rankings = _merge_seed(rankings, limit, lang)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "rankings": rankings,
    }
