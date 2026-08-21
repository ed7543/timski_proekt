"""add lessons course_sources

Revision ID: bc6e93a07557
Revises: 8dd1cdb251ad
Create Date: 2026-08-21 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bc6e93a07557'
down_revision: Union[str, None] = '8dd1cdb251ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Storage for the Gemini-generated lesson-content pipeline (courses_db.json /
    # "LearnWise - база извори" spreadsheet). Both tables FK into the existing
    # `courses` table by design - all 67 courses already exist there (ingested
    # from finki-hub.com), so no changes to `courses` itself are needed here.
    op.create_table('lessons',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('topic_title', sa.Text(), nullable=False),
    sa.Column('documentation', sa.Text(), nullable=True),
    sa.Column('quiz', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('documentation_generated_at', sa.DateTime(), nullable=True),
    sa.Column('quiz_generated_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lessons_course_id'), 'lessons', ['course_id'], unique=False)

    op.create_table('course_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('author', sa.String(length=255), nullable=True),
    sa.Column('publisher', sa.String(length=255), nullable=True),
    sa.Column('license', sa.String(length=255), nullable=True),
    sa.Column('url', sa.String(length=1000), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_course_sources_course_id'), 'course_sources', ['course_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_course_sources_course_id'), table_name='course_sources')
    op.drop_table('course_sources')
    op.drop_index(op.f('ix_lessons_course_id'), table_name='lessons')
    op.drop_table('lessons')
