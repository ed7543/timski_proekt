"""add quiz_attempts

Revision ID: 966b98935174
Revises: 90c99f0eb73f
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '966b98935174'
down_revision: Union[str, None] = '90c99f0eb73f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('quiz_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('topic', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=100), nullable=True),
    sa.Column('total_questions', sa.Integer(), nullable=False),
    sa.Column('answered_count', sa.Integer(), nullable=False),
    sa.Column('correct_count', sa.Integer(), nullable=False),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quiz_attempts_user_id'), 'quiz_attempts', ['user_id'], unique=False)
    op.create_index(op.f('ix_quiz_attempts_subject'), 'quiz_attempts', ['subject'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quiz_attempts_subject'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_user_id'), table_name='quiz_attempts')
    op.drop_table('quiz_attempts')
