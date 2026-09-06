"""add conversation members and invites

Revision ID: c7d2f4a9e1b6
Revises: f7a2c9d14e6b
Create Date: 2026-09-06 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2f4a9e1b6'
down_revision: Union[str, None] = 'f7a2c9d14e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('author_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_chat_messages_author_user_id_users', 'chat_messages', 'users',
        ['author_user_id'], ['id'],
    )

    op.create_table(
        'conversation_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'user_id', name='uq_conversation_members_conv_user'),
    )
    op.create_index(op.f('ix_conversation_members_conversation_id'), 'conversation_members', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_conversation_members_user_id'), 'conversation_members', ['user_id'], unique=False)

    op.create_table(
        'conversation_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index(op.f('ix_conversation_invites_conversation_id'), 'conversation_invites', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_conversation_invites_token'), 'conversation_invites', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_conversation_invites_token'), table_name='conversation_invites')
    op.drop_index(op.f('ix_conversation_invites_conversation_id'), table_name='conversation_invites')
    op.drop_table('conversation_invites')

    op.drop_index(op.f('ix_conversation_members_user_id'), table_name='conversation_members')
    op.drop_index(op.f('ix_conversation_members_conversation_id'), table_name='conversation_members')
    op.drop_table('conversation_members')

    op.drop_constraint('fk_chat_messages_author_user_id_users', 'chat_messages', type_='foreignkey')
    op.drop_column('chat_messages', 'author_user_id')
