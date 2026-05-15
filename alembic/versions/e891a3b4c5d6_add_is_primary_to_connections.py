"""add_is_primary_to_connections

Revision ID: e891a3b4c5d6
Revises: d789f2000805
Create Date: 2026-04-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e891a3b4c5d6'
down_revision: Union[str, None] = 'd789f2000805'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'productivity_connections',
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        'ix_prod_connections_primary',
        'productivity_connections',
        ['created_by_user_id', 'provider', 'is_primary'],
    )


def downgrade() -> None:
    op.drop_index('ix_prod_connections_primary', table_name='productivity_connections')
    op.drop_column('productivity_connections', 'is_primary')
