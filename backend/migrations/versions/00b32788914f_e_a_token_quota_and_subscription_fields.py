"""E-A token quota and subscription fields

Revision ID: 00b32788914f
Revises: c2fbb2654cf3
Create Date: 2026-05-26 18:00:47.294992

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '00b32788914f'
down_revision: Union[str, None] = 'c2fbb2654cf3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ⚠️ 의도적 no-op (drift 수정 — 2026-07-23).
    #
    # 본 마이그레이션이 원래 추가하려던 컬럼/인덱스
    #   - document_version: target_audience, target_stage, emotion_tone, difficulty,
    #     length_minutes, target_salvation_stage, darakbang_tier,
    #     salvation_focus_score, gospel_core_tag
    #   - interaction: ix_interaction_trace_id
    #   - subscriber: faith_stage, emotional_state, ... darakbang_verified (전 23개)
    # 는 이미 직전 리비전 c2fbb2654cf3 (baseline) 에서 동일하게 추가되고 있다.
    # 즉 본 마이그레이션은 순수 중복 ADD 였으며, 운영 DB는 앱 기동 시
    # `Base.metadata.create_all`(backend/app/db.py) 로 동일 스키마를 먼저 생성하므로
    # `alembic upgrade head` 를 돌리면 "중복 컬럼" OperationalError 가 발생했다.
    #
    # 해결: 본 리비전을 empty no-op 으로 강등. 체인 연결(c2fbb → 본 → a3c1f9e2b7d4)
    # 은 보존되며, 신규/기존 DB 모두 컬럼은 c2fbb 또는 create_all 로 보장된다.
    # 운영 반영 시: `alembic stamp head` 로 현재 HEAD 정렬(무 DDL) 권장.
    pass


def downgrade() -> None:
    # 대칭 no-op — 본 리비전은 컬럼을 소유하지 않음(c2fbb 가 소유).
    pass
