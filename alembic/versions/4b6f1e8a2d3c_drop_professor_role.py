"""data migration: retire the 'professor' role value

The app no longer distinguishes a 'professor' role anywhere in permission
checks - it never did anything beyond gating the "My courses" nav link,
which is now driven by is_premium / has_submitted_courses instead (see
routes/auth/__init__.py::me). Any existing users with role='professor'
are downgraded to the plain 'student' role; nothing else about their
account (is_premium, submitted courses, etc.) changes.

Revision ID: 4b6f1e8a2d3c
Revises: 9a1f3c7b2e4d
Create Date: 2026-09-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b6f1e8a2d3c'
down_revision: Union[str, None] = '9a1f3c7b2e4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'student' WHERE role = 'professor'")


def downgrade() -> None:
    # Irreversible by design - we have no record of which students used to
    # be 'professor', so there's nothing sensible to restore.
    pass
