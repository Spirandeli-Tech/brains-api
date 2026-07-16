"""add planner prefs to user_preferences

Revision ID: 2c4e6a8b0d1f
Revises: 1b3d5f7a9c2e
Create Date: 2026-07-16 00:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2c4e6a8b0d1f'
down_revision: Union[str, None] = '1b3d5f7a9c2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_preferences',
        sa.Column('planner_enabled', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'user_preferences',
        sa.Column('planner_hour', sa.Integer(), server_default='7', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('user_preferences', 'planner_hour')
    op.drop_column('user_preferences', 'planner_enabled')
