"""merge blog and study guide branches

Revision ID: 9304b6394e56
Revises: 517815f4fbca, c9e2a5f18b3d
Create Date: 2026-09-10 15:19:20.145881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9304b6394e56'
down_revision: Union[str, None] = ('517815f4fbca', 'c9e2a5f18b3d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
