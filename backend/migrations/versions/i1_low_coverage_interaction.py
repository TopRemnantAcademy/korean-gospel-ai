"""V-4: low_coverage column on interaction

Revision ID: i1_low_coverage_interaction
Revises: h1_drop_glossary_terms
Create Date: 2026-07-29 12:00:00.000000

"""
from typing import Sequence, Union

from sqlalchemy import Boolean, Column
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'i1_low_coverage_interaction'
down_revision: Union[str, None] = 'h1_drop_glossary_terms'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    try:
        result = conn.execute(
            __import__("sqlalchemy").text(
                f"SELECT {column} FROM {table} LIMIT 1"
            )
        )
        result.close()
        return True
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "interaction", "low_coverage"):
        op.add_column("interaction", Column("low_coverage", Boolean, default=False))


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "interaction", "low_coverage"):
        with op.batch_alter_table("interaction") as batch_op:
            batch_op.drop_column("low_coverage")
