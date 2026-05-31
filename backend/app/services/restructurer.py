"""구조화 — 구어체 설교를 섹션 헤딩 + 문어체 마크다운으로 재편집 (Stage 2, LLM).

핵심 원칙:
- 내용 추가·삭제 절대 금지 (의미 100% 보존)
- 구어체 → 자연스러운 문어체로 다듬기만
- 주제 단위로 ## 섹션 헤딩 자동 생성 → 의미 단위 청킹의 기반

비용 통제: 긴 문서는 윈도우 단위로 분할해 호출. 문서당 호출 = ⌈길이/window⌉.
안전장치: 출력이 입력의 60% 미만이면 "내용 소실 의심" → 원문 유지 + 경고.

LLM 독립: chat_with_fallback() 경유 → DeepSeek/Gemini 등 .env로 교체 가능.
"""
from __future__ import annotations

import logging

from ..config import settings
from .llm.base import Message
from .llm.fallback import chat_with_fallback

logger = logging.getLogger(__name__)


_RESTRUCTURE_SYSTEM = """당신은 한국어 설교·강의 원고를 정리하는 편집자입니다.

규칙 (반드시 준수):
1. 내용을 추가하거나 삭제하지 마세요. 의미를 절대 바꾸지 마세요.
2. 구어체("~거야", "~잖아")를 자연스러운 설명체로만 다듬으세요. 신학 용어·성경 인용은 그대로 두세요.
3. 주제가 바뀌는 지점마다 `## 소제목` 형식의 마크다운 헤딩을 넣으세요. 소제목은 그 단락의 핵심을 8자 내외로.
4. 출력은 마크다운 본문만. 설명·머리말·꼬리말 금지.
5. 원문의 모든 핵심 내용(성경구절, 예화, 적용)을 빠짐없이 보존하세요."""


def _make_windows(text: str, window_chars: int) -> list[str]:
    """문단 경계를 존중하며 window_chars 근처로 분할."""
    paras = text.split("\n\n")
    windows: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for p in paras:
        if buf and buf_len + len(p) > window_chars:
            windows.append("\n\n".join(buf))
            buf, buf_len = [], 0
        buf.append(p)
        buf_len += len(p) + 2
    if buf:
        windows.append("\n\n".join(buf))
    return windows or [text]


async def restructure_text(
    text: str,
    *,
    title: str = "",
    llm_provider: str | None = None,
) -> tuple[str, dict]:
    """구어체 텍스트를 섹션 헤딩 + 문어체 마크다운으로 변환.

    Returns:
        (structured_markdown, info)
        info = {"windows": n, "llm": provider, "fallback_used": bool, "warnings": [...]}
    """
    if not text or not text.strip():
        return text, {"windows": 0, "warnings": ["empty input"]}

    window_chars = getattr(settings, "ingest_restructure_window_chars", 3000)
    windows = _make_windows(text, window_chars)

    out_parts: list[str] = []
    warnings: list[str] = []
    used_provider = None

    for i, win in enumerate(windows):
        user_msg = f"[문서 제목] {title}\n\n[정리할 원고]\n{win}" if title else win
        try:
            # max_tokens: 입력보다 넉넉히 (출력이 입력보다 길 수 있음). 하한 1500.
            _max_out = max(1500, min(6000, int(len(win) * 1.5)))
            resp, llm, _ = await chat_with_fallback(
                [Message(role="user", content=user_msg)],
                primary_provider=llm_provider,
                system=_RESTRUCTURE_SYSTEM,
                temperature=0.2,
                max_tokens=_max_out,
            )
            used_provider = llm.provider_name
            result = (resp.text or "").strip()

            # 안전장치: 출력이 입력의 60% 미만 → 내용 소실 의심, 원문 유지
            if len(result) < len(win) * 0.6:
                warnings.append(f"window#{i}: 출력 과소({len(result)}/{len(win)}) → 원문 유지")
                out_parts.append(win)
            else:
                out_parts.append(result)
        except Exception as e:
            logger.warning("restructure window#%d 실패: %s — 원문 유지", i, e)
            warnings.append(f"window#{i}: LLM 실패 → 원문 유지")
            out_parts.append(win)

    structured = "\n\n".join(out_parts)
    return structured, {
        "windows": len(windows),
        "llm": used_provider,
        "warnings": warnings,
    }
