"""add runner_heartbeats

Revision ID: 4e6f8b0c2d3a
Revises: 3d5f7a9c1e2b
Create Date: 2026-07-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4e6f8b0c2d3a'
down_revision: Union[str, None] = '3d5f7a9c1e2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'runner_heartbeats',
        sa.Column('runner_id', sa.String(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('poll_interval', sa.String(), nullable=True),
        sa.Column('dry_run', sa.Boolean(), nullable=True),
        sa.Column('version', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('runner_id'),
    )


def downgrade() -> None:
    op.drop_table('runner_heartbeats')
