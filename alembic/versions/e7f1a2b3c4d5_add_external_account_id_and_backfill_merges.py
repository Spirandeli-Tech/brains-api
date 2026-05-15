"""add external_account_id to connections and backfill merge commits

Revision ID: e7f1a2b3c4d5
Revises: d1e2f3a4b5c6
Create Date: 2026-05-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7f1a2b3c4d5'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'productivity_connections',
        sa.Column('external_account_id', sa.String(), nullable=True),
    )
    op.create_index(
        'ix_prod_connections_external_account_id',
        'productivity_connections',
        ['provider', 'external_account_id'],
    )

    # Backfill is_merge for commits the previous migration missed — notably
    # Bitbucket UI merges ("Merged in feature/X (pull request #123)") and
    # plain "Merge feature/X into feature/Y" commits done via squash/FF
    # which leave only one parent and so weren't caught by len(parents) > 1.
    op.execute(
        """
        UPDATE productivity_commits
        SET is_merge = TRUE
        WHERE is_merge = FALSE
          AND (
                message LIKE 'Merge %'
             OR message LIKE 'Merged %'
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        'ix_prod_connections_external_account_id',
        table_name='productivity_connections',
    )
    op.drop_column('productivity_connections', 'external_account_id')
