"""P4 #8 — SupportTicket (사용자 신고/오류 제보) 테이블 추가

Revision ID: f1_support_ticket
Revises: 00b32788914f
Create Date: 2026-07-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1_support_ticket'
down_revision: Union[str, None] = '00b32788914f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'support_ticket',
        sa.Column('ticket_id', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sub_id', sa.String(length=40), nullable=True),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('target', sa.String(length=200), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('contact', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('dedup_hash', sa.String(length=64), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('ticket_id'),
    )
    op.create_index('ix_support_ticket_created_at', 'support_ticket', ['created_at'])
    op.create_index('ix_support_ticket_sub_id', 'support_ticket', ['sub_id'])
    op.create_index('ix_support_ticket_type', 'support_ticket', ['type'])
    op.create_index('ix_support_ticket_status', 'support_ticket', ['status'])
    op.create_index('ix_support_ticket_dedup_hash', 'support_ticket', ['dedup_hash'])


def downgrade() -> None:
    op.drop_table('support_ticket')
