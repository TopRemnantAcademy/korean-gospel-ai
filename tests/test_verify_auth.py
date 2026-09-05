"""_verify_auth 회귀 테스트 — 유효하지 않은 토큰으로 임의 신원 차용 방지 (T-강화).

수정 전: Bearer 토큰 검증 실패 시 요청 본문의 user_id 로 silently fallback →
         위조/만료 토큰으로도 임의 sub_id 사칭 가능 (쿼터 탈취/비인증 채팅).
수정 후: 인증을 시도했으나 실패하면 401 로 거부.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.app.api import chat_pipeline


@pytest.fixture
def fake_verify(monkeypatch):
    # _verify_auth 는 `from .auth import _verify_token` 을 lazy import 하므로
    # 원천 모듈 속성을 패치하면 호출 시점에 반영된다.
    with patch("backend.app.api.auth._verify_token") as m:
        yield m


def test_valid_token_with_matching_user_id(fake_verify):
    # 유효 토큰 sub 와 요청 user_id 가 일치하면 토큰 sub 를 사용
    fake_verify.return_value = "token-sub"
    assert chat_pipeline._verify_auth("Bearer tok123", "token-sub") == "token-sub"


def test_valid_token_without_user_id(fake_verify):
    # 유효 토큰인데 user_id 가 없으면 토큰 sub 를 사용
    fake_verify.return_value = "token-sub"
    assert chat_pipeline._verify_auth("Bearer tok123", None) == "token-sub"


def test_invalid_bearer_token_rejected_with_401(fake_verify):
    # 토큰을 제시했으나 검증 실패 → 위조/만료 토큰으로 신원 fallback 금지
    fake_verify.return_value = None
    with pytest.raises(HTTPException) as exc:
        chat_pipeline._verify_auth("Bearer forged", "victim-id")
    assert exc.value.status_code == 401


def test_valid_token_mismatched_user_id_rejected_with_403(fake_verify):
    fake_verify.return_value = "token-sub"
    with pytest.raises(HTTPException) as exc:
        chat_pipeline._verify_auth("Bearer tok123", "other-user")
    assert exc.value.status_code == 403


def test_no_auth_header_falls_back_to_requested_user():
    # 인증 헤더가 아예 없으면 기존 신뢰 클라이언트 경로대로 요청 user_id 를 신뢰
    assert chat_pipeline._verify_auth(None, "req-user") == "req-user"


def test_no_auth_and_no_user_returns_default():
    assert chat_pipeline._verify_auth(None, None) == chat_pipeline.DEFAULT_USER
