"""add_is_merge_to_productivity_commits

Revision ID: b9d2c4e5f1a3
Revises: e891a3b4c5d6
Create Date: 2026-04-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d2c4e5f1a3'
down_revision: Union[str, None] = 'e891a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'productivity_commits',
        sa.Column('is_merge', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE productivity_commits
        SET is_merge = TRUE
        WHERE message LIKE 'Merge pull request%'
           OR message LIKE 'Merge branch%'
           OR message LIKE 'Merge remote-tracking branch%'
        """
    )
    op.create_index(
        'ix_prod_commits_is_merge',
        'productivity_commits',
        ['connection_id', 'is_merge'],
    )


def downgrade() -> None:
    op.drop_index('ix_prod_commits_is_merge', table_name='productivity_commits')
    op.drop_column('productivity_commits', 'is_merge')
