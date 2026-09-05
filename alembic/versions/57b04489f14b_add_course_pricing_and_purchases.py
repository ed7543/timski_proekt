"""add course pricing and purchases

Revision ID: 57b04489f14b
Revises: 00c85bd8ad0c
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57b04489f14b'
down_revision: Union[str, None] = '00c85bd8ad0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('courses', sa.Column('price_cents', sa.Integer(), nullable=False, server_default='0'))

    op.create_table(
        'course_purchases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'course_id', name='uq_course_purchases_user_course'),
    )
    op.create_index(op.f('ix_course_purchases_user_id'), 'course_purchases', ['user_id'], unique=False)
    op.create_index(op.f('ix_course_purchases_course_id'), 'course_purchases', ['course_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_course_purchases_course_id'), table_name='course_purchases')
    op.drop_index(op.f('ix_course_purchases_user_id'), table_name='course_purchases')
    op.drop_table('course_purchases')
    op.drop_column('courses', 'price_cents')
