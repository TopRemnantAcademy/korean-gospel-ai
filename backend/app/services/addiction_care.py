"""중독자 케어 전용 모듈.

중독으로 고통받는 사용자들을 위한 특화 기능:
- 위기 레벨 감지 (자살 충동 등 응급 상황)
- 중독 유형 분류
- 답변 가이드라인 적용 (공감 우선, 비정죄, 희망 제시)
- 위기 상황 안전장치
- 죄책감/수치심 치유 프레임워크
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CrisisLevel(str, Enum):
    """위기 레벨."""
    safe = "safe"
    moderate = "moderate"
    high = "high"
    critical = "critical"


class AddictionType(str, Enum):
    """중독 유형."""
    none = "none"
    sex = "sex"
    alcohol = "alcohol"
    drug = "drug"
    gambling = "gambling"
    game = "game"
    unknown = "unknown"


@dataclass
class AddictionAssessment:
    """중독 관련 질문 평가 결과."""
    is_addiction_related: bool
    addiction_types: list[AddictionType]
    crisis_level: CrisisLevel
    has_suicidal_thought: bool
    has_extreme_shame: bool
    has_family_damage: bool
    key_themes: list[str]
    recommended_approach: list[str]
    crisis_resources: list[dict] = field(default_factory=list)


# 한국어 어미·띄어쓰기 변형을 regex로 처리
SUICIDE_PATTERNS = [
    r"자살",
    r"죽고\s*싶",
    r"죽을\s*까",
    r"죽어야",
    r"자살하고",
    r"자살할",
    r"극단적",
    r"극단\s*선택",
    r"목\s*매",
    r"뛰어내려",
    r"살\s*이유가\s*없",
    r"살\s*이유가",
    r"살\s*맛이",
    r"차라리\s*죽",
    r"없어지는\s*게",
    r"사라지는\s*게",
    r"안\s*사는\s*게",
]
SELF_HARM_PATTERNS = [
    r"자해",
    r"손목을",
    r"상처를\s*내",
]
HOPELESSNESS_PATTERNS = [
    r"희망이\s*없",
    r"절망",
    r"포기해야",
    r"다\s*끝났",
    r"망했",
    r"돌이킬\s*수\s*없",
    r"되돌릴\s*수\s*없",
]

ADDICTION_PATTERNS = {
    AddictionType.sex: [
        r"포르노", r"음란", r"자위", r"성중독", r"불륜", r"바람",
        r"야동", r"성적", r"음란물", r"섹스", r"성관계",
    ],
    AddictionType.alcohol: [
        r"술", r"알콜", r"알코올", r"음주", r"술병", r"술을 마셔",
        r"술 때문에", r"술 끊", r"술 중독",
    ],
    AddictionType.drug: [
        r"마약", r"필로폰", r"메스암페타민", r"대마", r"약물",
        r"향정", r"수면제", r"진통제", r"주사",
    ],
    AddictionType.gambling: [
        r"도박", r"토토", r"스포츠토토", r"사설토토", r"카지노",
        r"슬롯", r"경마", r"경륜", r"빚", r"부채",
    ],
    AddictionType.game: [
        r"게임중독", r"게임을 밤새", r"게임 때문에",
    ],
}

EMOTIONAL_PATTERNS = {
    "shame": [
        r"부끄러", r"수치심", r"수치스러", r"창피", r"얼굴을\s*들",
        r"더러", r"죄책감", r"미안", r"용서를\s*받을\s*수", r"용서\s*못",
    ],
    "family_damage": [
        r"아내(?:가|를|한테|에게)",
        r"남편(?:이|을|한테|에게)",
        r"자식(?:이|을|한테|에게)",
        r"가족(?:이|을|한테|에게)",
        r"부모님(?:이|을|한테|에게)",
        r"이혼", r"헤어졌", r"떠났", r"가족을\s*버렸",
        r"아이(?:한테|에게)", r"배우자(?:한테|에게)",
    ],
    "isolation": [
        r"혼자", r"외로워", r"아무도", r"말할 사람이",
        r"교회를 못 가", r"사람을 만날",
    ],
}


def _match_patterns(text: str, patterns: list[str]) -> int:
    """패턴 목록 중 매칭된 개수를 반환."""
    return sum(1 for p in patterns if re.search(p, text))


def assess_addiction_query(query: str) -> AddictionAssessment:
    """사용자 질문을 평가해서 중독 관련성, 위기 레벨 등을 파악합니다.

    Args:
        query: 사용자 질문 텍스트

    Returns:
        AddictionAssessment 객체
    """
    q = query
    addiction_types: list[AddictionType] = []
    key_themes: list[str] = []

    for add_type, patterns in ADDICTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, q):
                if add_type not in addiction_types:
                    addiction_types.append(add_type)
                break

    has_suicidal_thought = _match_patterns(q, SUICIDE_PATTERNS) > 0
    crisis_score = 0

    if has_suicidal_thought:
        crisis_level = CrisisLevel.critical
    else:
        if _match_patterns(q, SELF_HARM_PATTERNS) > 0:
            crisis_score += 2

        hopelessness_hits = _match_patterns(q, HOPELESSNESS_PATTERNS)
        if hopelessness_hits > 0:
            crisis_score += min(hopelessness_hits, 2)
            key_themes.append("절망/무희망")

        shame_count = _match_patterns(q, EMOTIONAL_PATTERNS["shame"])
        if shame_count >= 2:
            crisis_score += 1
            if "수치심/죄책감" not in key_themes:
                key_themes.append("수치심/죄책감")
        elif shame_count == 1 and hopelessness_hits > 0:
            if "수치심/죄책감" not in key_themes:
                key_themes.append("수치심/죄책감")

        family_count = _match_patterns(q, EMOTIONAL_PATTERNS["family_damage"])
        if family_count >= 1:
            key_themes.append("가족 피해")
            crisis_score += 1

        if crisis_score >= 4:
            crisis_level = CrisisLevel.high
        elif crisis_score >= 2:
            crisis_level = CrisisLevel.moderate
        else:
            crisis_level = CrisisLevel.safe

    shame_count = _match_patterns(q, EMOTIONAL_PATTERNS["shame"])
    has_extreme_shame = shame_count >= 2

    has_family_damage = _match_patterns(q, EMOTIONAL_PATTERNS["family_damage"]) > 0

    is_addiction_related = (
        len(addiction_types) > 0
        or has_suicidal_thought
        or crisis_level != CrisisLevel.safe
        or has_extreme_shame
        or has_family_damage
    )

    recommended_approach = _build_recommended_approach(
        addiction_types, crisis_level, key_themes
    )

    crisis_resources = []

    return AddictionAssessment(
        is_addiction_related=is_addiction_related,
        addiction_types=addiction_types,
        crisis_level=crisis_level,
        has_suicidal_thought=has_suicidal_thought,
        has_extreme_shame=has_extreme_shame,
        has_family_damage=has_family_damage,
        key_themes=key_themes,
        recommended_approach=recommended_approach,
        crisis_resources=crisis_resources,
    )


def _build_recommended_approach(
    addiction_types: list[AddictionType],
    crisis_level: CrisisLevel,
    key_themes: list[str],
) -> list[str]:
    """권장 답변 접근 방식을 생성합니다."""
    approaches = [
        "먼저 공감으로 시작하라 - 그들의 고통이 얼마나 큰지 인정하라",
        "절대 정죄하지 마라 - '너는 나쁜 사람이다'라는 느낌을 주지 마라",
        "죄와 사람을 분리하라 - 죄는 나쁘지만 그 사람 자체는 소중하다",
    ]

    if crisis_level == CrisisLevel.critical:
        approaches.insert(0, "생명이 가장 중요하다 - 즉각적인 안전 확인을 최우선으로")
        approaches.append("전문적인 도움을 강력히 권하라 - 혼자 이겨내려 하지 말라고")
        approaches.append("희망의 끈을 놓지 않게 하라 - 아직 늦지 않았다는 것을 강조")
    elif crisis_level == CrisisLevel.high:
        approaches.append("전문 상담이나 재활 프로그램 연결을 권유하라")
        approaches.append("혼자 짊어지지 말라고 말해라 - 도움을 구하는 것은 용기 있는 일")

    if "수치심/죄책감" in key_themes:
        approaches.append("수치심은 회복의 가장 큰 적임을 설명하라")
        approaches.append("하나님은 우리가 더러울 때 가장 먼저 찾아오시는 분임을 말하라")
        approaches.append("용서 받을 자격이 없어도 은혜로 받는 것임을 강조하라")

    if "가족 피해" in key_themes:
        approaches.append("가족에게 상처 준 것에 대한 죄책감을 공감하라")
        approaches.append("진정한 회복은 가족 관계 회복으로 이어짐을 말하라")
        approaches.append("먼저 자신이 회복하는 것이 가족을 위한 길임을 알려주라")

    if AddictionType.sex in addiction_types:
        approaches.append("성 중독은 의지력의 문제가 아니라 뇌의 질병임을 설명하라")
        approaches.append("교회 안에도 같은 고통을 하는 사람들이 많다는 것을 말해주라")
        approaches.append("건강한 성 정체성은 하나님 안에서 찾아짐을 가르쳐라")

    if AddictionType.alcohol in addiction_types:
        approaches.append("알콜 의존은 의지 부족이 아님을 명확히 하라")
        approaches.append("의학적 치료와 영적 회복이 함께 필요함을 설명하라")
        approaches.append("AA 등 공동체의 도움을 받을 것을 권하라")

    if AddictionType.drug in addiction_types:
        approaches.append("약물 중독은 뇌 질환임을 이해시켜라")
        approaches.append("혼자 금단 증상을 겪는 것은 위험하므로 전문가 도움을 강조")
        approaches.append("재활은 긴 여정이지만 분명히 가능함을 희망으로 말하라")

    if AddictionType.gambling in addiction_types:
        approaches.append("도박 중독의 뇌과학적 원인을 간단히 설명하라")
        approaches.append("경제적 문제 해결보다 중독 치유가 먼저임을 알려주라")
        approaches.append("가족에게 숨기지 말고 고백하는 것이 첫걸음임을 강조")

    approaches.append("작은 발걸음도 소중함을 격려하라 - 완벽하지 않아도 방향이 중요하다")
    approaches.append("하나님의 은혜는 가장 깊은 곳까지 미친다는 것을 확신시켜라")
    approaches.append("지금 바로 시작하면 된다 - 어제가 아니라 오늘부터")

    return approaches


def get_safety_guard_message(
    assessment: AddictionAssessment,
    target_lang: str = "ko",
) -> Optional[str]:
    """위기 상황시 안전 메시지를 반환합니다.

    Args:
        assessment: 중독 평가 결과
        target_lang: 대상 언어 (ko/en/zh/ja)

    Returns:
        안전 메시지 문자열, 해당 없으면 None
    """
    if assessment.crisis_level == CrisisLevel.critical:
        return _SAFETY_MESSAGES.get(target_lang, _SAFETY_MESSAGES["ko"])["critical"]
    elif assessment.crisis_level == CrisisLevel.high:
        return _SAFETY_MESSAGES.get(target_lang, _SAFETY_MESSAGES["ko"])["high"]
    return None


_SAFETY_MESSAGES = {
    "ko": {
        "critical": (
            "\n\n"
            "📞 **지금 당장 도움이 필요하신가요?**\n"
            "혼자서 이겨내려 하지 마세요. 전문가의 도움을 받는 것이 용기 있는 일입니다.\n\n"
            "당신은 소중한 사람입니다. 희망을 잃지 마세요."
        ),
        "high": (
            "\n\n"
            "💡 **함께 기억해주세요**\n"
            "혼자서 모든 걸 짊어지지 않으셔도 됩니다. 전문 상담이나 믿을 수 있는 목회자와 상담하는 것도 좋은 방법입니다.\n\n"
            "작은 발걸음부터 시작하셔도 됩니다. 당신은 혼자가 아닙니다."
        ),
    },
    "en": {
        "critical": (
            "\n\n"
            "📞 **Need help right now?**\n"
            "Don't try to overcome this alone. Reaching out for help is an act of courage.\n\n"
            "• Suicide & Crisis Lifeline: **988** (24/7, free)\n\n"
            "You are valuable. Don't lose hope."
        ),
        "high": (
            "\n\n"
            "💡 **Please remember**\n"
            "You don't have to carry everything alone. Talking to a counselor or a trusted pastor can help.\n\n"
            "Even small steps count. You are not alone."
        ),
    },
    "zh": {
        "critical": (
            "\n\n"
            "📞 **现在就需要帮助吗？**\n"
            "请不要独自承受。寻求帮助是勇敢的表现。\n\n"
            "• 北京心理危机研究与干预中心: **010-82951332** (24小时)\n\n"
            "你是宝贵的。不要放弃希望。"
        ),
        "high": (
            "\n\n"
            "💡 **请记住**\n"
            "你不需要独自承担一切。寻求专业咨询或与信任的牧者交谈也会有帮助。\n\n"
            "即使是小小的一步也很重要。你不是一个人。"
        ),
    },
    "ja": {
        "critical": (
            "\n\n"
            "📞 **今すぐ助けが必要ですか？**\n"
            "一人で乗り越えようとしないでください。助けを求めるのは勇気のあることです。\n\n"
            "• こころの健康相談統一ダイヤル: **0570-060-614** (24時間)\n\n"
            "あなたは大切な人です。希望を失わないでください。"
        ),
        "high": (
            "\n\n"
            "💡 **覚えておいてください**\n"
            "すべてを一人で抱え込まなくても大丈夫です。専門カウンセラーや信頼できる牧師に相談するのも良い方法です。\n\n"
            "小さな一歩からでも大丈夫です。あなたは一人ではありません。"
        ),
    },
}


# ── 위기 하드 바이패스 응답 (LLM/RAG 없이 결정적 안전 응답) ───────────────
# RiskLevel.urgent 또는 CrisisLevel.critical 감지 시, 생성 파이프라인을
# 건너뛰고 아래의 사전 검증된 공감+핫라인 메시지를 즉시 반환한다.
# LLM 환각/부적절 응답 위험을 원천 차단하기 위함.
_CRISIS_BYPASS_OPENER = {
    "ko": (
        "지금 정말 많이 힘드시죠. 그 고통을 혼자 견디지 않으셔도 됩니다.\n"
        "무엇보다 당신의 생명이 가장 소중합니다. 지금 이 순간, 당신은 결코 혼자가 아닙니다.\n"
        "\"여호와는 마음이 상한 자를 가까이 하시고 충심으로 통회하는 자를 구원하시는도다\" (시편 34:18)\n"
        "부디 아래 전문 상담 창구에 지금 바로 연락해 주세요. 24시간 곁에서 함께할 분들이 기다리고 있습니다."
    ),
    "en": (
        "You are going through so much right now, and you do not have to carry this pain alone.\n"
        "Above all, your life is precious. In this very moment, you are not alone.\n"
        "\"The Lord is close to the brokenhearted and saves those who are crushed in spirit.\" (Psalm 34:18)\n"
        "Please reach out to the professional help lines below right now — people are ready to be with you 24/7."
    ),
    "zh": (
        "此刻你一定非常痛苦，这份痛苦你不必独自承受。\n"
        "最重要的是，你的生命无比宝贵。就在此刻，你绝不孤单。\n"
        "\"耶和华靠近伤心的人，拯救灵性痛悔的人。\"（诗篇 34:18）\n"
        "请现在就联系下面的专业求助热线，有人愿意 24 小时陪伴你。"
    ),
    "ja": (
        "今、本当に辛い時を過ごしているのですね。その苦しみを一人で抱え込まなくても大丈夫です。\n"
        "何よりも、あなたの命が最も大切です。今この瞬間も、あなたは決して一人ではありません。\n"
        "「主は心の砕かれた者に近く、たましいの悔いくずおれた者を救われる。」（詩篇 34:18）\n"
        "どうか今すぐ、下記の専門の相談窓口に連絡してください。24時間、あなたに寄り添う人が待っています。"
    ),
}


def build_crisis_bypass_response(
    assessment: "AddictionAssessment | None" = None,
    target_lang: str = "ko",
) -> str:
    """위기 하드 바이패스용 결정적 안전 응답을 생성합니다.

    RAG/LLM 생성을 건너뛰고 즉시 반환할 사전 검증 메시지입니다.
    공감 오프너 + 소망의 말씀 + 핫라인(critical 안전 메시지)로 구성됩니다.

    Args:
        assessment: 중독/위기 평가 결과 (없어도 동작)
        target_lang: 대상 언어 (ko/en/zh/ja)

    Returns:
        완결된 위기 응답 문자열
    """
    lang = target_lang if target_lang in _CRISIS_BYPASS_OPENER else "ko"
    opener = _CRISIS_BYPASS_OPENER[lang]
    safety = _SAFETY_MESSAGES.get(lang, _SAFETY_MESSAGES["ko"])["critical"]
    return opener + safety


def build_addiction_system_prompt_addon(
    assessment: AddictionAssessment,
    target_lang: str = "ko",
) -> str:
    """중독 관련 질문에 대한 시스템 프롬프트 애드온을 생성합니다.

    Args:
        assessment: 중독 평가 결과
        target_lang: 대상 언어 (ko/en/zh/ja)

    Returns:
        시스템 프롬프트에 추가할 문자열
    """
    if (
        not assessment.is_addiction_related
        and assessment.crisis_level == CrisisLevel.safe
        and not assessment.has_suicidal_thought
    ):
        return ""

    l = target_lang if target_lang in _PROMPT_LABELS else "ko"
    labels = _PROMPT_LABELS[l]

    lines = [
        "",
        "=" * 40,
        f"【{labels['title']}】",
        "",
        labels["user_note"],
        f"{labels['crisis_level']}: {assessment.crisis_level.value}",
        f"{labels['addiction_type']}: {', '.join(t.value for t in assessment.addiction_types) if assessment.addiction_types else labels['uncertain']}",
        "",
        f"★★★ {labels['principles_title']} ★★★",
        f"1. {labels['p_empathy']}",
        f"2. {labels['p_separate']}",
        f"3. {labels['p_hope']}",
        f"4. {labels['p_shame']}",
        "",
        f"【{labels['structure']}】",
        f"1. {labels['s_empathy']}",
        f"2. {labels['s_truth']}",
        f"3. {labels['s_hope']}",
        "",
        f"【{labels['dont_title']}】",
        f"- {labels['d_simple']}",
        f"- {labels['d_condemn']}",
        f"- {labels['d_compare']}",
        f"- {labels['d_medical']}",
    ]

    if assessment.has_suicidal_thought:
        lines.extend([
            "",
            f"【{labels['suicide_title']}】",
            f"- {labels['sui_life']}",
            f"- {labels['sui_help']}",
            f"- {labels['sui_permanent']}",
            f"- {labels['sui_notalone']}",
        ])

    if assessment.has_extreme_shame:
        lines.extend([
            "",
            f"【{labels['shame_title']}】",
            f"- {labels['sh_weapon']}",
            f"- {labels['sh_close']}",
            f"- {labels['sh_light']}",
            f"- {labels['sh_grace']}",
        ])

    lines.extend([
        "",
        f"【{labels['hope_title']}】",
        f"- {labels['h_jesus']}",
        f"- {labels['h_paul']}",
        f"- {labels['h_magdalene']}",
        f"- {labels['h_deeper']}",
        "=" * 40,
        "",
    ])

    return "\n".join(lines)


_PROMPT_LABELS = {
    "ko": {
        "title": "중독 케어 특화 지침",
        "user_note": "이 사용자는 중독으로 깊은 고통을 겪고 있을 가능성이 높습니다.",
        "crisis_level": "위기 레벨",
        "addiction_type": "중독 유형",
        "uncertain": "불확실",
        "principles_title": "가장 중요한 원칙",
        "p_empathy": "먼저 공감하라 - 고통을 인정하고 정죄하지 마라",
        "p_separate": "죄와 사람을 분리하라 - 행동은 잘못되었지만 그 사람은 하나님의 형상",
        "p_hope": "희망을 주어라 - 아무리 깊은 구덩이에서도 하나님은 건져내신다",
        "p_shame": "수치심을 깨뜨려라 - 숨는 게 중독을 키운다",
        "structure": "답변 구조",
        "s_empathy": "공감: 고통을 인정하는 문장으로 시작",
        "s_truth": "진실: 성경적 진리를 부드럽게 전달",
        "s_hope": "소망: 하나님의 은혜와 회복의 가능성 제시",

        "dont_title": "절대 하지 말아야 할 것",
        "d_simple": "'그냥 기도해라' '믿음만 있으면 돼' - 너무 단순한 답변 금지",
        "d_condemn": "'너는 나쁜 놈이다' 식의 정죄 금지",
        "d_compare": "'나 같았으면...' '쉬운 거 아니냐' 등 비교 금지",
        "d_medical": "의학적 도움을 부정하는 발언 금지",
        "suicide_title": "자살 충동 감지 - 최우선 대응",
        "sui_life": "생명이 가장 소중함을 강력히 강조",
        "sui_help": "지금 당장 도움을 청하라고 격려",
        "sui_permanent": "자살은 영구적인 해결책이 아님을 분명히",
        "sui_notalone": "혼자가 아니라는 것을 여러 번 강조",
        "shame_title": "수치심 치유 특화",
        "sh_weapon": "수치심은 사단이 가장 좋아하는 무기임을 지적",
        "sh_close": "하나님은 가장 더러울 때 가장 가까이 오심을 말해줌",
        "sh_light": "비밀은 어둠 속에서만 자란다 - 나오면 치유 시작",
        "sh_grace": "용서는 자격으로 받는 게 아니라 은혜로 받는 것",
        "hope_title": "회복의 희망 메시지",
        "h_jesus": "예수님은 가장 죄가 많은 사람을 찾아가셨다",
        "h_paul": "바울은 교회를 박해했지만 위대한 사도가 되었다",
        "h_magdalene": "막달라 마리아는 귀신 일곱 마리 들었지만 예수님을 가장 먼저 만났다",
        "h_deeper": "중독은 깊지만 하나님의 은혜는 더 깊다",
    },
    "en": {
        "title": "Addiction Care Guidelines",
        "user_note": "This user may be in deep pain from addiction.",
        "crisis_level": "Crisis Level",
        "addiction_type": "Addiction Type",
        "uncertain": "Uncertain",
        "principles_title": "Most Important Principles",
        "p_empathy": "Start with empathy - acknowledge their pain without condemnation",
        "p_separate": "Separate sin from the person - the act is wrong but they are made in God's image",
        "p_hope": "Give hope - God delivers even from the deepest pit",
        "p_shame": "Break shame - secrecy fuels addiction",
        "structure": "Response Structure",
        "s_empathy": "Empathy: Start with acknowledging their pain",
        "s_truth": "Truth: Gently share biblical truth",
        "s_hope": "Hope: Present God's grace and possibility of recovery",

        "dont_title": "Things to Never Say",
        "d_simple": "Don't give oversimplified answers like 'just pray' or 'just have faith'",
        "d_condemn": "Never condemn them as a 'bad person'",
        "d_compare": "Never compare them to yourself or others",
        "d_medical": "Never dismiss the need for medical help",
        "suicide_title": "Suicidal Thoughts Detected - Top Priority",
        "sui_life": "Emphasize that life is most precious",
        "sui_help": "Encourage them to seek help right now",
        "sui_permanent": "Make clear that suicide is not a solution",
        "sui_notalone": "Repeatedly emphasize that they are not alone",
        "shame_title": "Shame Healing Focus",
        "sh_weapon": "Point out that shame is Satan's favorite weapon",
        "sh_close": "God comes closest when we feel most unworthy",
        "sh_light": "Secrets only grow in darkness - healing begins when we come out",
        "sh_grace": "Forgiveness is received by grace, not by qualification",
        "hope_title": "Messages of Hope for Recovery",
        "h_jesus": "Jesus came to seek and save the most lost",
        "h_paul": "Paul persecuted the church but became the greatest apostle",
        "h_magdalene": "Mary Magdalene had seven demons but was first to meet the risen Jesus",
        "h_deeper": "Addiction is deep, but God's grace is deeper",
    },
    "zh": {
        "title": "成瘾关怀指南",
        "user_note": "这位用户可能正因成瘾处于深深的痛苦中。",
        "crisis_level": "危机程度",
        "addiction_type": "成瘾类型",
        "uncertain": "不确定",
        "principles_title": "最重要的原则",
        "p_empathy": "先共情 - 承认他们的痛苦，不定罪",
        "p_separate": "将罪与人分开 - 行为是错的，但他们是按神的形像造的",
        "p_hope": "给予盼望 - 神能从最深的坑中拯救",
        "p_shame": "打破羞耻感 - 隐秘滋养成瘾",
        "structure": "回应结构",
        "s_empathy": "共情: 以承认他们的痛苦开始",
        "s_truth": "真理: 温柔地分享圣经真理",
        "s_hope": "盼望: 展示神的恩典和恢复的可能性",

        "dont_title": "绝对不要说的话",
        "d_simple": "不要说过于简单的话，如'只要祷告'、'只要有信心'",
        "d_condemn": "不要定他们为'坏人'",
        "d_compare": "不要把他们和你自己或别人比较",
        "d_medical": "不要否定对医疗帮助的需要",
        "suicide_title": "检测到自杀意念 - 最高优先处理",
        "sui_life": "强调生命是最宝贵的",
        "sui_help": "鼓励他们立即寻求帮助",
        "sui_permanent": "明确说明自杀不是解决办法",
        "sui_notalone": "反复强调他们并不孤单",
        "shame_title": "羞耻治愈重点",
        "sh_weapon": "指出羞耻是撒旦最喜欢的武器",
        "sh_close": "当我们最觉得不配时，神离我们最近",
        "sh_light": "秘密只在黑暗中生长 - 走出来就是医治的开始",
        "sh_grace": "宽恕是凭恩典领受的，不是靠资格",
        "hope_title": "恢复的盼望信息",
        "h_jesus": "耶稣来是要寻找拯救失丧最深的人",
        "h_paul": "保罗曾逼迫教会，但成了最伟大的使徒",
        "h_magdalene": "抹大拉的马利亚曾有七个鬼，但最先遇见复活的耶稣",
        "h_deeper": "成瘾虽深，神的恩典更深",
    },
    "ja": {
        "title": "依存症ケアガイドライン",
        "user_note": "このユーザーは依存症による深い苦しみの中にいる可能性があります。",
        "crisis_level": "危機レベル",
        "addiction_type": "依存症の種類",
        "uncertain": "不明",
        "principles_title": "最も重要な原則",
        "p_empathy": "まず共感から - 痛みを認め、責めない",
        "p_separate": "罪と人を分ける - 行いは間違っていても、その人は神のかたち",
        "p_hope": "希望を与える - どんなに深い穴からでも神は救い出してくださる",
        "p_shame": "恥を打ち砕く - 隠れていると依存症は育つ",
        "structure": "回答の構造",
        "s_empathy": "共感: 痛みを認める言葉から始める",
        "s_truth": "真理: 聖書的真理を優しく伝える",
        "s_hope": "希望: 神の恵みと回復の可能性を示す",

        "dont_title": "絶対に言ってはいけないこと",
        "d_simple": "'ただ祈ればいい''信仰さえあれば' などの単純すぎる回答は禁止",
        "d_condemn": "'お前は悪い人だ' というような非難は禁止",
        "d_compare": "'私だったら...''簡単でしょ' などの比較は禁止",
        "d_medical": "医学的な助けを否定する発言は禁止",
        "suicide_title": "自殺念疑い検出 - 最優先対応",
        "sui_life": "命が最も大切であることを強く強調",
        "sui_help": "今すぐ助けを求めるよう励ます",
        "sui_permanent": "自殺は解決策ではないことを明確に",
        "sui_notalone": "一人ではないことを何度も強調",
        "shame_title": "恥の癒やしに特化",
        "sh_weapon": "恥はサタンの大好きな武器であることを指摘",
        "sh_close": "神は私たちが最も価値なしと感じる時に最も近くにいてくださる",
        "sh_light": "秘密は暗闇の中でしか育たない - 出てくれば癒やしが始まる",
        "sh_grace": "赦しは資格で得るのではなく、恵みで受けるもの",
        "hope_title": "回復の希望のメッセージ",
        "h_jesus": "イエスは最も失われた人を探しに来てくださった",
        "h_paul": "パウロは教会を迫害したが、最も偉大な使徒となった",
        "h_magdalene": "マグダラのマリアは七つの悪霊がいたが、復活したイエスに最初に会った",
        "h_deeper": "依存症は深いが、神の恵みはそれ以上に深い",
    },
}


RECOVERY_STAGES = [
    {
        "stage": 1,
        "name": "인정의 단계",
        "description": "자신이 중독에 빠져 있다는 것을 인정하는 단계",
        "characteristics": [
            "부정에서 벗어나기 시작함",
            "자신의 상태를 솔직히 보게 됨",
            "타인에게 처음으로 고백할 수 있게 됨",
        ],
        "spiritual_key": "우리가 우리 죄를 자백하면 그는 미쁘시고 의로우사 우리 죄를 사하시며 모든 불의에서 우리를 깨끗하게 하시느니라 (요일 1:9)",
        "action_step": "오늘 하나님 앞에 솔직하게 자신의 상태를 고백해보세요. 숨기지 말고 있는 그대로 내어놓는 것이 첫걸음입니다.",
    },
    {
        "stage": 2,
        "name": "항복의 단계",
        "description": "자신의 힘으로는 이길 수 없다는 것을 인정하고 하나님께 항복하는 단계",
        "characteristics": [
            "의지력만으로는 안 된다는 것을 깨달음",
            "하나님의 은혜가 절실히 필요함을 느낌",
            "통제권을 하나님께 넘기게 됨",
        ],
        "spiritual_key": "내게 능력 주시는 자 안에서 내가 모든 것을 할 수 있느니라 (빌 4:13)",
        "action_step": "'하나님, 제 힘으로는 안 됩니다. 당신의 도우심이 필요합니다' 라고 기도해보세요. 항복하는 것이 패배가 아니라 승리의 시작입니다.",
    },
    {
        "stage": 3,
        "name": "회개의 단계",
        "description": "과거의 잘못을 진심으로 슬퍼하고 방향을 전환하는 단계",
        "characteristics": [
            "죄에 대한 진정한 슬픔을 느낌",
            "단순히 후회하는 것이 아니라 방향을 바꿈",
            "잃어버린 관계를 회복하고자 함",
        ],
        "spiritual_key": "주 여호와께서 내게 주의 말씀을 주셨으니 이는 곧 내 발에 등이요 내 길에 빛이니이다 (시 119:105)",
        "action_step": "과거에 상처 준 사람들에게 진심으로 사과하는 것을 준비해보세요. 먼저 하나님께 용서를 구하고, 다음은 상처 준 사람에게 나아가십시오.",
    },
    {
        "stage": 4,
        "name": "치유의 단계",
        "description": "상처를 치유받고 새 정체성을 회복하는 단계",
        "characteristics": [
            "수치심에서 벗어나기 시작함",
            "하나님 자녀로서의 정체성을 회복함",
            "과거가 전부가 아니라는 것을 깨달음",
        ],
        "spiritual_key": "그런즉 누구든지 그리스도 안에 있으면 새로운 피조물이라 옛 것은 지나가고 보라 새로운 것이 이르렀느니라 (고후 5:17)",
        "action_step": "매일 아침 '나는 하나님의 사랑받는 자녀다' 라고 선언해보세요. 당신의 정체성은 중독자가 아니라 하나님의 아들/딸입니다.",
    },
    {
        "stage": 5,
        "name": "성장의 단계",
        "description": "건강한 습관을 세우고 영적으로 성장하는 단계",
        "characteristics": [
            "규칙적인 기도와 말씀 생활이 자리 잡음",
            "건강한 관계를 맺게 됨",
            "유혹에 대처하는 방법을 배움",
        ],
        "spiritual_key": "오직 위로부터 낳은 의의 열매를 맺어 주며 자라나니 (골 1:10)",
        "action_step": "매일 말씀 1장과 기도 10분을 꾸준히 해보세요. 작은 습관이 큰 변화를 만듭니다.",
    },
    {
        "stage": 6,
        "name": "사역의 단계",
        "description": "자신이 받은 은혜로 다른 사람을 돕는 단계",
        "characteristics": [
            "자신의 경험을 나누게 됨",
            "다른 중독자들에게 희망이 됨",
            "고통이 의미 있게 변화됨",
        ],
        "spiritual_key": "우리가 모든 환난 가운데서도 위로를 받는 것은 하나님의 위로로 말미암아 우리가 또한 어떤 환난 가운데 있는 자들을 하나님께서 우리에게 주시는 위로로 위로하게 하려 함이라 (고후 1:4)",
        "action_step": "당신의 이야기를 들어줄 사람 한 명을 찾아보세요. 당신이 받은 은혜를 나눌 때 가장 큰 치유가 일어납니다.",
    },
]


SHAME_HEALING_FRAMEWORK = {
    "truths": [
        {
            "title": "수치심과 죄책감은 다릅니다",
            "content": "죄책감은 '내가 나쁜 일을 했다'는 것이고, 수치심은 '내가 나쁜 사람이다'는 것입니다. 죄책감은 우리를 회개로 이끌지만, 수치심은 우리를 숨게 만듭니다.",
            "bible_verse": "우리가 우리 죄를 자백하면 그는 미쁘시고 의로우사 우리 죄를 사하시며 모든 불의에서 우리를 깨끗하게 하시느니라 (요일 1:9)",
        },
        {
            "title": "하나님은 가장 더러울 때 가장 가까이 오십니다",
            "content": "예수님은 깨끗한 사람들과 함께 있지 않으셨습니다. 죄인들과 세리들과 함께 식사하시고, 가장 비천한 여자에게도 다가가셨습니다. 당신이 더럽다고 느낄 때, 바로 그때가 예수님이 가장 가까이 계신 때입니다.",
            "bible_verse": "내가 의인을 부르러 온 것이 아니요 죄인을 부르러 왔노라 (막 2:17)",
        },
        {
            "title": "비밀은 어둠 속에서만 자랍니다",
            "content": "수치심은 비밀을 먹고 자랍니다. 숨기면 숨길수록 더 커집니다. 하지만 빛 속으로 나오면 수치심은 약해집니다. 믿을 수 있는 한 사람에게, 혹은 하나님께 솔직히 고백하는 순간 치유가 시작됩니다.",
            "bible_verse": "빛 가운데서 행하는 자마다 빛에 속한즉 그 행위가 하나님 안에서 나타남이니라 (요 3:21)",
        },
        {
            "title": "용서는 자격이 아니라 은혜입니다",
            "content": "우리는 용서 받을 자격이 없습니다. 그래서 은혜인 것입니다. 자격으로 받는 것은 급여이지 은혜가 아닙니다. 예수님은 당신이 얼마나 노력했는지 보고 용서하시는 게 아닙니다. 그냥 사랑하시기 때문에 용서하십니다.",
            "bible_verse": "그 은혜로 말미암아 값 없이 의롭다 하심을 얻어 그리스도 예수 안에서 구원에 이르게 하셨느니라 (롬 3:24)",
        },
        {
            "title": "기억은 남아도 정죄는 없습니다",
            "content": "용서 받은 후에도 과거의 기억이 남을 수 있습니다. 그것은 하나님이 용서하지 않으신 게 아니라, 우리 뇌에 기억으로 남아 있는 것입니다. 중요한 것은 그 기억이 우리를 정죄하지 못한다는 사실입니다.",
            "bible_verse": "그들의 죄와 불법을 내가 다시는 기억지 아니하리라 (히 8:12)",
        },
    ],
    "exercises": [
        "오늘 하루만큼은 '나는 나쁜 사람이다' 라는 생각이 들 때마다 '나는 용서 받은 하나님의 자녀다' 라고 바꿔 말해보세요.",
        "자신을 정죄하는 생각이 들 때마다 요일 1:9절을 소리 내어 읽어보세요.",
        "하나님께 '당신이 저를 보시는 모습으로 저를 보게 해주세요' 라고 기도해보세요.",
    ],
}


ADDICTION_COMFORT_VERSES = {
    "sex": [
        {"verse": "참된 평안을 주시는 하나님", "content": "평강의 하나님이 친히 너희로 온전히 거룩하게 하시고 또 너희 온 영과 혼과 몸이 우리 주 예수 그리스도 강림하실 때에 흠 없게 보전되기를 원하노라 (살전 5:23)"},
        {"verse": "정결케 하시는 능력", "content": "너희 중에 이런 자들이 더러 있었느니라 그러나 너희가 씻김을 받았으며 거룩하게 되었으며 우리 주 예수 그리스도의 이름으로와 우리 하나님의 성령 안에서 의롭다 하심을 얻었느니라 (고전 6:11)"},
        {"verse": "육신의 십자가", "content": "내가 그리스도와 함께 십자가에 못 박혔나니 그런즉 이제는 내가 사는 것이 아니요 오직 그리스도께서 내 안에 사시느니라 (갈 2:20)"},
    ],
    "alcohol": [
        {"verse": "새 포도주", "content": "새 포도주는 새 부대에 넣어야 하리라 (마 9:17)"},
        {"verse": "성령 충만", "content": "술 취하지 말라 이는 방탕한 것이니 오직 성령으로 충만함을 받으라 (엡 5:18)"},
        {"verse": "자유함", "content": "그러므로 아들이 너희를 자유롭게 하면 너희가 참으로 자유하리라 (요 8:36)"},
    ],
    "drug": [
        {"verse": "마음의 변화", "content": "오직 너희는 마음을 새롭게 하여 그리스도의 형상을 본받은 새 사람을 입으라 (엡 4:23-24)"},
        {"verse": "강한 피난처", "content": "하나님은 우리의 피난처시요 힘이시니 환난 중에 만날 큰 도움이시라 (시 46:1)"},
        {"verse": "새것", "content": "보라 내가 새 것을 창조함이여 이제는 생겨나는도다 너희가 알지 못하겠느냐 참으로 내가 광야에 길을 사막에 강들을 내리라 (사 43:19)"},
    ],
    "gambling": [
        {"verse": "탐심의 위험", "content": "돈을 사랑함이 일만 악의 뿌리가 되나니 이것을 탐내는 자들은 미혹을 받아 믿음에서 떠나 많은 근심으로써 자기를 찔렀도다 (딤전 6:10)"},
        {"verse": "만족함", "content": "우리가 만족할 줄 알아야 하느니라 가진 것으로 족하도다 내가 약한 가운데 강하니라 (딤전 6:6, 고후 12:10)"},
        {"verse": "하나님의 공급", "content": "나의 하나님이 그리스도 예수 안에서 영광 가운데서 그 풍성함을 따라 너희 모든 쓸 것을 채우시리라 (빌 4:19)"},
    ],
    "general": [
        {"verse": "자유의 진리", "content": "진리를 알지니 진리가 너희를 자유롭게 하리라 (요 8:32)"},
        {"verse": "이기는 자", "content": "이기는 자를 내 하나님 성전에 기둥으로 세우리니 다시는 거기서 나가지 아니하리라 (계 3:12)"},
        {"verse": "힘의 근원", "content": "내게 능력 주시는 자 안에서 내가 모든 것을 할 수 있느니라 (빌 4:13)"},
        {"verse": "새 출발", "content": "그런즉 누구든지 그리스도 안에 있으면 새로운 피조물이라 옛 것은 지나가고 보라 새로운 것이 이르렀느니라 (고후 5:17)"},
    ],
}


def get_recovery_stage_info(stage_num: int) -> Optional[dict]:
    """회복 단계 정보를 반환합니다."""
    if 1 <= stage_num <= len(RECOVERY_STAGES):
        return RECOVERY_STAGES[stage_num - 1]
    return None


def get_comfort_verses(addiction_type: AddictionType) -> list[dict]:
    """중독 유형에 맞는 위로의 성경 구절들을 반환합니다."""
    type_key = addiction_type.value if addiction_type.value in ADDICTION_COMFORT_VERSES else "general"
    return ADDICTION_COMFORT_VERSES[type_key] + ADDICTION_COMFORT_VERSES["general"]

