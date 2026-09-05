"""merge three-way branch migrations

Revision ID: 1d285a133389
Revises: 4b6f1e8a2d3c, bc6e93a07557, e4b8df6c3f05
Create Date: 2026-09-05 18:54:17.801024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d285a133389'
down_revision: Union[str, None] = ('4b6f1e8a2d3c', 'bc6e93a07557', 'e4b8df6c3f05')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
