"""평가 하네스 순수 헬퍼 (Wave 2 / AI-AGENT-WORK).

- 위기 하드 바이패스 결정적 체크 (LLM/RAG 미사용 → CI 게이트로 안전)
- 팩추얼 검색 지표 (Hit@k / MRR / nDCG) — enhanced_rag.evaluation.RAGEvaluator 재사용

DB/LLM 의존성 없이 단위 테스트 가능하도록 순수 함수로 구성한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .addiction_care import (
    assess_addiction_query,
    build_crisis_bypass_response,
    CrisisLevel,
)
from .enhanced_rag.evaluation import RAGEvaluator
from .enhanced_rag.profile_boost import compute_profile_boost

# 핫라인 포함 여부 판별 힌트 (언어 무관)
_HOTLINE_HINTS = (
    "1340", "988", "116 123",
    "hotline", "lifeline",
)


def _has_hotline(text: str) -> bool:
    """응답 문자열에 위기 핫라인(전화번호/명칭)이 포함됐는지 관대하게 판별."""
    t = (text or "").lower()
    for hint in _HOTLINE_HINTS:
        if hint.lower() in t:
            return True
    # 폴백: 3~5자리 숫자(핫라인 번호 후보)
    if re.search(r"\b\d{3,5}\b", text or ""):
        return True
    return False


def normalize_doc_id(s: str | None) -> str:
    """doc id 정규화: 확장자 제거 + 공백/괄호/특수문자 제거 + 소문자.

    파일명 스템('01_요한복음_3장.txt')과 실제 doc_id('01_요한복음_3장')를
    동등 비교하기 위함. 부분 포함 매칭에도 사용된다.
    """
    if not s:
        return ""
    s = str(s)
    for ext in (".txt", ".md", ".json", ".csv", ".pdf"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]
    s = re.sub(r"[\s()（）\[\]<>\"']+", "", s)
    return s.lower()


@dataclass
class CrisisEvalResult:
    triggered: bool
    crisis_level: str | None
    detected_risk_level: str | None = None
    response: str = ""
    hotline_present: bool = False
    expected_bypass: bool = False
    passed: bool = False


def crisis_bypass_check(
    query: str,
    *,
    target_lang: str = "ko",
    expected_bypass: bool = True,
) -> CrisisEvalResult:
    """위기 하드 바이패스 결정적 체크 (LLM/RAG 미사용, 규칙 기반).

    assess_addiction_query 는 규칙 기반(결정적)이므로 위기 게이트로 안전하다.
    - triggered: CrisisLevel.critical 감지 여부
    - hotline_present: 결정적 응답에 핫라인 포함 여부
    - passed: (triggered == expected_bypass) AND (triggered 이면 핫라인 필수)
    """
    assessment = assess_addiction_query(query)
    triggered = assessment.crisis_level == CrisisLevel.critical
    response = build_crisis_bypass_response(assessment, target_lang=target_lang)
    hotline_present = _has_hotline(response)
    passed = (triggered == expected_bypass) and (not triggered or hotline_present)
    return CrisisEvalResult(
        triggered=triggered,
        crisis_level=getattr(assessment.crisis_level, "value", None),
        response=response,
        hotline_present=hotline_present,
        expected_bypass=expected_bypass,
        passed=passed,
    )


def extract_retrieved_doc_ids(items: Sequence[Any]) -> list[str]:
    """RetrievedItem/RetrievedPoint/딕셔너리 목록에서 doc_id 추출.

    메타데이터 우선, 폴백 체인: doc_id → source → title → point.id
    """
    out: list[str] = []
    for it in items or []:
        if isinstance(it, dict):
            meta = it.get("metadata") or {}
            point = it.get("point", it)
        else:
            meta = getattr(it, "metadata", None) or {}
            point = it
        did = (
            meta.get("doc_id")
            or meta.get("source")
            or meta.get("title")
            or getattr(point, "doc_id", None)
            or getattr(point, "id", None)
        )
        if did:
            out.append(str(did))
    return out


def retrieval_metrics(
    retrieved_items: Sequence[Any],
    expected_doc_ids: Iterable[str],
    k: int = 5,
) -> dict:
    """팩추얼 검색 지표 계산. expected_doc_ids 는 doc-level id 후보(관대 매칭).

    Returns:
        {"hit_at_k", "mrr", "ndcg_at_k", "k", "retrieved_count", "note?"}
    """
    expected_raw = [str(x) for x in (expected_doc_ids or []) if x]
    if not expected_raw:
        return {
            "hit_at_k": None, "mrr": None, "ndcg_at_k": None, "k": k,
            "retrieved_count": 0,
            "note": "expected_doc_ids 비어있음 — 회귀 기준 미설정",
        }

    expected_norm = {normalize_doc_id(e) for e in expected_raw}
    retrieved_raw = extract_retrieved_doc_ids(retrieved_items)
    retrieved_norm = [normalize_doc_id(r) for r in retrieved_raw]

    # 관대 매칭: 정규화 동등 또는 부분 포함이면 relevant 로 인정
    rel: set[str] = set(expected_norm)
    for rn in retrieved_norm:
        for en in expected_norm:
            if en and (en in rn or rn in en):
                rel.add(rn)
                break

    class _Wrap:
        __slots__ = ("doc_id", "chunk_id")

        def __init__(self, did: str):
            self.doc_id = did
            self.chunk_id = did

    wrapped = [_Wrap(rn) for rn in retrieved_norm]
    metrics = RAGEvaluator.eval_retrieval(
        cases=[{"retrieved": wrapped, "relevant": rel, "relevant_is_doc": True}],
        k=k,
    )
    return {
        "hit_at_k": metrics.hit_rate,
        "mrr": metrics.mrr,
        "ndcg_at_k": metrics.ndcg_at_k,
        "k": k,
        "retrieved_count": len(wrapped),
    }


# ── Wave C: 프로필 부스트 오프라인 결정적 게이트 ──
@dataclass
class ProfileBoostResult:
    meta: dict
    profile: dict
    boost: float
    expected: float
    passed: bool
    note: str = ""


def profile_boost_self_test() -> list[ProfileBoostResult]:
    """이식된 매트릭스/누적 로직을 결정적 단위 검증 (RAG 불필요 → CI 게이트).

    검증 포인트:
    - 매트릭스 셀 값 정확성
    - gospel_core_tag 부스트
    - 다단계(target_salvation_stage) 누적 (과거 break 버그 재발 방지)
    - 다라방(darakbang) 부스트
    """
    cases = [
        # (meta, profile, 기대 boost, 설명)
        (
            {"target_salvation_stage": ["seeker"]},
            {"salvation_status": "unknown"},
            0.40 + 0.15,  # 매트릭스 unknown×seeker 0.40 + assume_saved=False(seeker 단계) 0.15
            "unknown×seeker: 매트릭스 0.40 + assume_saved=False(seeker) 0.15",
        ),
        (
            {"target_salvation_stage": ["seeker"], "gospel_core_tag": True},
            {"salvation_status": "seeker"},
            0.35 + 0.30 + 0.15,  # seeker×seeker 0.35 + gospel_core 0.30 + assume_saved=False(seeker) 0.15
            "seeker×seeker 0.35 + gospel_core 0.30 + assume_saved=False(seeker) 0.15",
        ),
        (
            # 다단계 누적 — 과거 break 버그 재발 방지
            {"target_salvation_stage": ["seeker", "gospel_core"]},
            {"salvation_status": "unknown"},
            0.40 + 0.30 + 0.15,  # seeker 0.40 + gospel_core 0.30 + assume_saved=False 0.15
            "다단계 누적: seeker 0.40 + gospel_core 0.30 + assume_saved=False 0.15",
        ),
        (
            {"darakbang_tier": "darakbang_leader"},
            {"darakbang_role": "leader", "is_darakbang_member": True, "darakbang_verified": True},
            0.40,
            "leader×darakbang_leader 0.40",
        ),
        # ── 추가: 과거 미검증 분기 보강 ──
        (
            # assume_saved=True → discipleship/assured 단계 문서에 +0.25
            {"target_salvation_stage": ["discipleship"]},
            {"salvation_status": "assured", "assume_saved": True},
            0.25 + 0.25,  # 매트릭스 assured×discipleship 0.25 + assume_saved 0.25
            "assume_saved=True: 매트릭스 0.25 + assume_saved discipleship 0.25",
        ),
        (
            # 비회원(darakbang_role 있으나 is_darakbang_member=False) → 다라방 부스트 0
            {"darakbang_tier": "darakbang_leader"},
            {"salvation_status": "unknown", "darakbang_role": "leader", "is_darakbang_member": False},
            0.0,
            "비회원: 다라방 부스트 0",
        ),
        (
            # role 있으나 darakbang_verified=False → 다라방 부스트 0
            {"darakbang_tier": "darakbang_leader"},
            {"darakbang_role": "leader", "is_darakbang_member": True, "darakbang_verified": False},
            0.0,
            "미인증: 다라방 부스트 0",
        ),
    ]
    results: list[ProfileBoostResult] = []
    for meta, profile, expected, note in cases:
        got = compute_profile_boost(meta, profile)
        results.append(
            ProfileBoostResult(
                meta=meta, profile=profile, boost=got,
                expected=expected, passed=abs(got - expected) < 1e-9, note=note,
            )
        )
    return results
