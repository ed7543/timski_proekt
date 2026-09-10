"""merge blog, conversation-issue-no, and generation-method heads

Revision ID: bdac69742a76
Revises: 9304b6394e56, b1e4a7c92d05, d8f3a1c9b274
Create Date: 2026-09-10 21:25:17.187033

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bdac69742a76'
down_revision: Union[str, None] = ('9304b6394e56', 'b1e4a7c92d05', 'd8f3a1c9b274')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
