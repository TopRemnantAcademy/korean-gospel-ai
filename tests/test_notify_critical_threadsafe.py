"""notify_critical 동시성 회귀 테스트 — _notified_recently 딕셔너리 스레드 안전.

수정 전: 멀티워커/스레드 ASGI 에서 딕셔너리 읽기/할당/순회/pop 이 락 없이
        일어나 "dictionary changed size during iteration" RuntimeError 가능.
수정 후: _notified_lock 로 보호.
"""
from __future__ import annotations

import sys
import threading

from backend.app.logging_setup import notify_critical


def test_notify_critical_threadsafe_no_crash(monkeypatch):
    # Windows 데스크톱 toast(plyer) 분기를 건너뛰어 테스트 부작용(팝업) 방지.
    # 웹훅은 ALERT_WEBHOOK_URL 미설정 환경에서 미발생.
    monkeypatch.setattr(sys, "platform", "linux")

    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            # cooldown_sec=0 으로 매 호출마다 딕셔너리 변경 경로를 통과시킴
            notify_critical(f"concurrency-smoke-{i}", "msg", cooldown_sec=0)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"notify_critical 가 동시성 상황에서 크래시: {errors[:3]}"
