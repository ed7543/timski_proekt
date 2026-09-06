"""merge study-guide and conversation-invites heads

Revision ID: 517815f4fbca
Revises: 9d4c1a2f7e6b, c7d2f4a9e1b6
Create Date: 2026-09-06 21:32:08.133266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '517815f4fbca'
down_revision: Union[str, None] = ('9d4c1a2f7e6b', 'c7d2f4a9e1b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
