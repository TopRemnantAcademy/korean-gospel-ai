"""EPIC G-3: 영적 교정 정책 모듈.
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: EPIC G-3 — build_correction_block() 5종 × 3언어 교정 지시 블록
# Reason: ORDERS_COUNSELING.md G-3 — spiritual_error ≠ none 시 표준 교정 프로토콜 코드 강제
# Related: models/schemas.py (SpiritualError enum), api/chat.py (MODIFY)
# Status: COMPLETED
# =============================================================================
"""
from __future__ import annotations
from typing import Optional

from ..models.schemas import SpiritualError

# ---------------------------------------------------------------------------
# 교정 지시 블록 — 시스템 프롬프트에 prepend되어 LLM 응답을 가이드한다.
# 구조: 요약 → 차분한 정정 → 성경적 기준 → 자기 점검 질문 → 다음 행동
# ---------------------------------------------------------------------------

_CORRECTION_BLOCKS_KO: dict[SpiritualError, str] = {
    SpiritualError.ghost_doctrine: (
        "[영적 교정 지시 — 반드시 응답 첫 단락에 포함하라]\n"
        "사용자가 죽은 사람이 귀신이 된다는 잘못된 믿음을 드러냈습니다. "
        "다음 5단계 구조로 교정 단락을 작성하되, 정죄하지 말고 차분하게:\n"
        "1. 사용자의 두려움을 인정하는 한 문장\n"
        "2. 성경적 정정: '성경은 죽은 사람이 귀신이 된다고 가르치지 않습니다(히 9:27, 눅 16:19-31).'\n"
        "3. 그리스도 안의 신분으로 마음을 돌리는 한 문장\n"
        "4. 자기 점검 질문 1개 (지금 가장 두려운 것)\n"
        "5. 오늘 할 수 있는 한 가지 행동 제안\n"
        "교정 단락 끝에 빈 줄을 넣어 다음 본문과 시각적으로 분리할 것."
    ),
    SpiritualError.superstition: (
        "[영적 교정 지시 — 반드시 응답 첫 단락에 포함하라]\n"
        "사용자가 기독교와 미신(부적·사주·풍수 등)을 혼합하는 시각을 드러냈습니다. "
        "다음 구조로 교정 단락을 작성하되, 정죄하지 말고 차분하게:\n"
        "1. 사용자의 염려를 인정하는 한 문장\n"
        "2. 성경적 정정: 하나님만이 참된 보호와 인도의 근원임을 밝히는 구절 인용\n"
        "3. 두 가지를 동시에 의지하는 것의 영적 위험을 부드럽게 지적\n"
        "4. 자기 점검 질문 1개 (지금 실제로 의지하는 것이 무엇인지)\n"
        "5. 오늘 할 수 있는 한 가지 실천 제안\n"
        "교정 단락 끝에 빈 줄 삽입."
    ),
    SpiritualError.exaggerated_demonology: (
        "[영적 교정 지시 — 반드시 응답 첫 단락에 포함하라]\n"
        "사용자가 모든 문제를 귀신 탓으로 돌리거나 축사에 과도하게 집착하는 시각을 드러냈습니다. "
        "다음 구조로 교정 단락을 작성하되, 정죄하지 말고 차분하게:\n"
        "1. 사용자의 고통을 인정하는 한 문장\n"
        "2. 성경적 균형: 영적 싸움이 실재하지만 그리스도의 승리가 이미 완성됐음 (골 2:15, 요일 4:4)\n"
        "3. 축사 집착이 오히려 두려움을 강화할 수 있다는 부드러운 지적\n"
        "4. 자기 점검 질문 1개 (그리스도 안의 신분에 마음이 머무는지)\n"
        "5. 오늘 할 수 있는 한 가지 실천 제안\n"
        "교정 단락 끝에 빈 줄 삽입."
    ),
    SpiritualError.legalism: (
        "[영적 교정 지시 — 반드시 응답 첫 단락에 포함하라]\n"
        "사용자가 행위·노력으로 구원이나 하나님의 은혜를 얻으려는 율법주의적 사고를 드러냈습니다. "
        "다음 구조로 교정 단락을 작성하되, 정죄하지 말고 차분하게:\n"
        "1. 사용자의 진지함을 인정하는 한 문장\n"
        "2. 성경적 정정: 구원은 행위가 아닌 은혜와 믿음으로 (엡 2:8-9, 롬 3:28)\n"
        "3. 행위로 의를 얻으려는 시도가 오히려 복음의 기쁨을 빼앗는다는 부드러운 지적\n"
        "4. 자기 점검 질문 1개 (지금 하나님 앞에 서는 근거가 무엇인지)\n"
        "5. 오늘 할 수 있는 한 가지 실천 제안\n"
        "교정 단락 끝에 빈 줄 삽입."
    ),
}

_CORRECTION_BLOCKS_EN: dict[SpiritualError, str] = {
    SpiritualError.ghost_doctrine: (
        "[SPIRITUAL CORRECTION DIRECTIVE — Include this as the first paragraph of your response]\n"
        "The user has expressed a belief that deceased people become ghosts. "
        "Write a correction paragraph using this 5-step structure. Do NOT condemn — be calm and pastoral:\n"
        "1. Acknowledge the user's fear in one sentence.\n"
        "2. Biblical correction: 'The Bible does not teach that the dead become ghosts (Heb 9:27, Luke 16:19-31).'\n"
        "3. Redirect to the user's identity in Christ.\n"
        "4. One self-examination question (what they fear most right now).\n"
        "5. One practical action for today.\n"
        "Add a blank line after the correction paragraph to visually separate it from the main answer."
    ),
    SpiritualError.superstition: (
        "[SPIRITUAL CORRECTION DIRECTIVE — Include this as the first paragraph of your response]\n"
        "The user has shown a tendency to mix Christianity with superstition (charms, fortune-telling, etc.). "
        "Write a correction paragraph using this structure. Do NOT condemn — be calm and pastoral:\n"
        "1. Acknowledge the user's concern in one sentence.\n"
        "2. Biblical correction: God alone is the source of true protection and guidance (cite a verse).\n"
        "3. Gently note the spiritual danger of trusting two sources simultaneously.\n"
        "4. One self-examination question (what they are actually relying on).\n"
        "5. One practical step for today.\n"
        "Add a blank line after the correction paragraph."
    ),
    SpiritualError.exaggerated_demonology: (
        "[SPIRITUAL CORRECTION DIRECTIVE — Include this as the first paragraph of your response]\n"
        "The user is attributing all problems to demonic influence or is excessively focused on exorcism. "
        "Write a correction paragraph using this structure. Do NOT condemn — be calm and pastoral:\n"
        "1. Acknowledge the user's suffering in one sentence.\n"
        "2. Biblical balance: Spiritual warfare is real, but Christ's victory is already complete (Col 2:15, 1 John 4:4).\n"
        "3. Gently note that fixating on demons can intensify fear.\n"
        "4. One self-examination question (whether their mind rests on Christ's victory).\n"
        "5. One practical step for today.\n"
        "Add a blank line after the correction paragraph."
    ),
    SpiritualError.legalism: (
        "[SPIRITUAL CORRECTION DIRECTIVE — Include this as the first paragraph of your response]\n"
        "The user is expressing a works-based view of salvation or earning God's grace through effort. "
        "Write a correction paragraph using this structure. Do NOT condemn — be calm and pastoral:\n"
        "1. Acknowledge the user's sincerity in one sentence.\n"
        "2. Biblical correction: Salvation is by grace through faith, not works (Eph 2:8-9, Rom 3:28).\n"
        "3. Gently note that striving for righteousness through works robs the joy of the gospel.\n"
        "4. One self-examination question (what grounds them before God).\n"
        "5. One practical step for today.\n"
        "Add a blank line after the correction paragraph."
    ),
}

_CORRECTION_BLOCKS_ZH: dict[SpiritualError, str] = {
    SpiritualError.ghost_doctrine: (
        "[灵性纠正指示 — 必须作为回答的第一段]\n"
        "用户表达了认为死者会变成鬼魂的错误信念。"
        "请按以下5步结构撰写纠正段落，不要定罪，保持平静而牧者般的语气：\n"
        "1. 用一句话认可用户的恐惧。\n"
        "2. 圣经纠正：'圣经并未教导死人会变成鬼魂（来9:27，路16:19-31）。'\n"
        "3. 将用户的心引向其在基督里的身份。\n"
        "4. 一个自我省察问题（现在最恐惧的是什么）。\n"
        "5. 今天可以做的一件事。\n"
        "纠正段落后插入空行，使其与主要内容视觉上分隔。"
    ),
    SpiritualError.superstition: (
        "[灵性纠正指示 — 必须作为回答的第一段]\n"
        "用户表现出将基督教与迷信（符咒、算命等）混合的倾向。"
        "请按以下结构撰写纠正段落，不要定罪，保持平静而牧者般的语气：\n"
        "1. 用一句话认可用户的担忧。\n"
        "2. 圣经纠正：上帝是真正保护与引导的唯一源头（引用经文）。\n"
        "3. 温和地指出同时依靠两种来源的属灵危险。\n"
        "4. 一个自我省察问题（真正依靠的是什么）。\n"
        "5. 今天可以采取的一个实际步骤。\n"
        "纠正段落后插入空行。"
    ),
    SpiritualError.exaggerated_demonology: (
        "[灵性纠正指示 — 必须作为回答的第一段]\n"
        "用户将所有问题归咎于鬼魂，或对赶鬼过度执着。"
        "请按以下结构撰写纠正段落，不要定罪，保持平静而牧者般的语气：\n"
        "1. 用一句话认可用户的痛苦。\n"
        "2. 圣经的平衡：属灵争战是真实的，但基督的胜利已经完成（西2:15，约一4:4）。\n"
        "3. 温和地指出过度关注鬼魂反而会加剧恐惧。\n"
        "4. 一个自我省察问题（是否将心放在基督的胜利上）。\n"
        "5. 今天可以采取的一个实际步骤。\n"
        "纠正段落后插入空行。"
    ),
    SpiritualError.legalism: (
        "[灵性纠正指示 — 必须作为回答的第一段]\n"
        "用户表达了认为可以通过行为努力获得救恩或神恩典的律法主义思想。"
        "请按以下结构撰写纠正段落，不要定罪，保持平静而牧者般的语气：\n"
        "1. 用一句话认可用户的认真态度。\n"
        "2. 圣经纠正：救恩是因着恩典借着信心，不是靠行为（弗2:8-9，罗3:28）。\n"
        "3. 温和地指出靠行为求义反而夺去福音的喜乐。\n"
        "4. 一个自我省察问题（在上帝面前站立的根基是什么）。\n"
        "5. 今天可以采取的一个实际步骤。\n"
        "纠正段落后插入空行。"
    ),
}

_CORRECTION_BLOCKS_JA: dict[SpiritualError, str] = {
    SpiritualError.ghost_doctrine: (
        "[霊的修正指示 — 回答の最初の段落として必須]\n"
        "ユーザーは「亡くなった人は幽霊になる」という誤った信念を表明しています。\n"
        "以下の5段階構造で修正の段落を作成してください。責め立てず、落ち着いた牧者的な口調を保ってください：\n"
        "1. ユーザーの恐怖を一言で認める。\n"
        "2. 聖書的修正：「聖書は、死人が幽霊になるとは教えていません（ヘブル9:27、ルカ16:19-31）。」\n"
        "3. ユーザーの心をキリストにある身分に向ける。\n"
        "4. 一つの自己点検の質問（今、何が一番怖いですか）。\n"
        "5. 今日できる一つの実践的なステップ。\n"
        "修正の段落の後に空行を入れ、本文と視覚的に分ける。"
    ),
    SpiritualError.superstition: (
        "[霊的修正指示 — 回答の最初の段落として必須]\n"
        "ユーザーはキリスト教と迷信（お守り、占いなど）を混ぜ合わせる傾向が見られます。\n"
        "以下の構造で修正の段落を作成してください。責め立てず、落ち着いた牧者的な口調を保ってください：\n"
        "1. ユーザーの不安を一言で認める。\n"
        "2. 聖書的修正：神こそが真の守りと導きの唯一の源である（聖句を引用）。\n"
        "3. 二つの源に同時に頼ることの霊的な危険性を優しく指摘する。\n"
        "4. 一つの自己点検の質問（本当に頼っているものは何ですか）。\n"
        "5. 今日できる一つの実践的なステップ。\n"
        "修正の段落の後に空行を入れる。"
    ),
    SpiritualError.exaggerated_demonology: (
        "[霊的修正指示 — 回答の最初の段落として必須]\n"
        "ユーザーはすべての問題を悪霊のせいにするか、悪霊退治に過度に執着しています。\n"
        "以下の構造で修正の段落を作成してください。責め立てず、落ち着いた牧者的な口調を保ってください：\n"
        "1. ユーザーの苦しみを一言で認める。\n"
        "2. 聖書的バランス：霊的戦いは真実だが、キリストの勝利はすでに完成している（コロサイ2:15、Ⅰヨハネ4:4）。\n"
        "3. 悪霊に過度に注意を向けると、かえって恐怖が増すことを優しく指摘する。\n"
        "4. 一つの自己点検の質問（心がキリストの勝利に置かれているか）。\n"
        "5. 今日できる一つの実践的なステップ。\n"
        "修正の段落の後に空行を入れる。"
    ),
    SpiritualError.legalism: (
        "[霊的修正指示 — 回答の最初の段落として必須]\n"
        "ユーザーは、行いの努力によって救いや神の恵みを得られるという律法主義的な考えを表明しています。\n"
        "以下の構造で修正の段落を作成してください。責め立てず、落ち着いた牧者的な口調を保ってください：\n"
        "1. ユーザーの真剣な姿勢を一言で認める。\n"
        "2. 聖書的修正：救いは恵みによる信仰によるのであって、行いによるのではない（エペソ2:8-9、ローマ3:28）。\n"
        "3. 行いによって義とされようとすると、かえって福音の喜びが失われることを優しく指摘する。\n"
        "4. 一つの自己点検の質問（神の前に立つ根拠は何ですか）。\n"
        "5. 今日できる一つの実践的なステップ。\n"
        "修正の段落の後に空行を入れる。"
    ),
}

_LANG_MAP = {
    "ko": _CORRECTION_BLOCKS_KO,
    "en": _CORRECTION_BLOCKS_EN,
    "zh": _CORRECTION_BLOCKS_ZH,
    "ja": _CORRECTION_BLOCKS_JA,
}


def build_correction_block(error: SpiritualError, target_lang: str = "ko") -> Optional[str]:
    """spiritual_error 에 맞는 교정 지시 블록을 반환한다.

    none 이면 None 반환 (호출부에서 분기 불필요).
    알 수 없는 target_lang 은 한국어로 폴백.
    """
    if error == SpiritualError.none:
        return None
    blocks = _LANG_MAP.get(target_lang, _CORRECTION_BLOCKS_KO)
    return blocks.get(error)
