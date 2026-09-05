"""CCP P1: ccp_rate_card 테이블 + interaction 원가 귀속 컬럼 5종

Revision ID: l1_ccp_cost_attribution
Revises: k1_content_link_lang
Create Date: 2026-08-02

LLM 호출 1건의 실제 원가(KRW)를 불변 스냅샷으로 확정하기 위한 기반 스키마.

1) ccp_rate_card
   provider/model 별 토큰 단가를 기간(effective_from ~ effective_to)으로
   버전 관리한다. 요율 변경 시 UPDATE 가 아닌 INSERT 로 이력을 남긴다.

2) interaction 확장 (llm_provider, llm_model, prompt_tokens,
   completion_tokens, cost_krw, rate_card_id)
   모두 nullable — 과거 행과 원가 산정 불가 턴(fast-path 등)은 NULL 로 두고
   집계에서 제외한다. '원가 없음'과 '원가 0원'을 구분하기 위함이다.

SQLite 는 ALTER TABLE 제약이 크므로 batch_alter_table 을 사용한다
(migrations/env.py 의 render_as_batch=True 와 동일 전략).

주: 초기 요율 시딩은 본 마이그레이션에 넣지 않는다. 단가는 사업적 판단이
    개입되는 데이터이며 환경별로 달라질 수 있으므로, 스키마(구조) 변경과
    데이터 입력을 분리한다. 시딩은 scripts/seed_ccp_rates.py 로 수행한다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "l1_ccp_cost_attribution"
down_revision = "k1_content_link_lang"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1) 요율 카드 테이블 ────────────────────────────────────────────────
    op.create_table(
        "ccp_rate_card",
        sa.Column("rate_card_id", sa.String(40), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("input_price_per_1k", sa.Numeric(18, 6), nullable=False),
        sa.Column("output_price_per_1k", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="KRW"),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("effective_to", sa.DateTime(), nullable=True),
        sa.Column("source_note", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "provider",
            "model",
            "effective_from",
            name="uq_ccp_rate_card_scope_from",
        ),
    )
    op.create_index(
        "ix_ccp_rate_card_lookup",
        "ccp_rate_card",
        ["provider", "model", "effective_from"],
    )

    # ── 2) interaction 원가 컬럼 ──────────────────────────────────────────
    with op.batch_alter_table("interaction") as batch_op:
        batch_op.add_column(sa.Column("llm_provider", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("llm_model", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("prompt_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("completion_tokens", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("cost_krw", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("rate_card_id", sa.String(40), nullable=True))

    # provider 별 원가 집계가 관리자 대시보드의 주 질의이므로 인덱스 추가.
    op.create_index(
        "ix_interaction_llm_provider", "interaction", ["llm_provider"]
    )


def downgrade():
    op.drop_index("ix_interaction_llm_provider", table_name="interaction")

    with op.batch_alter_table("interaction") as batch_op:
        batch_op.drop_column("rate_card_id")
        batch_op.drop_column("cost_krw")
        batch_op.drop_column("completion_tokens")
        batch_op.drop_column("prompt_tokens")
        batch_op.drop_column("llm_model")
        batch_op.drop_column("llm_provider")

    op.drop_index("ix_ccp_rate_card_lookup", table_name="ccp_rate_card")
    op.drop_table("ccp_rate_card")
