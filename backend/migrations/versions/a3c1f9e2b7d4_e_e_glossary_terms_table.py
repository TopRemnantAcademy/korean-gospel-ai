"""E-E glossary_terms table — DEMOTED TO NO-OP.

자동 추출 용어집(GlossaryTerm) 기능이 번역 용어집(glossary.json)으로 대체되어
본 마이그레이션은 더 이상 테이블을 생성하지 않는다.
마이그레이션 체인 유지를 위해 파일은 유지하되 본문은 no-op.
실제 테이블 제거는 h1_drop_glossary_terms 마이그레이션에서 수행.

Revision ID: a3c1f9e2b7d4
Revises: 00b32788914f
Create Date: 2026-05-26 20:00:00.000000

"""
from typing import Sequence, Union


revision: str = 'a3c1f9e2b7d4'
down_revision: Union[str, None] = '00b32788914f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: 자동 추출 용어집 제거됨 (번역 용어집 glossary.json 으로 대체)
    pass


def downgrade() -> None:
    # No-op
    pass
