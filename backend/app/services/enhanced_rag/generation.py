"""Enhanced RAG — 응답 생성 모듈.

기존 LLM 폴백 체인(chat_with_fallback)을 재사용 → provider 장애 시 자동 전환.
반환: (answer, provider, model, token_usage)
"""
from __future__ import annotations

import logging

from ..llm.base import Message
from ..llm.fallback import chat_with_fallback

from .config import RAGConfig

logger = logging.getLogger(__name__)


class ResponseGenerator:
    def __init__(self, config: RAGConfig):
        self.config = config

    async def generate(
        self, query: str, system_prompt: str, user_prompt: str
    ) -> tuple[str, str, str, dict]:
        try:
            resp, llm, _chain = await chat_with_fallback(
                [Message(role="user", content=user_prompt)],
                primary_provider=self.config.generation_provider,
                temperature=self.config.generation_temperature,
                max_tokens=self.config.generation_max_tokens,
                system=system_prompt,
            )
            tokens = {
                "prompt": resp.prompt_tokens,
                "completion": resp.completion_tokens,
                "total": resp.total_tokens,
            }
            return resp.text, resp.provider or llm.provider_name, resp.model, tokens
        except Exception as e:
            logger.error("[rag-gen] 생성 실패: %s", e)
            # LLM 사용 불가 시 컨텍스트만 반환 (검색 결과는 여전히 유효)
            return (
                "(응답 생성 실패: LLM provider 를 사용할 수 없습니다. 검색된 컨텍스트를 확인하세요.)",
                "none",
                "",
                {},
            )
