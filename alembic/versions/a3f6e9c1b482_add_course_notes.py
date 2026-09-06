"""add course notes

Revision ID: a3f6e9c1b482
Revises: f7a2c9d14e6b
Create Date: 2026-09-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f6e9c1b482'
down_revision: Union[str, None] = 'f7a2c9d14e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'course_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id']),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_course_notes_course_id'), 'course_notes', ['course_id'], unique=False)
    op.create_index(op.f('ix_course_notes_uploaded_by_id'), 'course_notes', ['uploaded_by_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_course_notes_uploaded_by_id'), table_name='course_notes')
    op.drop_index(op.f('ix_course_notes_course_id'), table_name='course_notes')
    op.drop_table('course_notes')
