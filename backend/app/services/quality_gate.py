"""품질 게이트 — 인덱싱 직전 청크 자동 검증 (Stage 7).

목적: "조용한 오염" 방지. 빈/중복/과소·과대 청크가 검색 인덱스에
      들어가지 못하게 막고, 차단 사유를 리포트로 반환한다.
      hard_block(자해조장 등) 청크만 제외. legalism/false_assurance 는
      설교문이 해당 주제를 반박할 수 있으므로 경고만 기록하고 통과.

규칙 기반(LLM 무관)이라 빠르고 결정적. safety_service 의 신학왜곡 패턴을 재사용한다.

사용:
    from .quality_gate import run_quality_gate
    result = run_quality_gate(chunks)
    if result.blocked:
        # 인덱싱 중단, result.report 로 사유 확인
    clean_chunks = result.chunks   # 빈/중복/하드블록 제거된 청크
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from ..config import settings
from .chunker import Chunk
from . import safety_service


@dataclass
class GateResult:
    chunks: list[Chunk]                       # 정제된(통과) 청크
    blocked: bool = False                      # 치명 위반으로 인덱싱 차단?
    report: dict = field(default_factory=dict) # 검사 결과 상세
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize_for_hash(text: str) -> str:
    """중복 판정용 정규화 — 공백·문장부호 차이 무시."""
    return re.sub(r"\s+", "", re.sub(r"[^\w가-힣]", "", text))


def _theology_violations(text: str) -> list[str]:
    """신학 왜곡 패턴 검출 (safety_service 재사용)."""
    flags: list[str] = []
    for pat in safety_service.LEGALISM_PATTERNS:
        if pat.search(text):
            flags.append("legalism")
            break
    for pat in safety_service.FALSE_ASSURANCE_PATTERNS:
        if pat.search(text):
            flags.append("false_assurance")
            break
    # HARD_BLOCK_PATTERNS 는 re.Pattern 리스트 (SAFETY_TRIGGERS 와 달리 dict 아님)
    for pat in safety_service.HARD_BLOCK_PATTERNS:
        if pat.search(text):
            flags.append("hard_block")
            break
    return flags


def run_quality_gate(chunks: list[Chunk]) -> GateResult:
    """청크 리스트를 검증·정제. 치명 위반 시 blocked=True."""
    if not chunks:
        return GateResult(chunks=[], blocked=True,
                          errors=["청크가 0개 — 인덱싱할 내용 없음"],
                          report={"total": 0})

    max_tokens = getattr(settings, "ingest_chunk_max_tokens", 512)
    min_tokens = getattr(settings, "ingest_chunk_min_tokens", 50)

    clean: list[Chunk] = []
    seen_hashes: set[str] = set()

    stats = {
        "total": len(chunks),
        "empty_removed": 0,
        "duplicate_removed": 0,
        "oversize": 0,
        "undersize": 0,
        "theology_violations": [],
    }
    warnings: list[str] = []
    errors: list[str] = []

    for c in chunks:
        body = (c.text or "").strip()

        # 1) 빈 청크 제거
        if not body:
            stats["empty_removed"] += 1
            continue

        # 2) 중복 청크 제거 (정규화 해시)
        h = hashlib.sha1(_normalize_for_hash(body).encode("utf-8")).hexdigest()
        if h in seen_hashes:
            stats["duplicate_removed"] += 1
            continue
        seen_hashes.add(h)

        # 3) 과대 청크 — 경고 (chunker가 이미 분할하므로 드묾)
        if c.token_estimate > max_tokens:
            stats["oversize"] += 1
            warnings.append(f"chunk#{c.chunk_id} {c.token_estimate}tok > max({max_tokens})")

        # 4) 과소 청크 — 경고 (chunker가 병합하므로 드묾)
        if c.token_estimate < min_tokens:
            stats["undersize"] += 1

        # 5) 신학 왜곡 검출 — 치명(hard_block)만 청크 제외, 나머지는 경고
        viols = _theology_violations(body)
        if viols:
            stats["theology_violations"].append({"chunk_id": c.chunk_id, "flags": viols})
            if "hard_block" in viols:
                # 극단적 내용만 청크에서 제외 (예: 자해 조장 등)
                errors.append(f"chunk#{c.chunk_id} hard_block 제외: {','.join(viols)}")
                continue  # 이 청크는 clean에 추가하지 않음
            else:
                # legalism, false_assurance 는 주제 토론 가능 → 경고만
                warnings.append(f"chunk#{c.chunk_id} 신학주의: {','.join(viols)} (경고만, 청크 유지)")

        clean.append(c)

    # 차단 조건: 모든 청크가 제거된 경우만 차단
    # (신학 위반은 경고로 처리, 설교문이 율법주의를 반박할 수 있으므로 차단 안 함)
    blocked = not clean

    return GateResult(
        chunks=clean,
        blocked=blocked,
        report=stats,
        warnings=warnings,
        errors=errors,
    )
