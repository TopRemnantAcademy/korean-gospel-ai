"""한중 번역 서브시스템 (Translator 추상화 + 버전 관리 용어집).

설계 원칙:
- Translator 는 플러그인 인터페이스. glossary(규칙/오프라인), llm, deepl 구현을 교체 가능.
- Glossary 는 버전 관리 JSON. 번역 전 청크에 등장하는 용어만 추출해 프롬프트/치환에 주입 →
  토큰 효율 + 신학 용어 일관성 동시 확보.
- TranslationManager 가 오케스트레이션: 번역 → 검증(trans_meta) → 결과 반환.
- 원문(한국어)은 절대 덮어쓰지 않음. 번역문은 보조 필드.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from .config import BilingualConfig
from .verification import verify_translation

logger = logging.getLogger(__name__)

_DEFAULT_GLOSSARY = Path(__file__).parent / "data" / "glossary.json"


@dataclass
class Term:
    ko: str
    zh: str
    category: str = "other"
    note: str = ""
    en: str = ""  # 영어 대응어 (데이터만 준비, 코드 주입은 추후)


@dataclass
class TranslationResult:
    zh_text: str
    applied_terms: list[str] = field(default_factory=list)
    present_terms: list[str] = field(default_factory=list)
    engine: str = "glossary"
    glossary_version: str = ""


class Glossary:
    """버전 관리 한국어→중국어 용어집."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.version = "unknown"
        self.source_lang = "ko"
        self.target_lang = "zh"
        self.terms: list[Term] = []
        self._by_ko: dict[str, Term] = {}
        self._sorted: list[Term] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.warning("[glossary] 용어집 없음: %s — 빈 용어집으로 동작", self.path)
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.version = data.get("version", "unknown")
        self.source_lang = data.get("source_lang", "ko")
        self.target_lang = data.get("target_lang", "zh")
        self.terms = [
            Term(
                ko=t["ko"],
                zh=t["zh"],
                en=t.get("en", ""),
            )
            for t in data.get("terms", [])
        ]
        self._by_ko = {t.ko: t for t in self.terms}
        # 긴 용어부터 치환 (하위 문자열 오치환 방지)
        self._sorted = sorted(self.terms, key=lambda t: -len(t.ko))
        logger.info("[glossary] 로드 완료 v=%s, %d개 용어", self.version, len(self.terms))

    def translate(self, text: str) -> tuple[str, list[str], list[str]]:
        """용어 사전 기반 치환. 미번역 부분은 원문 그대로 유지(부분 번역)."""
        result = text
        applied: list[str] = []
        for term in self._sorted:
            if term.ko in result:
                result = result.replace(term.ko, term.zh)
                applied.append(term.ko)
        present = [t.ko for t in self.terms if t.ko in text]
        return result, applied, present

    def context_prompt(self, text: str) -> str:
        """청크에 등장하는 용어만 추출해 번역 지침용 프롬프트 조각 생성."""
        present = [t for t in self.terms if t.ko in text]
        if not present:
            return ""
        lines = [f"- {t.ko} → {t.zh}" for t in present]
        return "신학/고유명사 번역 지침:\n" + "\n".join(lines)


@runtime_checkable
class Translator(Protocol):
    async def translate(self, ko_text: str, ctx: Optional[str] = None) -> TranslationResult: ...


class GlossaryTranslator:
    """규칙 기반(오프라인) 번역기. 용어집 치환만 수행. 외부 의존 없음."""

    def __init__(self, glossary: Glossary, cfg: BilingualConfig):
        self.glossary = glossary
        self.cfg = cfg

    async def translate(self, ko_text: str, ctx: Optional[str] = None) -> TranslationResult:
        zh, applied, present = self.glossary.translate(ko_text)
        return TranslationResult(
            zh_text=zh,
            applied_terms=applied,
            present_terms=present,
            engine=self.cfg.translation_engine_label,
            glossary_version=self.glossary.version,
        )


class LLMTranslator:
    """LLM 기반 번역기 (Tencent DeepSeek-V4 우선).

    - primary provider 로 tencent 를 사용 (chat_with_fallback).
    - 용어집(glossary) 기반 지침을 시스템 프롬프트에 주입해 신학 용어 일관성 확보.
    - 호출 실패(키 부재/네트워크/타임아웃) 시 GlossaryTranslator 로 자동 폴백.
    """

    def __init__(self, glossary: Glossary, cfg: BilingualConfig):
        self.glossary = glossary
        self.cfg = cfg

    async def translate(self, ko_text: str, ctx: Optional[str] = None) -> TranslationResult:
        guideline = self.glossary.context_prompt(ko_text)
        system = (
            "你是一位专业的韩语到中文神学翻译专家。"
            "请将以下韩语文本翻译成自然流畅的中文。\n"
            "严格遵守以下术语翻译规则:\n"
            f"{guideline}\n"
            "要求: 保留原文的宗教含义和感情色彩, 不要添加解释或注释。"
        )
        user_msg = ko_text
        if ctx:
            user_msg = f"[上下文参考]\n{ctx}\n\n[请翻译]\n{ko_text}"

        try:
            from ..llm.fallback import chat_with_fallback
            from ..llm.base import Message

            messages = [Message(role="user", content=user_msg)]
            resp, _llm, _attempts = await chat_with_fallback(
                messages,
                primary_provider="tencent",
                system=system,
                temperature=0.2,
                max_tokens=max(800, int(len(ko_text) * 2)),  # R-7: 긴 청크 truncate 방지
            )
            zh_text = (resp.text or "").strip()
            if not zh_text:
                raise ValueError("LLM 번역 결과가 비어 있습니다.")
        except Exception as e:
            logger.warning(
                "[llm-translator] LLM 번역 실패 → GlossaryTranslator 폴백: %s", e
            )
            return await GlossaryTranslator(self.glossary, self.cfg).translate(ko_text, ctx)

        # applied: 소스(ko_text)에서 발견된 용어
        # present: 번역 결과(zh_text)에서 실제로 발견된 중국어 용어 — 독립 계산
        applied = [t.ko for t in self.glossary.terms if t.ko in ko_text]
        present = [t.zh for t in self.glossary.terms if t.zh and t.zh in zh_text]
        return TranslationResult(
            zh_text=zh_text,
            applied_terms=applied,
            present_terms=present,
            engine="llm",
            glossary_version=self.glossary.version,
        )


class TranslationManager:
    """번역 오케스트레이션: 번역 → 검증(trans_meta) → 결과."""

    def __init__(self, cfg: BilingualConfig):
        self.cfg = cfg
        path = Path(cfg.glossary_path) if cfg.glossary_path else _DEFAULT_GLOSSARY
        self.glossary = Glossary(path)
        if cfg.translator == "llm":
            self.translator: Translator = LLMTranslator(self.glossary, cfg)
        else:
            self.translator = GlossaryTranslator(self.glossary, cfg)

    async def translate_chunk(
        self, ko_text: str, neighbor_ctx: Optional[str] = None
    ) -> tuple[TranslationResult, dict]:
        """청크 1건 번역 + 검증. (TranslationResult, trans_meta) 반환."""
        ctx = neighbor_ctx if (self.cfg.context_preservation and neighbor_ctx) else None
        res = await self.translator.translate(ko_text, ctx)

        trans_meta: dict = {
            "engine": res.engine,
            "glossary_version": res.glossary_version,
            "translated_at": _now_iso(),
            "source_lang": self.cfg.source_lang,
            "target_lang": self.cfg.primary_lang,
            "review_policy": self.cfg.review_policy,
        }

        if self.cfg.auto_verify:
            vr = verify_translation(
                ko_text, res.zh_text, res.applied_terms, res.present_terms, self.cfg
            )
            trans_meta.update(vr.to_meta())
            if vr.review_status == "flagged":
                trans_meta["notes"] = vr.notes
        else:
            trans_meta["review_status"] = "auto"
            trans_meta["quality_score"] = None

        return res, trans_meta


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
