"""add_meta_to_automations

Revision ID: b7c1d2e3f4a5
Revises: 4e6f8b0c2d3a
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, None] = '4e6f8b0c2d3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('meta', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'meta')
