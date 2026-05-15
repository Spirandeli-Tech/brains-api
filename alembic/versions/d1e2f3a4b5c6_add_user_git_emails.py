"""add user_git_emails

Revision ID: d1e2f3a4b5c6
Revises: c1a2b3d4e5f6
Create Date: 2026-05-01 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_git_emails',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'email', name='uq_user_git_emails_user_email'),
    )
    op.create_index('ix_user_git_emails_user_id', 'user_git_emails', ['user_id'])
    op.create_index('ix_user_git_emails_email', 'user_git_emails', ['email'])


def downgrade() -> None:
    op.drop_index('ix_user_git_emails_email', table_name='user_git_emails')
    op.drop_index('ix_user_git_emails_user_id', table_name='user_git_emails')
    op.drop_table('user_git_emails')
