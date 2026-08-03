"""add_restart_requested_at_to_runner_heartbeats

Revision ID: 31f4c9ab7de1
Revises: 30877432d102
Create Date: 2026-08-03 07:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '31f4c9ab7de1'
down_revision: Union[str, None] = '30877432d102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'runner_heartbeats',
        sa.Column('restart_requested_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('runner_heartbeats', 'restart_requested_at')
