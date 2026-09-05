"""subscriber.subscription_expires_at 추가

Revision ID: j1_subscription_expiry
Revises: i1_low_coverage_interaction
Create Date: 2026-07-29

표준/프리미엄 구독의 만료일을 저장하여 관리자 UI에서
"구독 기간이 얼마 남았는지"를 표시할 수 있게 한다.
free/lifetime 티어는 만료일을 사용하지 않는다(None).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "j1_subscription_expiry"
down_revision = "i1_low_coverage_interaction"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.add_column(
            sa.Column("subscription_expires_at", sa.DateTime(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.drop_column("subscription_expires_at")
