"""add generation_method to lessons

Revision ID: d8f3a1c9b274
Revises: 517815f4fbca
Create Date: 2026-09-10 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f3a1c9b274'
down_revision: Union[str, None] = '517815f4fbca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable=False + server_default='source': every existing lesson row
    # (all of which were generated the original, source-grounded way, before
    # --generate-without-source/--force-general-knowledge existed) backfills
    # to 'source' automatically - see backend/database/models.py's Lesson
    # docstring for what this column tracks.
    op.add_column(
        'lessons',
        sa.Column('generation_method', sa.String(length=20), nullable=False, server_default='source'),
    )


def downgrade() -> None:
    op.drop_column('lessons', 'generation_method')
