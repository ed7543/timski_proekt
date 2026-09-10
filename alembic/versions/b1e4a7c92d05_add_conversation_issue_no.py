"""add conversation issue_no

Revision ID: b1e4a7c92d05
Revises: 517815f4fbca
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1e4a7c92d05'
down_revision: Union[str, None] = '517815f4fbca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('conversation_seq', sa.Integer(), nullable=False, server_default='0'))
    # Nullable for the backfill step below, then tightened to NOT NULL once
    # every existing row has a value.
    op.add_column('conversations', sa.Column('issue_no', sa.Integer(), nullable=True))

    # Backfill: number each user's existing conversations 1..N in creation
    # order (matching what the old client-side computation already showed
    # for current, non-deleted data), then set conversation_seq to the
    # highest issue_no handed out so future conversations keep counting up
    # instead of restarting from 0.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at ASC) AS rn
            FROM conversations
        )
        UPDATE conversations
        SET issue_no = ranked.rn
        FROM ranked
        WHERE conversations.id = ranked.id
        """
    )
    op.execute(
        """
        UPDATE users
        SET conversation_seq = COALESCE(
            (SELECT MAX(issue_no) FROM conversations WHERE conversations.user_id = users.id),
            0
        )
        """
    )

    op.alter_column('conversations', 'issue_no', nullable=False)
    op.alter_column('users', 'conversation_seq', server_default=None)


def downgrade() -> None:
    op.drop_column('conversations', 'issue_no')
    op.drop_column('users', 'conversation_seq')
