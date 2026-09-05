"""편집 검증 서비스 — 글자 수, XSS, No-op, 필드별 제약 검증.

설계 문서 §12.2 기반 구현.
"""

from __future__ import annotations

import json
import re
from typing import Optional

# ── 필드별 글자 수 제한 ──
# (최소 차단, 권장 최소, 권장 최대, 최대 차단)
TEXT_FIELD_LIMITS: dict[str, tuple[int, int, int, int]] = {
    "question": (10, 20, 150, 500),
    "answer": (20, 100, 2000, 5000),
    "root_cause": (20, 80, 250, 500),
    "ai_diagnosis": (20, 100, 300, 600),
    "best_answer": (20, 100, 2000, 5000),
    "best_answer_why": (20, 60, 200, 400),
    "reflection": (10, 25, 100, 200),
    # ── 작업 W: 단편 설교 + 추천 추가질문 ──
    "short_sermon_title": (2, 5, 60, 120),
    "short_sermon_text": (20, 80, 600, 1500),
}

# 제어문자 제거 패턴
_CONTROL_CHARS = re.compile(r"[\u0000-\u001f\u007f-\u009f]")


def sanitize_text(value: str) -> str:
    """텍스트 sanitize: strip + 제어문자 제거 + XSS 방지."""
    v = value.strip()
    # 유니코드 제어문자 제거
    v = _CONTROL_CHARS.sub("", v)
    # XSS 방지
    v = v.replace("<script", "").replace("javascript:", "")
    return v


def validate_text_field(
    field: str,
    value: str,
    *,
    old_value: Optional[str] = None,
) -> dict:
    """TEXT 필드 값 검증.

    Returns:
        {
            "valid": bool,
            "error": Optional[str],
            "warnings": list[dict],
            "sanitized_value": str,
            "no_change": bool,
        }
    """
    result: dict = {
        "valid": True,
        "error": None,
        "warnings": [],
        "sanitized_value": value,
        "no_change": False,
    }

    # Sanitize
    sanitized = sanitize_text(value)
    result["sanitized_value"] = sanitized

    # No-op 감지
    if old_value is not None and sanitized == old_value.strip():
        result["no_change"] = True
        return result

    # 공백만 있는 문자열
    if not sanitized:
        result["valid"] = False
        result["error"] = f"{_field_label(field)}은(는) 비워둘 수 없습니다"
        return result

    limits = TEXT_FIELD_LIMITS.get(field)
    if limits is None:
        return result  # TEXT 필드가 아니면 통과

    min_block, min_recommend, max_recommend, max_block = limits
    length = len(sanitized)

    # 최소 길이 미달 → 차단
    if length < min_block:
        result["valid"] = False
        result["error"] = (
            f"{_field_label(field)}은(는) 최소 {min_block}자 이상이어야 합니다 (현재: {length}자)"
        )
        return result

    # 최대 길이 초과 → 차단
    if length > max_block:
        result["valid"] = False
        result["error"] = (
            f"{_field_label(field)}은(는) 최대 {max_block}자를 초과할 수 없습니다 (현재: {length}자)"
        )
        return result

    # 권장 범위 경고
    if length < min_recommend:
        result["warnings"].append({
            "type": "too_short",
            "message": f"텍스트가 {min_recommend}자 미만입니다. 더 자세한 설명을 권장합니다.",
            "current_length": length,
            "recommended_min": min_recommend,
        })
    elif length > max_recommend:
        result["warnings"].append({
            "type": "too_long",
            "message": f"텍스트가 {max_recommend}자를 초과했습니다. 간결하게 줄이는 것을 권장합니다.",
            "current_length": length,
            "recommended_max": max_recommend,
        })

    return result


def validate_bool_field(field: str, value) -> dict:
    """BOOL 필드 값 검증.

    Returns:
        {"valid": bool, "error": Optional[str], "sanitized_value": bool}
    """
    result: dict = {"valid": True, "error": None, "sanitized_value": None}

    if isinstance(value, bool):
        result["sanitized_value"] = value
        return result

    # 문자열 → bool 변환
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in ("true", "1", "yes"):
            result["sanitized_value"] = True
            return result
        if lower in ("false", "0", "no", ""):
            result["sanitized_value"] = False
            return result

    result["valid"] = False
    result["error"] = f"{_field_label(field)}은(는) true/false 값만 허용됩니다"
    return result


def validate_field(
    field: str,
    new_value,
    *,
    old_value: Optional[str] = None,
    current_is_featured: bool = False,
    current_is_hidden: bool = False,
) -> dict:
    """통합 필드 검증 — TEXT/BOOL 모두 처리.

    Returns:
        {
            "valid": bool,
            "error": Optional[str],
            "warnings": list[dict],
            "sanitized_value": any,
            "no_change": bool,
        }
    """
    # BOOL 필드
    if field in ("is_featured", "is_hidden"):
        bool_result = validate_bool_field(field, new_value)
        if not bool_result["valid"]:
            return {
                "valid": False,
                "error": bool_result["error"],
                "warnings": [],
                "sanitized_value": None,
                "no_change": False,
            }

        sv = bool_result["sanitized_value"]

        # is_featured + is_hidden 동시 True 방지
        if field == "is_featured" and sv and current_is_hidden:
            return {
                "valid": False,
                "error": "is_featured와 is_hidden은 동시에 True일 수 없습니다",
                "warnings": [],
                "sanitized_value": None,
                "no_change": False,
            }
        if field == "is_hidden" and sv and current_is_featured:
            return {
                "valid": False,
                "error": "is_featured와 is_hidden은 동시에 True일 수 없습니다",
                "warnings": [],
                "sanitized_value": None,
                "no_change": False,
            }

        # No-op for bool
        current_value = current_is_featured if field == "is_featured" else current_is_hidden
        no_change = (sv == current_value)

        return {
            "valid": True,
            "error": None,
            "warnings": [],
            "sanitized_value": sv,
            "no_change": no_change,
        }

    # ── 작업 W: 신규 필드 특수 처리 ──
    # 추천 추가질문: JSON 배열 (문자열 리스트)
    if field == "suggested_followups":
        return _validate_followups(new_value, old_value=old_value)
    # 단편 설교 원문 문서 ID: 빈 값 클리어 허용 (일반 텍스트 검증 미적용)
    if field == "short_sermon_doc_id":
        s = sanitize_text(str(new_value))
        if s == "":
            no_change = (str(old_value or "") == "")
            return {"valid": True, "error": None, "warnings": [], "sanitized_value": "", "no_change": no_change}
        if len(s) > 50:
            return {
                "valid": False,
                "error": f"{_field_label(field)}은(는) 최대 50자까지 가능합니다 (현재: {len(s)}자)",
                "warnings": [],
                "sanitized_value": None,
                "no_change": False,
            }
        return {"valid": True, "error": None, "warnings": [], "sanitized_value": s, "no_change": (str(old_value or "") == s)}

    # TEXT 필드
    return validate_text_field(field, str(new_value), old_value=old_value)


def _validate_followups(new_value, old_value=None) -> dict:
    """추천 추가질문(JSON 배열) 검증 — 항목 최대 6개, 각 ≤120자, 빈 항목 제외.

    new_value: JSON 문자열 또는 list. 반환 sanitized_value 는 list.
    """
    try:
        if isinstance(new_value, str):
            parsed = json.loads(new_value)
        else:
            parsed = new_value
    except Exception:
        return {"valid": False, "error": "추천 추가질문은 JSON 배열 형식이어야 합니다", "warnings": [], "sanitized_value": None, "no_change": False}

    if not isinstance(parsed, list):
        return {"valid": False, "error": "추천 추가질문은 배열이어야 합니다", "warnings": [], "sanitized_value": None, "no_change": False}

    items: list[str] = []
    for it in parsed:
        if not isinstance(it, str):
            return {"valid": False, "error": "추천 추가질문은 문자열 배열만 허용됩니다", "warnings": [], "sanitized_value": None, "no_change": False}
        s = sanitize_text(it)
        if not s:
            continue  # 빈 항목은 무시
        if len(s) > 120:
            return {"valid": False, "error": "각 추천 추가질문은 120자를 초과할 수 없습니다", "warnings": [], "sanitized_value": None, "no_change": False}
        items.append(s)

    if len(items) > 6:
        return {"valid": False, "error": "추천 추가질문은 최대 6개까지 가능합니다", "warnings": [], "sanitized_value": None, "no_change": False}

    # no_change 비교
    cur: list = []
    if old_value is not None:
        try:
            cur = old_value if isinstance(old_value, list) else json.loads(old_value)
        except Exception:
            cur = []
    if not isinstance(cur, list):
        cur = []
    no_change = (cur == items)
    return {"valid": True, "error": None, "warnings": [], "sanitized_value": items, "no_change": no_change}


def validate_edit_reason(reason: Optional[str]) -> dict:
    """edit_reason 검증 (200자 제한)."""
    result: dict = {"valid": True, "error": None}
    if reason is not None and len(reason) > 200:
        result["valid"] = False
        result["error"] = f"수정 사유는 200자를 초과할 수 없습니다 (현재: {len(reason)}자)"
    return result


def _field_label(field: str) -> str:
    """필드명 → 표시 레이블."""
    labels = {
        "question": "질문",
        "answer": "답변",
        "root_cause": "근본 원인 분석",
        "ai_diagnosis": "진단",
        "best_answer": "도움된 답변",
        "best_answer_why": "도움된 이유",
        "reflection": "성찰 질문",
        "is_featured": "상단 고정",
        "is_hidden": "숨김",
        "short_sermon_title": "단편 설교 제목",
        "short_sermon_text": "단편 설교 본문",
        "short_sermon_doc_id": "원문 문서 ID",
        "suggested_followups": "추천 추가질문",
    }
    return labels.get(field, field)
