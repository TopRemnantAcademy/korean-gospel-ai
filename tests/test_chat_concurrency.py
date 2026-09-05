"""T4 — 채팅 경로 동시성 안정성 테스트.

인사 fast-path(is_greeting_or_smalltalk)와 ZZ 정규화(preprocess_for_chunking)는
채팅 요청마다 호출되는 순수 함수다. 다수의 동시 호출에서도 결정적(race-free)
결과를 내는지 검증한다.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.app.api import chat_pipeline
from backend.app.services.normalizer import preprocess_for_chunking

_GREETINGS = ["안녕하세요", "감사합니다", "你好", "hello", "반갑습니다"]
_QUESTIONS = [
    "하나님의 사랑은 무엇인가요?",
    "기도하는 방법을 알려주세요",
    "구원이란 무엇인가요?",
]


def test_greeting_fastpath_concurrent_async():
    items = _GREETINGS * 50 + _QUESTIONS * 50

    async def run():
        return await asyncio.gather(
            *[asyncio.to_thread(chat_pipeline.is_greeting_or_smalltalk, x) for x in items]
        )

    results = asyncio.run(run())
    assert len(results) == len(items)
    # 결정적: 같은 입력은 항상 같은 결과 (greeting 들은 모두 True 여야 함)
    greet_results = results[: len(_GREETINGS) * 50]
    assert all(greet_results)
    question_results = results[len(_GREETINGS) * 50 :]
    assert not any(question_results)


def test_preprocess_concurrent_threads():
    texts = ["하나님 의 말씀은 은혜입니다 그런데 믿음이 부족합니다"] * 100

    def work():
        return [preprocess_for_chunking(t) for t in texts]

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(work) for _ in range(8)]
        outs = [f.result() for f in futs]

    # 모든 워커가 동일한 결정적 결과를 산출 (공유 상태 없음)
    base = outs[0]
    for o in outs[1:]:
        assert o == base
    for line in base:
        assert ". " in line
