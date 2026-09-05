"""번역 품질 검증 (Translation Quality Verifier).

중국어 번역 정확도를 자동으로 평가한다:
- 용어집 준수율(glossary compliance): 원문에 등장한 한국어 용어가 중국어로 올바르게 치환되었는가
- 길이/구조 이상 탐지: 번역문/원문 길이비가 비정상이면 환각/누락 의심
- CJK 문자 포함 여부: 번역 결과가 실제 중국어인가
- (플러그형) 역번역 유사도 / LLM-as-judge: 외부 엔진 연결 시 quality_score 에 반영

결과는 trans_meta.review_status 로 이어져, flagged 청크는 인간 검수 큐(human-in-the-loop)로 분류된다.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .config import BilingualConfig

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[一-鿿]")


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


@dataclass
class VerificationResult:
    quality_score: float
    glossary_compliance: float       # 0~1
    length_ratio: float
    length_ok: bool
    has_target_script: bool          # 중국어 CJK 포함 여부
    review_status: str               # auto | flagged
    applied_terms: list[str] = field(default_factory=list)
    flagged_terms: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_meta(self) -> dict:
        return {
            "quality_score": round(self.quality_score, 4),
            "glossary_compliance": round(self.glossary_compliance, 4),
            "length_ratio": round(self.length_ratio, 4),
            "review_status": self.review_status,
            "applied_terms": self.applied_terms,
            "flagged_terms": self.flagged_terms,
        }


def verify_translation(
    ko_text: str,
    zh_text: str,
    applied_terms: list[str],
    present_terms: list[str],
    cfg: BilingualConfig,
    *,
    back_translation_score: Optional[float] = None,
) -> VerificationResult:
    """한중 번역 1건을 검증한다.

    applied_terms: 번역 과정에서 중국어로 치환된 한국어 용어
    present_terms : 원문(ko_text)에 실제로 등장한 한국어 용어 후보
    back_translation_score: 있으면 quality_score 에 가중 반영 (0~1, None=미사용)
    """
    ko_len = len(ko_text or "")
    zh_len = len(zh_text or "")

    # 1) 용어집 준수율
    present = list(dict.fromkeys(present_terms))  # 중복 제거 보존 순서
    applied = list(dict.fromkeys(applied_terms))
    if present:
        compliance = len(applied) / len(present)
        flagged_terms = [t for t in present if t not in set(applied)]
    else:
        compliance = 1.0
        flagged_terms = []

    # 2) 길이/구조 이상
    if ko_len == 0:
        length_ratio = 0.0
    else:
        length_ratio = zh_len / ko_len
    length_ok = (
        cfg.length_ratio_min <= length_ratio <= cfg.length_ratio_max
        if ko_len > 0
        else (zh_len == 0)
    )

    # 3) 목표 언어(CJK) 포함
    has_script = _has_cjk(zh_text)

    # 4) 종합 점수 (가중 합성)
    length_component = 1.0 if length_ok else 0.3
    script_component = 1.0 if (has_script or zh_len == 0) else 0.0
    base = compliance * 0.55 + length_component * 0.30 + script_component * 0.15
    if back_translation_score is not None:
        # 역번역 유사도가 있으면 신뢰도 보강 (40% 반영)
        base = base * 0.6 + float(back_translation_score) * 0.4
    quality_score = max(0.0, min(1.0, base))

    notes: list[str] = []
    if not length_ok:
        notes.append(f"길이비 비정상({length_ratio:.2f})")
    if not has_script and zh_len:
        notes.append("중국어(CJK) 문자 미포함 — 번역 실패 의심")
    if flagged_terms:
        notes.append(f"미치환 용어 {len(flagged_terms)}건")

    review_status = "auto"
    if quality_score < cfg.quality_min_score:
        review_status = "flagged"
    if compliance < cfg.glossary_compliance_min:
        review_status = "flagged"
    if not has_script and zh_len:
        review_status = "flagged"

    return VerificationResult(
        quality_score=quality_score,
        glossary_compliance=compliance,
        length_ratio=length_ratio,
        length_ok=length_ok,
        has_target_script=has_script,
        review_status=review_status,
        applied_terms=applied,
        flagged_terms=flagged_terms,
        notes=notes,
    )
