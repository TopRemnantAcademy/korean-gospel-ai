"""중독 케어 모듈 단위 테스트.

테스트 항목:
1. 위기 레벨 감지 (자살 충동 등)
2. 중독 유형 분류 (성중독, 알콜, 마약, 도박 등)
3. 죄책감/수치심 감지
4. 가족 피해 감지
5. 시스템 프롬프트 애드온 생성
6. 안전 메시지 생성
7. 회복 단계 데이터 무결성
8. 위로 성경 구절 데이터
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.addiction_care import (
    assess_addiction_query,
    build_addiction_system_prompt_addon,
    get_safety_guard_message,
    CrisisLevel,
    AddictionType,
    RECOVERY_STAGES,
    SHAME_HEALING_FRAMEWORK,
    ADDICTION_COMFORT_VERSES,
    get_recovery_stage_info,
    get_comfort_verses,
)


class TestCrisisDetection(unittest.TestCase):
    """위기 레벨 감지 테스트."""

    def test_suicide_keyword_detected(self):
        """자살 관련 키워드가 감지되어야 함."""
        queries = [
            "자살하고 싶어요",
            "죽고싶어요",
            "극단적인 선택을 할까 봐요",
            "차라리 죽는 게 나을 것 같아요",
            "살 이유가 없어요",
        ]
        for q in queries:
            result = assess_addiction_query(q)
            self.assertTrue(
                result.has_suicidal_thought,
                f"'{q}' 에서 자살 생각이 감지되어야 함"
            )
            self.assertEqual(
                result.crisis_level, CrisisLevel.critical,
                f"'{q}' 의 위기 레벨은 critical 이어야 함"
            )

    def test_no_suicide_in_normal_query(self):
        """일반 질문에서는 자살 생각이 감지되지 않아야 함."""
        result = assess_addiction_query("하나님은 어떤 분이신가요?")
        self.assertFalse(result.has_suicidal_thought)
        self.assertEqual(result.crisis_level, CrisisLevel.safe)

    def test_hopelessness_detected(self):
        """절망감이 감지되어야 함."""
        result = assess_addiction_query("모든 게 다 끝났어요. 희망이 없어요")
        self.assertIn("절망/무희망", result.key_themes)
        self.assertNotEqual(result.crisis_level, CrisisLevel.critical)


class TestAddictionTypeClassification(unittest.TestCase):
    """중독 유형 분류 테스트."""

    def test_sex_addiction_detected(self):
        """성중독 관련 키워드가 감지되어야 함."""
        queries = [
            "포르노를 끊을 수가 없어요",
            "음란한 생각이 계속 들어요",
            "성중독인 것 같아요",
            "야동 보는 걸 멈출 수 없어요",
        ]
        for q in queries:
            result = assess_addiction_query(q)
            self.assertIn(
                AddictionType.sex, result.addiction_types,
                f"'{q}' 에서 성중독이 감지되어야 함"
            )
            self.assertTrue(result.is_addiction_related)

    def test_alcohol_addiction_detected(self):
        """알콜 중독 관련 키워드가 감지되어야 함."""
        queries = [
            "술을 매일 마셔요",
            "알콜 중독인 것 같아요",
            "술 때문에 아내가 떠났어요",
        ]
        for q in queries:
            result = assess_addiction_query(q)
            self.assertIn(
                AddictionType.alcohol, result.addiction_types,
                f"'{q}' 에서 알콜 중독이 감지되어야 함"
            )

    def test_drug_addiction_detected(self):
        """마약 중독 관련 키워드가 감지되어야 함."""
        queries = [
            "필로폰을 5년 했어요",
            "마약을 끊고 싶어요",
            "약물 중독에서 벗어나고 싶어요",
        ]
        for q in queries:
            result = assess_addiction_query(q)
            self.assertIn(
                AddictionType.drug, result.addiction_types,
                f"'{q}' 에서 마약 중독이 감지되어야 함"
            )

    def test_gambling_addiction_detected(self):
        """도박 중독 관련 키워드가 감지되어야 함."""
        queries = [
            "도박으로 빚이 많이 생겼어요",
            "스포츠토토를 끊을 수 없어요",
            "카지노에 계속 가게 돼요",
        ]
        for q in queries:
            result = assess_addiction_query(q)
            self.assertIn(
                AddictionType.gambling, result.addiction_types,
                f"'{q}' 에서 도박 중독이 감지되어야 함"
            )

    def test_multiple_addiction_types(self):
        """여러 중독 유형이 동시에 감지될 수 있음."""
        result = assess_addiction_query("술과 포르노 둘 다 끊을 수가 없어요")
        self.assertIn(AddictionType.alcohol, result.addiction_types)
        self.assertIn(AddictionType.sex, result.addiction_types)

    def test_non_addiction_query(self):
        """중독과 관련 없는 질문은 중독 관련으로 분류되지 않아야 함."""
        result = assess_addiction_query("예수님은 누구신가요?")
        self.assertFalse(result.is_addiction_related)
        self.assertEqual(len(result.addiction_types), 0)


class TestShameAndFamilyDetection(unittest.TestCase):
    """죄책감/수치심 및 가족 피해 감지 테스트."""

    def test_extreme_shame_detected(self):
        """심각한 수치심이 감지되어야 함."""
        result = assess_addiction_query(
            "너무 죄책감이 들어서 하나님 앞에 나아갈 수가 없어요. "
            "제가 정말 더러운 것 같아요"
        )
        self.assertTrue(result.has_extreme_shame)
        self.assertIn("수치심/죄책감", result.key_themes)

    def test_family_damage_detected(self):
        """가족 피해가 감지되어야 함."""
        queries = [
            "술 때문에 아내가 아이 데리고 나갔어요",
            "도박으로 아내한테 너무 미안해요",
            "자식한테도 해 끼쳤어요",
        ]
        for q in queries:
            result = assess_addiction_query(q)
            self.assertTrue(
                result.has_family_damage,
                f"'{q}' 에서 가족 피해가 감지되어야 함"
            )
            self.assertIn("가족 피해", result.key_themes)


class TestSystemPromptAddon(unittest.TestCase):
    """시스템 프롬프트 애드온 테스트."""

    def test_addiction_query_produces_addon(self):
        """중독 관련 질문은 프롬프트 애드온을 생성해야 함."""
        assessment = assess_addiction_query("포르노 중독에서 벗어나고 싶어요")
        addon = build_addiction_system_prompt_addon(assessment)
        self.assertTrue(len(addon) > 0)
        self.assertIn("중독 케어", addon)
        self.assertIn("공감", addon)

    def test_non_addiction_query_empty_addon(self):
        """중독 관련 없는 질문은 빈 애드온을 반환해야 함."""
        assessment = assess_addiction_query("오늘 날씨가 좋네요")
        addon = build_addiction_system_prompt_addon(assessment)
        self.assertEqual(addon, "")

    def test_suicidal_has_crisis_section(self):
        """자살 충동시 위기 섹션이 포함되어야 함."""
        assessment = assess_addiction_query("자살하고 싶어요")
        addon = build_addiction_system_prompt_addon(assessment)
        self.assertIn("자살 충동", addon)
        self.assertIn("최우선", addon)

    def test_shame_has_healing_section(self):
        """수치심 심할 때 치유 섹션이 포함되어야 함."""
        assessment = assess_addiction_query(
            "너무 죄책감이 들고 수치스러워서 하나님 앞에 나갈 수 없어요"
        )
        addon = build_addiction_system_prompt_addon(assessment)
        self.assertIn("수치심 치유", addon)

    def test_crisis_resources_in_addon(self):
        """위기 레벨이 높아도 연락처는 더 이상 포함되지 않음."""
        assessment = assess_addiction_query("정말 죽고 싶어요")
        addon = build_addiction_system_prompt_addon(assessment)
        self.assertNotIn("1393", addon)
        self.assertNotIn("자살예방", addon)


class TestSafetyGuardMessage(unittest.TestCase):
    """안전 메시지 생성 테스트."""

    def test_critical_level_has_safety_message(self):
        """위기 레벨 critical은 안전 메시지가 있어야 함 (핫라인 번호 제외)."""
        assessment = assess_addiction_query("자살하고 싶어요")
        msg = get_safety_guard_message(assessment)
        self.assertIsNotNone(msg)
        self.assertIn("도움이 필요하신가요", msg)
        self.assertNotIn("1393", msg)

    def test_high_level_has_safety_message(self):
        """위기 레벨 high도 안전 메시지가 있어야 함 (핫라인 번호 제외)."""
        assessment = assess_addiction_query(
            "마약 때문에 다 망했어요. 너무 절망적이에요"
        )
        if assessment.crisis_level == CrisisLevel.high:
            msg = get_safety_guard_message(assessment)
            self.assertIsNotNone(msg)
            self.assertNotIn("1577-0199", msg)

    def test_safe_level_no_safety_message(self):
        """위기 레벨 safe는 안전 메시지가 없어야 함."""
        assessment = assess_addiction_query("안녕하세요")
        msg = get_safety_guard_message(assessment)
        self.assertIsNone(msg)


class TestRecoveryStages(unittest.TestCase):
    """회복 단계 데이터 테스트."""

    def test_all_six_stages_exist(self):
        """6단계가 모두 존재해야 함."""
        self.assertEqual(len(RECOVERY_STAGES), 6)

    def test_each_stage_has_required_fields(self):
        """각 단계에 필요한 필드가 모두 있어야 함."""
        required = ["stage", "name", "description", "characteristics",
                     "spiritual_key", "action_step"]
        for stage in RECOVERY_STAGES:
            for field in required:
                self.assertIn(field, stage, f"Stage missing field: {field}")
                self.assertTrue(len(str(stage[field])) > 0)

    def test_stage_numbers_sequential(self):
        """단계 번호가 1부터 순차적이어야 함."""
        for i, stage in enumerate(RECOVERY_STAGES, 1):
            self.assertEqual(stage["stage"], i)

    def test_get_recovery_stage_info(self):
        """단계 정보 조회 함수 테스트."""
        stage1 = get_recovery_stage_info(1)
        self.assertIsNotNone(stage1)
        self.assertEqual(stage1["name"], "인정의 단계")

        self.assertIsNone(get_recovery_stage_info(0))
        self.assertIsNone(get_recovery_stage_info(7))


class TestComfortVerses(unittest.TestCase):
    """위로 성경 구절 테스트."""

    def test_all_types_have_verses(self):
        """모든 중독 유형에 구절이 있어야 함."""
        for atype in ["sex", "alcohol", "drug", "gambling", "general"]:
            self.assertIn(atype, ADDICTION_COMFORT_VERSES)
            self.assertTrue(len(ADDICTION_COMFORT_VERSES[atype]) > 0)

    def test_each_verse_has_required_fields(self):
        """각 구절에 필요한 필드가 있어야 함."""
        for atype, verses in ADDICTION_COMFORT_VERSES.items():
            for v in verses:
                self.assertIn("verse", v)
                self.assertIn("content", v)
                self.assertTrue(len(v["verse"]) > 0)
                self.assertTrue(len(v["content"]) > 0)

    def test_get_comfort_verses(self):
        """구절 조회 함수 테스트."""
        verses = get_comfort_verses(AddictionType.sex)
        self.assertTrue(len(verses) > 3)

        general = get_comfort_verses(AddictionType.none)
        self.assertTrue(len(general) >= 4)


class TestShameHealingFramework(unittest.TestCase):
    """수치심 치유 프레임워크 테스트."""

    def test_has_truths_and_exercises(self):
        """진리와 연습문제가 모두 있어야 함."""
        self.assertIn("truths", SHAME_HEALING_FRAMEWORK)
        self.assertIn("exercises", SHAME_HEALING_FRAMEWORK)

    def test_at_least_five_truths(self):
        """최소 5개의 진리가 있어야 함."""
        self.assertTrue(len(SHAME_HEALING_FRAMEWORK["truths"]) >= 5)

    def test_each_truth_has_fields(self):
        """각 진리에 필요한 필드가 있어야 함."""
        for truth in SHAME_HEALING_FRAMEWORK["truths"]:
            self.assertIn("title", truth)
            self.assertIn("content", truth)
            self.assertIn("bible_verse", truth)

    def test_exercises_exist(self):
        """연습 문제가 있어야 함."""
        self.assertTrue(len(SHAME_HEALING_FRAMEWORK["exercises"]) >= 3)


class TestRecommendedApproach(unittest.TestCase):
    """권장 접근 방식 테스트."""

    def test_addiction_queries_have_approaches(self):
        """중독 관련 질문은 권장 접근 방식이 있어야 함."""
        result = assess_addiction_query("포르노 중독을 끊고 싶어요")
        self.assertTrue(len(result.recommended_approach) > 5)

    def test_empathy_first_in_all(self):
        """모든 중독 질문에 공감이 첫 번째 원칙이어야 함."""
        types_to_test = [
            ("포르노를 끊을 수 없어요", AddictionType.sex),
            ("술 때문에 가족이 떠났어요", AddictionType.alcohol),
            ("마약을 끊고 싶어요", AddictionType.drug),
            ("도박으로 빚이 생겼어요", AddictionType.gambling),
        ]
        for query, expected_type in types_to_test:
            result = assess_addiction_query(query)
            self.assertTrue(
                any("공감" in a for a in result.recommended_approach),
                f"'{query}' 에 공감 관련 접근이 있어야 함"
            )

    def test_suicidal_has_life_first(self):
        """자살 충동시 생명이 최우선이어야 함."""
        result = assess_addiction_query("자살하고 싶어요")
        self.assertTrue(
            any("생명" in a and "가장 중요" in a for a in result.recommended_approach),
            "자살 충동시 '생명이 가장 중요' 접근이 있어야 함"
        )


def run_all_tests():
    """모든 테스트 실행."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestCrisisDetection,
        TestAddictionTypeClassification,
        TestShameAndFamilyDetection,
        TestSystemPromptAddon,
        TestSafetyGuardMessage,
        TestRecoveryStages,
        TestComfortVerses,
        TestShameHealingFramework,
        TestRecommendedApproach,
    ]

    for tc in test_classes:
        tests = loader.loadTestsFromTestCase(tc)
        suite.addTests(tests)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"테스트 결과: {result.testsRun} 실행, "
          f"{len(result.failures)} 실패, {len(result.errors)} 에러")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
