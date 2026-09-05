"""P4 #2 — 프롬프트 인젝션 방어.

사용자 제공 배경 정보(user_context)와 대화 기록(history)은 **불신 데이터**로 취급한다.
시스템 프롬프트 경계를 깨지 않도록:
  1) 제어 문자 제거
  2) 시스템 프롬프트 경계를 깨려는 인젝션 패턴 중화
  3) 길이 제한
  4) 대화 기록에서 신뢰되지 않는 role(system 등) 제거 — 시스템 프롬프트는
     오직 신뢰된 소스에서만 구성된다.
"""
from __future__ import annotations

import re

# 시스템 프롬프트 경계를 깨려는 흔한 패턴 (한/영)
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(the\s+)?(system|previous)\s+prompt",
    r"system\s+prompt\s*(를|을)?\s*(무시|파기|변경|덮어쓰기|재정의)",
    r"이전\s*(지시|명령|프롬프트)?\s*(무시|잊|파기|변경)",
    r"you\s+are\s+now\s+a",
    r"새로운\s*(역할|지시|시스템)\s*:",
    r"```(?:system|instruction)",
    r"<system>",
    r"<\s*system",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE | re.MULTILINE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_CONTEXT_LEN = 2000
MAX_HISTORY_LEN = 1500
_ALLOWED_HISTORY_ROLES = {"user", "assistant", "tool"}


def sanitize_untrusted_text(text: str, max_len: int = MAX_CONTEXT_LEN) -> str:
    """불신 텍스트를 데이터로 정리: 제어문자 제거, 인젝션 패턴 중화, 길이 제한."""
    if not text:
        return ""
    text = _CONTROL_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)  # 연속 개행 정규화
    # 인젝션 패턴을 중화 — 모델이 지시(instruction)로 해석하지 못하게
    text = _INJECTION_RE.sub("[redacted:instruction-injection-attempt]", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text.strip()


def sanitize_history(messages: list[dict]) -> list[dict]:
    """대화 기록에서 신뢰되지 않는 role(system/unknown)을 제거하고 내용을 정리한다.

    공격자가 기록에 system 메시지를 주입해 시스템 프롬프트를 덮는 것을 차단.
    """
    clean: list[dict] = []
    for m in messages or []:
        role = str(m.get("role") or "").strip().lower()
        content = m.get("content") or ""
        if role not in _ALLOWED_HISTORY_ROLES:
            continue  # system/unknown 등은 무시
        clean.append({"role": role, "content": sanitize_untrusted_text(content, MAX_HISTORY_LEN)})
    return clean
