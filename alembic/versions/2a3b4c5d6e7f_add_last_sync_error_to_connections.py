"""add_last_sync_error_to_connections

Revision ID: 2a3b4c5d6e7f
Revises: 1d1e2b0b1a99
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2a3b4c5d6e7f'
down_revision: Union[str, None] = '1d1e2b0b1a99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'productivity_connections',
        sa.Column('last_sync_attempted_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'productivity_connections',
        sa.Column('last_sync_status', sa.String(), nullable=True),
    )
    op.add_column(
        'productivity_connections',
        sa.Column('last_sync_error', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('productivity_connections', 'last_sync_error')
    op.drop_column('productivity_connections', 'last_sync_status')
    op.drop_column('productivity_connections', 'last_sync_attempted_at')
