"""merge quiz-attempts-questions with master

Revision ID: 5b826603c92d
Revises: bdac69742a76, f1a2b3c4d5e6
Create Date: 2026-09-10 22:27:10.257496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b826603c92d'
down_revision: Union[str, None] = ('bdac69742a76', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
