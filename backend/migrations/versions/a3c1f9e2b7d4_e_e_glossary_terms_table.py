"""E-E glossary_terms table

Revision ID: a3c1f9e2b7d4
Revises: 00b32788914f
Create Date: 2026-05-26 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c1f9e2b7d4'
down_revision: Union[str, None] = '00b32788914f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'glossary_terms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('term', sa.String(100), nullable=False),
        sa.Column('canonical_form', sa.String(100), nullable=False),
        sa.Column('aliases', sa.JSON(), nullable=True),
        sa.Column('category', sa.String(30), nullable=False, server_default='other'),
        sa.Column('definition', sa.Text(), nullable=True),
        sa.Column('related_terms', sa.JSON(), nullable=True),
        sa.Column('frequency_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_seen_doc_id', sa.String(40), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('operator_verified', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_theology_term', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('term', name='uq_glossary_term'),
    )
    op.create_index('ix_glossary_terms_term', 'glossary_terms', ['term'])


def downgrade() -> None:
    op.drop_index('ix_glossary_terms_term', table_name='glossary_terms')
    op.drop_table('glossary_terms')
