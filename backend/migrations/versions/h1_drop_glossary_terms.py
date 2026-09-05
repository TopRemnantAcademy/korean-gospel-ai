"""Drop glossary_terms table (자동 추출 용어집 제거 후속).

번역 용어집(glossary.json)으로 대체되어 자동 추출 용어집 테이블은 불필요.
기존 DB 에 남은 테이블을 제거한다. IF EXISTS 로 안전하게 처리.

Revision ID: h1_drop_glossary_terms
Revises: g1_crisis_bypass_eval
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'h1_drop_glossary_terms'
down_revision: Union[str, None] = 'g1_crisis_bypass_eval'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS glossary_terms")


def downgrade() -> None:
    # 재생성은 의도하지 않음 (번역 용어집으로 대체)
    pass
