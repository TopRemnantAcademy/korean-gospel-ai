"""E-F document_drafts table

Revision ID: b7e2d4f1a9c5
Revises: a3c1f9e2b7d4
Create Date: 2026-05-26 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2d4f1a9c5'
down_revision: Union[str, None] = 'a3c1f9e2b7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'document_drafts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version_id', sa.String(40), nullable=False),
        sa.Column('operator_id', sa.String(60), nullable=False, server_default='admin'),
        sa.Column('draft_body', sa.Text(), nullable=True),
        sa.Column('draft_meta', sa.JSON(), nullable=True),
        sa.Column('saved_at', sa.DateTime(), nullable=False),
        sa.Column('device_id', sa.String(60), nullable=False, server_default='browser'),
        sa.Column('conflict_resolved', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['version_id'], ['document_version.version_id'], name='fk_draft_version'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version_id', 'operator_id', name='uq_draft_ver_op'),
    )
    op.create_index('ix_document_drafts_version_id', 'document_drafts', ['version_id'])


def downgrade() -> None:
    op.drop_index('ix_document_drafts_version_id', table_name='document_drafts')
    op.drop_table('document_drafts')
