"""Enhanced RAG — 프로필 기반 soft boost (개인화 재순위).

레거시 `services/retriever.py` 의 프로필 부스트 + 매트릭스를
단일 소스로 이식. 두 경로 모두 이 모듈을 참조하므로 매트릭스가 한 곳에서
관리된다(Wave E 단일화 정신). 공개 API `compute_profile_boost` 를 통해
레거시 retriever / enhanced_rag / 평가 하네스가 동일 함수를 사용한다.

의존성 없음 — 순수 함수 모듈. 단위 테스트/오프라인 게이트에서 자유롭게 import 가능.
"""
from __future__ import annotations

# (사용자 salvation_status, 자료 target_salvation_stage) → boost
SALVATION_BOOST_MATRIX: dict[tuple[str, str], float] = {
    ("unknown", "seeker"): 0.40,
    ("unknown", "uncertain"): 0.20,
    ("unknown", "gospel_core"): 0.30,
    ("seeker", "seeker"): 0.35,
    ("seeker", "gospel_core"): 0.50,
    ("uncertain", "assurance"): 0.45,
    ("uncertain", "uncertain"): 0.25,
    ("uncertain", "gospel_core"): 0.35,
    ("assured", "discipleship"): 0.25,
    ("assured", "assured"): 0.10,
    ("mature", "discipleship"): 0.30,
    ("mature", "leadership"): 0.20,
    ("mature", "pastoral"): 0.15,
}

# (darakbang_role, 자료 darakbang_tier) → boost
DARAKBANG_BOOST_MATRIX: dict[tuple[str, str], float] = {
    ("member", "darakbang_general"): 0.20,
    ("member", "darakbang_deep"): 0.15,
    ("leader", "darakbang_general"): 0.10,
    ("leader", "darakbang_deep"): 0.30,
    ("leader", "darakbang_leader"): 0.40,
    ("pastor", "darakbang_deep"): 0.25,
    ("pastor", "darakbang_leader"): 0.35,
    ("pastor", "pastoral"): 0.40,
}


def compute_profile_boost(meta: dict, profile: dict) -> float:
    """프로필 기반 점수 부스트 누적 계산.

    과거 버그: 다단계(target_salvation_stage) 문서에서 첫 매치에서 break 하여
    나머지 단계의 부스트가 누락됨. 이제 모든 매치 단계를 누적(sum)한다.

    `meta`는 문서/청크 메타데이터(`target_salvation_stage`, `gospel_core_tag`,
    `darakbang_tier`). `profile`은 사용자 프로필
    (`salvation_status`, `darakbang_role`, `is_darakbang_member`,
    `darakbang_verified`, `assume_saved`).
    """
    total_boost = 0.0
    salvation_status = profile.get("salvation_status", "unknown")
    darakbang_role = (
        profile.get("darakbang_role")
        if profile.get("is_darakbang_member")
        else None
    )
    darakbang_verified = profile.get("darakbang_verified", False)
    assume_saved = profile.get("assume_saved", False)

    doc_stages = meta.get("target_salvation_stage") or []
    if isinstance(doc_stages, str):
        doc_stages = [doc_stages]
    for stage in doc_stages:
        b = SALVATION_BOOST_MATRIX.get((salvation_status, stage), 0.0)
        if b:
            total_boost += b  # ✅ 누적 (기존 break 버그 수정)

    if meta.get("gospel_core_tag") and salvation_status in ("unknown", "seeker", "uncertain"):
        total_boost += 0.30

    if assume_saved:
        if "discipleship" in doc_stages or "assured" in doc_stages:
            total_boost += 0.25
    else:
        if "seeker" in doc_stages or "gospel_core" in doc_stages:
            total_boost += 0.15

    if darakbang_role and darakbang_verified:
        doc_tier = meta.get("darakbang_tier")
        if doc_tier:
            total_boost += DARAKBANG_BOOST_MATRIX.get((darakbang_role, doc_tier), 0.0)

    return total_boost
