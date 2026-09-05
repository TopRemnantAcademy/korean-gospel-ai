"""P4 #6 — retriever 프로필 부스트 누적 버그 회귀 테스트.

과거 버그: 다단계 target_salvation_stage 문서에서 첫 매치에서 break 하여
나머지 단계 부스트가 누락. 이제 모든 매치 단계를 누적(sum)해야 한다.

참고: compute_profile_boost 는 단계별 SALVATION_BOOST_MATRIX 합산 외에
추가 보너스(gospel_core_tag +0.30, seeker/gospel_core 단계 +0.15,
assume_saved discipleship +0.25, darakbang +N)를 함께 누적한다.
"""
from backend.app.services.retriever import compute_profile_boost


def test_multi_stage_boost_is_cumulative():
    # seeker + gospel_core 두 단계 MATRIX 가 모두 누적됨 (0.35 + 0.50)
    # + seeker 단계 보너스 0.15 = 1.00
    meta = {"target_salvation_stage": ["seeker", "gospel_core"]}
    profile = {"salvation_status": "seeker"}
    assert compute_profile_boost(meta, profile) == 1.0


def test_multi_stage_exceeds_single_stage_no_break():
    multi = {"target_salvation_stage": ["seeker", "gospel_core"]}
    single = {"target_salvation_stage": ["seeker"]}
    profile = {"salvation_status": "seeker"}
    # 과거 break 버그였다면 두 값이 같았을 것. 누적이므로 multi > single.
    assert compute_profile_boost(multi, profile) > compute_profile_boost(single, profile)


def test_single_stage_boost():
    meta = {"target_salvation_stage": ["seeker"]}
    profile = {"salvation_status": "seeker"}
    # 0.35 (matrix) + 0.15 (seeker 보너스) = 0.50
    assert compute_profile_boost(meta, profile) == 0.50


def test_gospel_core_tag_bonus_for_unknown():
    meta = {"gospel_core_tag": True, "target_salvation_stage": []}
    profile = {"salvation_status": "unknown"}
    assert compute_profile_boost(meta, profile) == 0.30


def test_assume_saved_discipleship_bonus():
    meta = {"target_salvation_stage": ["discipleship"]}
    profile = {"salvation_status": "assured", "assume_saved": True}
    # 0.25 (matrix) + 0.25 (assume_saved discipleship) = 0.50
    assert compute_profile_boost(meta, profile) == 0.50


def test_darakbang_role_bonus():
    meta = {"target_salvation_stage": [], "darakbang_tier": "darakbang_leader"}
    profile = {
        "salvation_status": "unknown",
        "is_darakbang_member": True,
        "darakbang_role": "leader",
        "darakbang_verified": True,
    }
    # ("leader","darakbang_leader")=0.40
    assert compute_profile_boost(meta, profile) == 0.40


def test_string_stage_normalized_to_list():
    meta = {"target_salvation_stage": "seeker"}
    profile = {"salvation_status": "seeker"}
    assert compute_profile_boost(meta, profile) == 0.50
