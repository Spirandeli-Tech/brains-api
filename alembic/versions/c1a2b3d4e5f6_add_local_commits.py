"""add_local_commits

Revision ID: c1a2b3d4e5f6
Revises: b9d2c4e5f1a3
Create Date: 2026-04-26 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = 'b9d2c4e5f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'local_commits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('hash', sa.String(length=40), nullable=False),
        sa.Column('short_hash', sa.String(length=7), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('author', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('committed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('branch', sa.String(), nullable=False),
        sa.Column('additions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deletions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('repo_name', sa.String(), nullable=False),
        sa.Column('remote_url', sa.String(), nullable=False, server_default=''),
        sa.Column('source', sa.String(), nullable=False, server_default='qwe'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('hash', 'remote_url', name='uq_local_commits_hash_remote'),
    )
    op.create_index('ix_local_commits_committed_at', 'local_commits', ['committed_at'])
    op.create_index('ix_local_commits_email', 'local_commits', ['email'])


def downgrade() -> None:
    op.drop_index('ix_local_commits_email', table_name='local_commits')
    op.drop_index('ix_local_commits_committed_at', table_name='local_commits')
    op.drop_table('local_commits')
