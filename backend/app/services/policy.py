"""Tone/Policy 검증 레이어.
- 입력 검증: 룰 기반 (yaml) 차단어/위험질문
- 출력 검증: LLM-as-judge 로 신학적 톤 + 아첨금지 5개 항목 검증
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-4 — JudgeResult Pydantic 확장 (FlatteryFlags + violation_flags)
#                  judge_output 5개 아첨 항목 추가 + prompts/policy_judge.py 연동
# Reason: ORDERS_COUNSELING.md G-4 — 톤 검증 부재 해소, Layer B 구성
# Related: prompts/policy_judge.py (NEW), services/regen.py (G-4.6에서 소비)
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

from ..config import settings


@dataclass
class PolicyResult:
    allowed: bool
    reason: str = ""           # 차단/수정 이유
    severity: str = "ok"       # ok | warn | block
    flags: list[str] = None    # 발동된 룰 코드들

    def __post_init__(self):
        if self.flags is None:
            self.flags = []


# ✏️ AI-CHANGE 2026-05-26 [Claude]: G-4 — 아첨금지 5개 항목 플래그 (Layer B)
class FlatteryFlags(BaseModel):
    flattery: bool = False              # 인격·질문 칭찬
    excessive_praise: bool = False      # "정말 좋은 질문" 류
    emotional_pandering: bool = False   # 감정 단순 추인, 권면 없음
    childish_friendliness: bool = False # 이모지·의성어·친근체
    unbiblical_agreement: bool = False  # 비성경적 주장 동조


# ✏️ AI-CHANGE 2026-05-26 [Claude]: G-4 — JudgeResult Pydantic 모델로 교체 (flattery_flags + violation_flags 추가)
class JudgeResult(BaseModel):
    pass_: bool                         # 톤 OK?
    score: float                        # 0.0 ~ 1.0
    notes: str = ""
    flattery_flags: FlatteryFlags = FlatteryFlags()
    violation_flags: list[str] = []     # Layer C(regen) 가 소비


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    p = settings.root_dir / settings.policy_rules_path
    if not p.exists():
        return {"input_blocklist": [], "input_warnings": [], "output_must_avoid": []}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


# ---------- Input policy ----------
def check_input(text: str) -> PolicyResult:
    if not settings.policy_enabled:
        return PolicyResult(allowed=True, severity="ok")
    rules = _load_rules()
    flags: list[str] = []

    # 차단 (정규식 가능)
    for code, pat in (rules.get("input_blocklist") or {}).items():
        try:
            if re.search(pat, text, flags=re.IGNORECASE):
                flags.append(code)
                return PolicyResult(
                    allowed=False, severity="block",
                    reason=f"입력이 정책에 의해 차단되었습니다 ({code}).",
                    flags=flags,
                )
        except re.error:
            continue

    # 경고만 (통과시키되 flag)
    for code, pat in (rules.get("input_warnings") or {}).items():
        try:
            if re.search(pat, text, flags=re.IGNORECASE):
                flags.append(code)
        except re.error:
            continue

    return PolicyResult(allowed=True, severity="warn" if flags else "ok", flags=flags)


# ---------- Output policy (LLM-as-judge) ----------
async def judge_output(question: str, answer: str, target_lang: str = "ko") -> JudgeResult:
    """LLM judge 가 신학적 톤 + 아첨금지 5개 항목을 검증. policy_enabled=False 면 자동 통과."""
    if not settings.policy_enabled:
        return JudgeResult(pass_=True, score=1.0)

    from .llm.factory import get_llm
    from .llm.base import Message
    from ..prompts.policy_judge import get_judge_prompt
    import json

    llm = get_llm()
    judge_system = get_judge_prompt(target_lang)
    user = f"[질문]\n{question}\n\n[답변]\n{answer}"

    _fallback = JudgeResult(pass_=True, score=0.5, notes="judge 파싱 실패")

    try:
        resp = await llm.chat(
            [Message(role="user", content=user)],
            temperature=0.0, max_tokens=300, system=judge_system,
        )
        m = re.search(r"\{.*\}", resp.text, flags=re.DOTALL)
        if not m:
            return _fallback
        data = json.loads(m.group())

        flags = FlatteryFlags(
            flattery=bool(data.get("flattery", False)),
            excessive_praise=bool(data.get("excessive_praise", False)),
            emotional_pandering=bool(data.get("emotional_pandering", False)),
            childish_friendliness=bool(data.get("childish_friendliness", False)),
            unbiblical_agreement=bool(data.get("unbiblical_agreement", False)),
        )
        # 5개 항목 중 하나라도 true 면 violation_flags 에 추가
        violations = [k for k, v in flags.model_dump().items() if v]
        pass_base = bool(data.get("pass", True))
        pass_final = pass_base and not violations

        return JudgeResult(
            pass_=pass_final,
            score=float(data.get("score", 0.5)),
            notes=str(data.get("notes", "")),
            flattery_flags=flags,
            violation_flags=violations,
        )
    except Exception as e:
        return JudgeResult(pass_=True, score=0.5, notes=f"judge 오류: {e}")
