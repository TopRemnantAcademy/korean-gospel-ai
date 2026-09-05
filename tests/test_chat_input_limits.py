"""회귀 테스트: ChatRequest / ChatMessage 입력 길이 제한.

DoS 방지: query/history/content/user_context 에 max_length 를 추가하여
메모리 소모 및 비용 기반 DoS 를 원천 차단.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models.schemas import ChatMessage, ChatRequest

# ── query max_length=2000 ──


def test_query_within_limit_accepted():
    req = ChatRequest(query="하나님의 사란은 무엇인가요?")
    assert req.query == "하나님의 사란은 무엇인가요?"


def test_query_at_boundary_accepted():
    """정확히 2000자는 허용."""
    req = ChatRequest(query="A" * 2000)
    assert len(req.query) == 2000


def test_query_over_limit_rejected():
    """2001자는 거부."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(query="A" * 2001)
    assert "max_length" in str(exc_info.value).lower() or "2000" in str(exc_info.value)


def test_query_empty_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(query="")


def test_query_whitespace_only_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(query="   ")


# ── history max_length=50 ──


def test_history_within_limit_accepted():
    history = [ChatMessage(role="user", content="test") for _ in range(50)]
    req = ChatRequest(query="test", history=history)
    assert len(req.history) == 50


def test_history_over_limit_rejected():
    history = [ChatMessage(role="user", content="test") for _ in range(51)]
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(query="test", history=history)
    assert "max_length" in str(exc_info.value).lower() or "50" in str(exc_info.value)


# ── ChatMessage.content max_length=10000 ──


def test_message_content_within_limit_accepted():
    msg = ChatMessage(role="user", content="B" * 10000)
    assert len(msg.content) == 10000


def test_message_content_over_limit_rejected():
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="B" * 10001)


# ── ChatMessage.role max_length=20 ──


def test_message_role_within_limit_accepted():
    msg = ChatMessage(role="user", content="hello")
    assert msg.role == "user"


def test_message_role_over_limit_rejected():
    with pytest.raises(ValidationError):
        ChatMessage(role="X" * 21, content="hello")


# ── user_context max_length=2000 ──


def test_user_context_within_limit_accepted():
    req = ChatRequest(query="test", user_context="C" * 2000)
    assert len(req.user_context) == 2000


def test_user_context_over_limit_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(query="test", user_context="C" * 2001)


def test_user_context_none_accepted():
    req = ChatRequest(query="test", user_context=None)
    assert req.user_context is None
