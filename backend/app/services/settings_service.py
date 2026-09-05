"""런타임 설정 토글 저장소 (app_setting 테이블).

관리자 설정 페이지에서 변경되는 값(이메일 인증 필수 여부, 질문 할당량 on/off, 티어별 한도)을
DB에 보관하고, config 기본값을 런타임에 오버라이드한다. 민감 값(SMTP 비밀번호 등)은 저장하지 않는다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from ..db import get_session
from ..models.orm import AppSetting
from ..config import settings as _cfg


def _set(key: str, value: Any, vtype: str) -> None:
    sval = "1" if vtype == "bool" and value else ("0" if vtype == "bool" else str(value))
    with get_session() as s:
        row = s.query(AppSetting).filter(AppSetting.key == key).first()
        if not row:
            row = AppSetting(key=key, value_type=vtype)
            s.add(row)
        row.value = sval
        row.value_type = vtype
        row.updated_at = datetime.datetime.utcnow()


def _get(key: str) -> Optional[AppSetting]:
    with get_session() as s:
        return s.query(AppSetting).filter(AppSetting.key == key).first()


_DEFAULTS: dict[str, str] = {}

def register_setting(key: str, default: Any) -> None:
    _DEFAULTS[key] = str(default)


def get_bool(key: str, default: bool) -> bool:
    row = _get(key)
    if row is None or row.value is None:
        fallback = _DEFAULTS.get(key)
        if fallback is not None:
            return fallback.lower() in ("true", "1", "yes")
        return default
    return row.value_type == "bool" and row.value == "1"


def get_int(key: str, default: int) -> int:
    row = _get(key)
    if row is None or row.value is None:
        fallback = _DEFAULTS.get(key)
        if fallback is not None:
            try:
                return int(fallback)
            except (ValueError, TypeError):
                pass
        return default
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return default


def get_str(key: str, default: str) -> str:
    row = _get(key)
    if row is None or row.value is None:
        return _DEFAULTS.get(key, default)
    return row.value


def set_bool(key: str, value: bool) -> None:
    _set(key, value, "bool")


def set_int(key: str, value: int) -> None:
    _set(key, value, "int")


def set_str(key: str, value: str) -> None:
    _set(key, value, "str")


def all_settings() -> list[dict]:
    """관리자 설정 페이지용: config 기본값 + DB 오버라이드 병합."""
    keys = {
        "require_email_verification": ("bool", _cfg.require_email_verification),
        "question_quota_enabled": ("bool", _cfg.question_quota_enabled),
        "quota_anonymous_daily": ("int", _cfg.quota_anonymous_daily),
        "quota_free_daily": ("int", _cfg.quota_free_daily),
        "quota_standard_daily": ("int", _cfg.quota_standard_daily),
        "quota_premium_daily": ("int", _cfg.quota_premium_daily),
        "quota_lifetime_daily": ("int", _cfg.quota_lifetime_daily),
    }

    # 주간 메시지 기본값 등록 (get_str에서 _DEFAULTS fallback 용)
    for _gs_key, _gs_default in [
        ("greeting_sub_ko", "마약중독자만 중독이 아니다, 모든 사람이 중독문제가 있다."),
        ("greeting_sub_zh", "不只是吸毒者才会上瘾，每个人都有上瘾的问题。"),
        ("greeting_sub_en", "It's not just drug addicts who have an addiction problem; everyone does."),
    ]:
        register_setting(_gs_key, _gs_default)
        keys[_gs_key] = ("str", _gs_default)
    out = []
    for k, (vtype, default) in keys.items():
        if vtype == "bool":
            val = get_bool(k, default)
        elif vtype == "int":
            val = get_int(k, default)
        else:
            val = get_str(k, default)
        out.append({"key": k, "value": val, "type": vtype, "default": default})
    return out


# ── 모듈 로드 시점에 주간 메시지 기본값 등록 ──
for _k, _v in [
    ("greeting_sub_ko", "마약중독자만 중독이 아니다, 모든 사람이 중독문제가 있다."),
    ("greeting_sub_zh", "不只是吸毒者才会上瘾，每个人都有上瘾的问题。"),
    ("greeting_sub_en", "It's not just drug addicts who have an addiction problem; everyone does."),
]:
    register_setting(_k, _v)
