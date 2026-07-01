"""add_days_of_week_to_automations

Revision ID: 1d1e2b0b1a99
Revises: 34139f659807
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1d1e2b0b1a99'
down_revision: Union[str, None] = '34139f659807'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('days_of_week', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'days_of_week')
