"""응답 합성 후 안전망 정책. 치유/중독 맥락 강제 보호.

운영자가 못 끄도록 코드로 박는다 (정책 룰이 아닌 하드코딩).
"""

# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: N3 — SAFETY_TRIGGERS 패턴 확장 (공백·영어·한자 우회 차단)
#       N8 — SafetyVerdict.appended_text 필드 추가 (prefix-slice 위험 제거)
#       N17 — HARD_BLOCK_PATTERNS 확장 (의료 권유·번영신학·율법주의)
#       D-C23 — LEGALISM_PATTERNS + FALSE_ASSURANCE_PATTERNS + post_check_legalism()
# Reason: ORDERS.md N3, N8, N17, EPIC D-C23
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import re
from dataclasses import dataclass


# N3: 공백/영어/한자 우회를 막기 위해 패턴 다중화
SAFETY_TRIGGERS = [
    {
        "code": "SUICIDE_SELFHARM",
        "pattern": re.compile(
            r"(자\s*살|자\s*해|죽\s*고\s*싶|목\s*숨\s*을\s*끊|살\s*고\s*싶\s*지\s*않"
            r"|세\s*상\s*떠\s*나\s*고\s*싶|돌아가고\s*싶|돌아가시고\s*싶|돌아가실\s*것"
            r"|세상\s*떠나시고\s*싶|세상\s*떠나실\s*것"
            r"|끝\s*낼\s*래|이\s*번\s*이\s*마\s*지\s*막"
            r"|스\s*스\s*로\s*를?\s*해\s*치"
            r"|want\s+to\s+(die|end\s+it|kill\s+myself)|self.?harm|suicid"
            r"|自[殺殘杀]|想死)",
            re.IGNORECASE,
        ),
    },
]

# N17: 출력에 절대 들어가면 안 되는 표현 (들어가면 block + 로그)
HARD_BLOCK_PATTERNS = [
    # 구원 단정·심판 선언
    re.compile(r"당신은\s*구원받지\s*못합니다"),
    re.compile(r"지옥에\s*갈\s*것입니다"),
    re.compile(r"구원받을\s*수\s*없"),
    re.compile(r"하나님이\s*버리셨"),
    re.compile(r"you\s+will\s+go\s+to\s+hell", re.IGNORECASE),
    re.compile(r"you\s+cannot\s+be\s+saved", re.IGNORECASE),
    re.compile(r"god\s+has\s+abandoned\s+you", re.IGNORECASE),
    re.compile(r"你会下地狱"),
    re.compile(r"你不能得救"),
    re.compile(r"上帝已经抛弃了你"),
    # 의료 거부 권유
    re.compile(r"이?\s*약을?\s*끊으세요"),
    re.compile(r"약\s*(안\s*먹어도|보다\s*기도가?\s*먼저)"),
    re.compile(r"병원에?\s*(안\s*가도|갈\s*필요\s*(없|없어))"),
    re.compile(r"신앙으로\s*모든?\s*병"),
    re.compile(r"stop\s+taking\s+your\s+medicine", re.IGNORECASE),
    re.compile(r"停止服药"),
    re.compile(r"不用去医院"),
    # 번영신학 허위 약속
    re.compile(r"헌금(하면|을\s*드리면)\s*(복|축복|병이?\s*낫)"),
    re.compile(r"십일조를?\s*드리면\s*복"),
    re.compile(r"씨앗을?\s*심으면\s*(복|축복)"),
    # 관계 파괴·강압
    re.compile(r"이혼하세요"),
    re.compile(r"부모를?\s*(떠나세요|버리세요)"),
    # 율법주의 배타 선언
    re.compile(r"교회\s*(안\s*나가면|나가지\s*않으면)\s*구원"),
]


@dataclass
class SafetyVerdict:
    answer: str  # 최종 답변 (안전망 추가됐을 수 있음)
    triggered: list[str]  # 발동된 룰 코드
    blocked: bool  # 하드블록 발동?
    block_reason: str = ""
    appended_text: str = ""  # N8: 안전망으로 추가된 텍스트만 (prefix-slice 위험 제거)


# D-C23: 율법주의·행위 구원 표현 감지 (출력 soft-block — 재생성 후보)
LEGALISM_PATTERNS: list[re.Pattern] = [
    re.compile(r"네가?\s*더\s*(기도|봉사|헌금|섬김)하면", re.IGNORECASE),
    re.compile(r"믿음이\s*(부족|약)하니", re.IGNORECASE),
    re.compile(r"노력해야\s*(구원|확신|평안)", re.IGNORECASE),
    re.compile(r"십일조.{0,10}안\s*?내면", re.IGNORECASE),
    re.compile(r"교회\s*출석.{0,10}안\s*?하면.{0,10}(구원|문제|잘못)", re.IGNORECASE),
    re.compile(r"(더|더욱)\s*(열심히|충성|헌신)해야\s*구원", re.IGNORECASE),
    re.compile(r"죄를?\s*안?\s*회개하면\s*(구원\s*없|벌|지옥)", re.IGNORECASE),
]

# D-C23: 거짓 확신 (너무 단순화된 보장)
FALSE_ASSURANCE_PATTERNS: list[re.Pattern] = [
    re.compile(r"한\s*번\s*(구원|영접)했으니\s*(끝|완전|영원히\s*안전)", re.IGNORECASE),
    re.compile(r"기도만\s*하면\s*(다|반드시)\s*(해결|이뤄)", re.IGNORECASE),
    re.compile(r"믿으면\s*모든\s*(병|문제|고통)\s*(낫|해결|사라)", re.IGNORECASE),
]


def post_check_legalism(response: str) -> list[str]:
    """D-C23: LLM 응답에서 율법주의·거짓확신 표현 감지. 플래그 리스트 반환.

    chat.py 에서 debug_info 에 포함, 운영자에게만 표시.
    flagged 되면 Layer C regen (regenerate_strict) 후보로 처리 가능.
    """
    flags: list[str] = []
    for pat in LEGALISM_PATTERNS:
        if pat.search(response):
            flags.append(f"legalism:{pat.pattern[:30]}")
    for pat in FALSE_ASSURANCE_PATTERNS:
        if pat.search(response):
            flags.append(f"false_assurance:{pat.pattern[:30]}")
    return flags


def apply(question: str, answer: str) -> SafetyVerdict:
    """답변에 안전망 적용. 합성 단계 마지막에 호출."""
    triggered: list[str] = []

    # 하드 블록 (출력에 금지 표현 있으면 차단)
    for pat in HARD_BLOCK_PATTERNS:
        if pat.search(answer):
            return SafetyVerdict(
                answer=(
                    "죄송합니다. 답변 중 부적절한 표현이 감지되어 보여드릴 수 없습니다.\n"
                    "다른 표현으로 다시 질문해 주시거나, 상담자에게 연결을 요청하실 수 있습니다."
                ),
                triggered=[f"hard_block:{pat.pattern}"],
                blocked=True,
                block_reason=f"hard_block:{pat.pattern}",
                appended_text="",
            )

    # 질문 또는 답변에 트리거 키워드가 있으면 안전 리소스 추가
    combined = f"{question}\n{answer}"
    extras: list[str] = []
    for rule in SAFETY_TRIGGERS:
        if rule["pattern"].search(combined):
            triggered.append(rule["code"])
            extras.append(rule.get("append", ""))

    appended = "".join(extras)
    final = answer + appended
    return SafetyVerdict(
        answer=final, triggered=triggered, blocked=False, appended_text=appended
    )
