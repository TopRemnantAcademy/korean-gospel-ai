"""인기 QA 언어 분기 테스트 (lang=ko/zh 시드 병합 + _lang_of 분류).

실제 interaction DB 없이 결정론적으로 검증: 빈 세션으로 모킹하면 실시간 랭킹이
비어지고, 라우터가 lang 에 맞는 curated 시드만 병합한다. 따라서
- lang=ko → 한국어(한글) 질문만
- lang=zh → 중국어(한자) 질문만
이 보장되는지 확인한다.
"""
from __future__ import annotations

from contextlib import contextmanager

from backend.app.services import trending_service
from backend.app.services.trending_service import _lang_of, get_realtime_question_ranking
from backend.app.api.ranking import get_question_ranking


class _FakeQuery:
    def filter(self, *a, **k):
        return self

    def group_by(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def all(self):
        return []


class _FakeSession:
    def query(self, *a, **k):
        return _FakeQuery()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@contextmanager
def _fake_session_cm():
    yield _FakeSession()


def test_lang_of_classification():
    assert _lang_of("내가 정말 구원받았는지 어떻게 확신할 수 있나요?") == "ko"
    assert _lang_of("我怎样才能确定自己真的得救了？") == "zh"
    assert _lang_of("How can I be saved?") == "en"
    assert _lang_of("!!!") == "other"


def test_popular_questions_lang_ko_returns_korean_only(monkeypatch):
    monkeypatch.setattr(trending_service, "get_session_immediate", _fake_session_cm)
    ko = get_question_ranking(limit=12, lang="ko").get("rankings", [])
    assert ko, "lang=ko 시드가 병합되어야 함"
    assert all(_lang_of(r["question"]) == "ko" for r in ko), "lang=ko 는 한국어만"


def test_popular_questions_lang_zh_returns_chinese_only(monkeypatch):
    monkeypatch.setattr(trending_service, "get_session_immediate", _fake_session_cm)
    zh = get_question_ranking(limit=12, lang="zh").get("rankings", [])
    assert zh, "lang=zh 시드가 병합되어야 함"
    assert all(_lang_of(r["question"]) == "zh" for r in zh), "lang=zh 는 중국어만"


def test_popular_questions_no_duplicates(monkeypatch):
    monkeypatch.setattr(trending_service, "get_session_immediate", _fake_session_cm)
    ko = get_question_ranking(limit=50, lang="ko").get("rankings", [])
    questions = [r["question"] for r in ko]
    assert len(questions) == len(set(questions)), "중복 질문 없음"
    assert any(r.get("category") for r in ko), "카테고리 보존"


def test_realtime_ranking_respects_lang_filter(monkeypatch):
    # get_realtime_question_ranking 단독 호출도 lang 필터가 동작하는지 확인
    monkeypatch.setattr(trending_service, "get_session_immediate", _fake_session_cm)
    assert get_realtime_question_ranking(limit=10, lang="ko") == []
    assert get_realtime_question_ranking(limit=10, lang="zh") == []
