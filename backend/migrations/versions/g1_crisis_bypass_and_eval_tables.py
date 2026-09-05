"""Wave A+B — interaction.crisis_bypass 컬럼 + eval_question / eval_run 테이블

이 리비전은 기존 2개 head(b7e2d4f1a9c5, f1_support_ticket)를 병합하면서
동시에 스키마 변경을 적용한다.

- Wave A: interaction 테이블에 crisis_bypass(bool) 추가 — 위기 하드 바이패스 턴 표시
- Wave B: 평가 하네스용 eval_question / eval_run 테이블 신규 생성

Revision ID: g1_crisis_bypass_eval
Revises: b7e2d4f1a9c5, f1_support_ticket
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g1_crisis_bypass_eval'
down_revision: Union[str, Sequence[str], None] = ('b7e2d4f1a9c5', 'f1_support_ticket')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Wave A: interaction.crisis_bypass ──────────────────────────────
    with op.batch_alter_table('interaction') as batch_op:
        batch_op.add_column(
            sa.Column('crisis_bypass', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index('ix_interaction_crisis_bypass', ['crisis_bypass'])

    # ── Wave B: eval_question ──────────────────────────────────────────
    op.create_table(
        'eval_question',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('reference_answer', sa.Text(), nullable=True),
        sa.Column('expected_doc_ids', sa.JSON(), nullable=True),
        sa.Column('expected_risk_level', sa.String(length=20), nullable=True),
        sa.Column('expected_crisis_bypass', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('lang', sa.String(length=8), nullable=False, server_default='ko'),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_eval_question_category', 'eval_question', ['category'])
    op.create_index('ix_eval_question_active', 'eval_question', ['active'])
    op.create_index('ix_eval_question_cat_active', 'eval_question', ['category', 'active'])

    # ── Wave B: eval_run ───────────────────────────────────────────────
    op.create_table(
        'eval_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=40), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('retrieved_ids', sa.JSON(), nullable=True),
        sa.Column('hit_at_k', sa.Float(), nullable=True),
        sa.Column('mrr', sa.Float(), nullable=True),
        sa.Column('ndcg_at_k', sa.Float(), nullable=True),
        sa.Column('judge_score', sa.Float(), nullable=True),
        sa.Column('judge_verdict', sa.Text(), nullable=True),
        sa.Column('detected_risk_level', sa.String(length=20), nullable=True),
        sa.Column('crisis_bypass_triggered', sa.Boolean(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('model', sa.String(length=60), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['eval_question.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_eval_run_run_id', 'eval_run', ['run_id'])
    op.create_index('ix_eval_run_category', 'eval_run', ['category'])
    op.create_index('ix_eval_run_created_at', 'eval_run', ['created_at'])
    op.create_index('ix_eval_run_run_cat', 'eval_run', ['run_id', 'category'])
    op.create_index('ix_eval_run_question', 'eval_run', ['question_id'])


def downgrade() -> None:
    op.drop_index('ix_eval_run_question', table_name='eval_run')
    op.drop_index('ix_eval_run_run_cat', table_name='eval_run')
    op.drop_index('ix_eval_run_created_at', table_name='eval_run')
    op.drop_index('ix_eval_run_category', table_name='eval_run')
    op.drop_index('ix_eval_run_run_id', table_name='eval_run')
    op.drop_table('eval_run')

    op.drop_index('ix_eval_question_cat_active', table_name='eval_question')
    op.drop_index('ix_eval_question_active', table_name='eval_question')
    op.drop_index('ix_eval_question_category', table_name='eval_question')
    op.drop_table('eval_question')

    with op.batch_alter_table('interaction') as batch_op:
        batch_op.drop_index('ix_interaction_crisis_bypass')
        batch_op.drop_column('crisis_bypass')
