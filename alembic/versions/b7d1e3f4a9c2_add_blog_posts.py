"""add blog posts

Revision ID: b7d1e3f4a9c2
Revises: a3f6e9c1b482
Create Date: 2026-09-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1e3f4a9c2'
down_revision: Union[str, None] = 'a3f6e9c1b482'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'blog_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=1000), nullable=True),
        sa.Column('source_url', sa.String(length=1000), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=False),
        sa.Column('added_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['added_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('blog_posts')
