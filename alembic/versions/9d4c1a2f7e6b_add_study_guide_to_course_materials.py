"""add study guide (documentation + quiz/quiz_hard) to course_materials

Revision ID: 9d4c1a2f7e6b
Revises: a3f6e9c1b482
Create Date: 2026-09-06 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9d4c1a2f7e6b'
down_revision: Union[str, None] = 'a3f6e9c1b482'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Marketplace equivalent of the lessons/quiz_hard split (migration
    # f7a2c9d14e6b) - `quiz` is the default/"Medium" tier, `quiz_hard` is a
    # second, independent tier generated on demand. Both share
    # gemini_generator.generate_quiz(difficulty=...) - see courseRoute.py's
    # study-guide endpoints.
    op.add_column('course_materials', sa.Column('documentation', sa.Text(), nullable=True))
    op.add_column('course_materials', sa.Column('quiz', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('course_materials', sa.Column('quiz_hard', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('course_materials', sa.Column('documentation_generated_at', sa.DateTime(), nullable=True))
    op.add_column('course_materials', sa.Column('quiz_generated_at', sa.DateTime(), nullable=True))
    op.add_column('course_materials', sa.Column('quiz_hard_generated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('course_materials', 'quiz_hard_generated_at')
    op.drop_column('course_materials', 'quiz_generated_at')
    op.drop_column('course_materials', 'documentation_generated_at')
    op.drop_column('course_materials', 'quiz_hard')
    op.drop_column('course_materials', 'quiz')
    op.drop_column('course_materials', 'documentation')
