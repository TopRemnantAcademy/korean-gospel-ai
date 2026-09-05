"""다국어 시스템 전체 점검 스크립트.

설치된 모든 모듈의 일본어 지원 현황과 버그를 자동으로 검사합니다.
사용법: python -m scripts.check_i18n
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


def check_target_lang_literal():
    """schemas.py TargetLang Literal 확인."""
    try:
        from app.models.schemas import TargetLang
        from typing import get_args
        langs = get_args(TargetLang)
        has_ja = "ja" in langs
        return {
            "name": "TargetLang Literal",
            "status": "✅" if has_ja else "❌",
            "detail": f"지원 언어: {langs}",
        }
    except Exception as e:
        return {"name": "TargetLang Literal", "status": "❌", "detail": str(e)}


def check_system_prompts():
    """시스템 프롬프트 다국어 지원 확인."""
    results = []
    try:
        from app.prompts.system import (
            get_system_prompt,
            build_user_prompt,
            build_strict_addendum,
            _USER_PROMPT_TEMPLATES,
            _LANG_TO_SYSTEM_PROMPT,
            _STRICT_ADDENDUM_MAP,
        )

        results.append({
            "name": "시스템 프롬프트 (system prompt)",
            "status": "✅" if "ja" in _LANG_TO_SYSTEM_PROMPT else "❌",
            "detail": f"지원 언어: {list(_LANG_TO_SYSTEM_PROMPT.keys())}",
        })

        results.append({
            "name": "사용자 프롬프트 (user prompt)",
            "status": "✅" if "ja" in _USER_PROMPT_TEMPLATES else "❌",
            "detail": f"지원 언어: {list(_USER_PROMPT_TEMPLATES.keys())}",
        })

        results.append({
            "name": "Strict Addendum (아첨 재생성)",
            "status": "✅" if "ja" in _STRICT_ADDENDUM_MAP else "❌",
            "detail": f"지원 언어: {list(_STRICT_ADDENDUM_MAP.keys())}",
        })

        # 실제 함수 호출 테스트
        try:
            sp = get_system_prompt("ja")
            results.append({
                "name": "get_system_prompt('ja')",
                "status": "✅" if len(sp) > 100 else "⚠️",
                "detail": f"{len(sp)}자",
            })
        except Exception as e:
            results.append({
                "name": "get_system_prompt('ja')",
                "status": "❌",
                "detail": str(e),
            })

        try:
            up = build_user_prompt("테스트", ["컨텍스트"], target_lang="ja")
            results.append({
                "name": "build_user_prompt('ja')",
                "status": "✅",
                "detail": f"{len(up)}자",
            })
        except Exception as e:
            results.append({
                "name": "build_user_prompt('ja')",
                "status": "❌",
                "detail": str(e),
            })

    except Exception as e:
        results.append({
            "name": "시스템 프롬프트 전체",
            "status": "❌",
            "detail": f"import 오류: {e}",
        })

    return results


def check_clarifier():
    """재질문 생성기 다국어 지원 확인."""
    results = []
    try:
        from app.prompts.clarifier import (
            get_clarifier_prompt,
            _LANG_TO_CLARIFIER_PROMPT,
        )

        results.append({
            "name": "Clarifier 프롬프트",
            "status": "✅" if "ja" in _LANG_TO_CLARIFIER_PROMPT else "❌",
            "detail": f"지원 언어: {list(_LANG_TO_CLARIFIER_PROMPT.keys())}",
        })
    except Exception as e:
        results.append({
            "name": "Clarifier 프롬프트",
            "status": "❌",
            "detail": str(e),
        })

    try:
        from app.services.clarifier import _FALLBACK_QUESTION
        results.append({
            "name": "Clarifier Fallback 질문",
            "status": "✅" if "ja" in _FALLBACK_QUESTION else "❌",
            "detail": f"지원 언어: {list(_FALLBACK_QUESTION.keys())}",
        })
    except Exception as e:
        results.append({
            "name": "Clarifier Fallback",
            "status": "❌",
            "detail": str(e),
        })

    return results


def check_spiritual_correction():
    """영적 교정 블록 다국어 지원 확인."""
    try:
        from app.services.spiritual_correction import _LANG_MAP
        return {
            "name": "영적 교정 블록",
            "status": "✅" if "ja" in _LANG_MAP else "❌",
            "detail": f"지원 언어: {list(_LANG_MAP.keys())}",
        }
    except Exception as e:
        return {"name": "영적 교정 블록", "status": "❌", "detail": str(e)}


def check_policy_judge():
    """Policy Judge 다국어 지원 확인."""
    try:
        from app.prompts.policy_judge import get_judge_prompt
        result = get_judge_prompt("ja")
        has_ja_hint = "日本語" in result or "日本" in result or "ja" in result
        return {
            "name": "Policy Judge",
            "status": "✅" if has_ja_hint else "⚠️",
            "detail": "일본어 힌트 포함됨" if has_ja_hint else "일본어 힌트 없음 (한국어 기본만)",
        }
    except Exception as e:
        return {"name": "Policy Judge", "status": "❌", "detail": str(e)}


def check_flattery_patterns():
    """아첨 필터 패턴 다국어 지원 확인."""
    try:
        import yaml
        yaml_path = Path(__file__).parent.parent / "data" / "policy" / "flattery_patterns.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        langs = list(data.keys())
        return {
            "name": "아첨 필터 패턴",
            "status": "✅" if "ja" in langs else "❌",
            "detail": f"지원 언어: {langs}",
        }
    except ImportError:
        return {"name": "아첨 필터 패턴", "status": "⚠️", "detail": "yaml 모듈 없어서 확인 불가"}
    except Exception as e:
        return {"name": "아첨 필터 패턴", "status": "❌", "detail": str(e)}


def check_addiction_care():
    """중독 케어 모듈 다국어 지원 확인."""
    results = []
    try:
        from app.services.addiction_care import (
            assess_addiction_query,
            build_addiction_system_prompt_addon,
            get_safety_guard_message,
            CrisisLevel,
        )

        # 평가 함수 테스트
        assessment = assess_addiction_query("ポルノ依存症で死にたいです")
        results.append({
            "name": "중독 평가 (일본어 쿼리)",
            "status": "✅",
            "detail": f"위기레벨: {assessment.crisis_level.value}, 자살: {assessment.has_suicidal_thought}",
        })

        # 안전 메시지 테스트
        safety = get_safety_guard_message(assessment, target_lang="ja")
        results.append({
            "name": "안전 메시지 (일본어)",
            "status": "✅" if safety and len(safety) > 50 else "❌",
            "detail": f"{len(safety or '')}자",
        })

        # 프롬프트 애드온 테스트
        addon = build_addiction_system_prompt_addon(assessment, target_lang="ja")
        results.append({
            "name": "시스템 프롬프트 애드온 (일본어)",
            "status": "✅" if addon and len(addon) > 100 else "❌",
            "detail": f"{len(addon or '')}자",
        })

    except Exception as e:
        results.append({
            "name": "중독 케어 모듈",
            "status": "❌",
            "detail": str(e),
        })

    return results


def check_greeting_service():
    """인사말 서비스 다국어 지원 확인."""
    try:
        from app.services.greeting_service import rule_based_greeting
        result = rule_based_greeting({}, 5, None)
        return {
            "name": "Greeting 서비스 (규칙 기반)",
            "status": "⚠️",
            "detail": "한국어만 지원 (규칙 기반)",
        }
    except Exception as e:
        return {"name": "Greeting 서비스", "status": "❌", "detail": str(e)}


def check_rag_engine():
    """독립형 RAG 엔진 확인."""
    try:
        from app.services.rag_engine import (
            RAGEngine,
            _SUPPORTED_LANGS,
        )
        return {
            "name": "RAG Engine (독립형)",
            "status": "✅" if "ja" in _SUPPORTED_LANGS else "❌",
            "detail": f"지원 언어: {_SUPPORTED_LANGS}",
        }
    except Exception as e:
        return {"name": "RAG Engine", "status": "❌", "detail": str(e)}


def main():
    print()
    print("=" * 65)
    print(" 🌏 다국어 시스템 전체 점검 보고서")
    print("=" * 65)
    print()

    all_results = []

    print("📋 [1/8] 기본 스키마")
    print("-" * 65)
    r = check_target_lang_literal()
    print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
    all_results.append(r)
    print()

    print("📋 [2/8] 시스템 프롬프트")
    print("-" * 65)
    for r in check_system_prompts():
        print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
        all_results.append(r)
    print()

    print("📋 [3/8] Clarifier (재질문)")
    print("-" * 65)
    for r in check_clarifier():
        print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
        all_results.append(r)
    print()

    print("📋 [4/8] 영적 교정")
    print("-" * 65)
    r = check_spiritual_correction()
    print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
    all_results.append(r)
    print()

    print("📋 [5/8] Policy Judge")
    print("-" * 65)
    r = check_policy_judge()
    print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
    all_results.append(r)
    print()

    print("📋 [6/8] 아첨 필터")
    print("-" * 65)
    r = check_flattery_patterns()
    print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
    all_results.append(r)
    print()

    print("📋 [7/8] 중독 케어")
    print("-" * 65)
    for r in check_addiction_care():
        print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
        all_results.append(r)
    print()

    print("📋 [8/8] RAG Engine")
    print("-" * 65)
    r = check_rag_engine()
    print(f"  {r['status']}  {r['name']:30s}  {r['detail']}")
    all_results.append(r)
    print()

    total = len(all_results)
    passed = sum(1 for r in all_results if r["status"] == "✅")
    warnings = sum(1 for r in all_results if r["status"] == "⚠️")
    failed = sum(1 for r in all_results if r["status"] == "❌")

    print("=" * 65)
    print(f"  총 {total}개 항목: ✅ {passed}개  ⚠️ {warnings}개  ❌ {failed}개")
    print("=" * 65)
    print()

    if failed > 0:
        print("❌ 실패 항목:")
        for r in all_results:
            if r["status"] == "❌":
                print(f"   - {r['name']}: {r['detail']}")
        print()

    if warnings > 0:
        print("⚠️ 주의 항목:")
        for r in all_results:
            if r["status"] == "⚠️":
                print(f"   - {r['name']}: {r['detail']}")
        print()

    return failed == 0


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent / "backend"
    sys.path.insert(0, str(project_root))
    success = main()
    sys.exit(0 if success else 1)
