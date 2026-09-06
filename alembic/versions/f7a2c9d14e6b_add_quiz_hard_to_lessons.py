"""add quiz_hard to lessons

Revision ID: f7a2c9d14e6b
Revises: 1d285a133389
Create Date: 2026-09-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f7a2c9d14e6b'
down_revision: Union[str, None] = '1d285a133389'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Second, independent quiz tier per lesson ("Hard", alongside the
    # existing `quiz` column which now represents "Medium"). Kept as its own
    # nullable column rather than reshaping `quiz` into a {difficulty: ...}
    # dict, so every already-generated quiz stays exactly as-is (no backfill,
    # no risk of misreading old rows) - Hard is purely additive and generated
    # on demand, same flow as the original quiz generation.
    op.add_column('lessons', sa.Column('quiz_hard', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('lessons', sa.Column('quiz_hard_generated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('lessons', 'quiz_hard_generated_at')
    op.drop_column('lessons', 'quiz_hard')
