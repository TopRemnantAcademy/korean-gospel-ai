"""Fast Judge - 결정론적 검사로 일부 LLM Judge 호출 생략.
아첨 패턴 0개 + 이모지 0개 + 길이 충분시 통과."""
from __future__ import annotations
import re


_FAST_PASS_MIN_LENGTH = 50
_EMOJI_RANGE = re.compile(r'[\U0001F300-\U0001FAFF\u2764\u2600-\u2B55]')


def is_judge_fast_pass(answer: str, flattery_total_matches: int) -> bool:
    """LLM Judge 호출 없이도 안전한 답변인지 확인.

    조건 모두 충족시 fast pass:
    - flattery_total_matches == 0 (아첨 패턴 0개)
    - 답변 길이 50자 이상
    - 이모지 0개

    Returns:
        True면 Judge 호출 생략 가능
    """
    if flattery_total_matches > 0:
        return False
    if len(answer.strip()) < _FAST_PASS_MIN_LENGTH:
        return False
    if _EMOJI_RANGE.search(answer):
        return False
    return True
