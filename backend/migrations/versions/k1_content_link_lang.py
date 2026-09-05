"""content_link.lang 컬럼 추가 (언어별 콘텐츠 격리)

Revision ID: k1_content_link_lang
Revises: j1_subscription_expiry
Create Date: 2026-08-01

중국어 앱이 /mobile/content?lang=zh 로 호출할 때 한글 콘텐츠를
읽지 않도록, content_link 에 lang(ko|zh|en|ja) 컬럼을 추가.
기존 행은 기본값 'ko' 로 채워짐(중국어 앱은 zh 데이터를 별도 등록해야 함).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "k1_content_link_lang"
down_revision = "j1_subscription_expiry"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("content_link") as batch_op:
        batch_op.add_column(
            sa.Column("lang", sa.String(8), nullable=False, server_default="ko")
        )


def downgrade():
    with op.batch_alter_table("content_link") as batch_op:
        batch_op.drop_column("lang")
