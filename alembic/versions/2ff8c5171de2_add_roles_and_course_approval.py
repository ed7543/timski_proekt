"""add roles and course approval workflow

Revision ID: 2ff8c5171de2
Revises: 8dd1cdb251ad
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ff8c5171de2'
down_revision: Union[str, None] = '8dd1cdb251ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing rows (all current users become
    # "student", all current - already scraper-ingested - courses become
    # "approved"), matching the ORM-level Python defaults in models.py.
    op.add_column('users', sa.Column('role', sa.String(length=20), nullable=False, server_default='student'))

    op.add_column('courses', sa.Column('status', sa.String(length=20), nullable=False, server_default='approved'))
    op.add_column('courses', sa.Column('submitted_by_id', sa.Integer(), nullable=True))
    op.add_column('courses', sa.Column('reviewed_by_id', sa.Integer(), nullable=True))
    op.add_column('courses', sa.Column('reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('courses', sa.Column('rejection_reason', sa.Text(), nullable=True))
    op.create_foreign_key('fk_courses_submitted_by_id_users', 'courses', 'users', ['submitted_by_id'], ['id'])
    op.create_foreign_key('fk_courses_reviewed_by_id_users', 'courses', 'users', ['reviewed_by_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_courses_reviewed_by_id_users', 'courses', type_='foreignkey')
    op.drop_constraint('fk_courses_submitted_by_id_users', 'courses', type_='foreignkey')
    op.drop_column('courses', 'rejection_reason')
    op.drop_column('courses', 'reviewed_at')
    op.drop_column('courses', 'reviewed_by_id')
    op.drop_column('courses', 'status')
    op.drop_column('users', 'role')
