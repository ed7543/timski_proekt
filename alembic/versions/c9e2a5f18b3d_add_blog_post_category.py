"""add category to blog posts

Revision ID: c9e2a5f18b3d
Revises: b7d1e3f4a9c2
Create Date: 2026-09-06 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e2a5f18b3d'
down_revision: Union[str, None] = 'b7d1e3f4a9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('blog_posts', sa.Column('category', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('blog_posts', 'category')
