"""add automation ephemeral flag

Revision ID: 1b3d5f7a9c2e
Revises: 12a06171c704
Create Date: 2026-07-16 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1b3d5f7a9c2e'
down_revision: Union[str, None] = '12a06171c704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'automations',
        sa.Column('ephemeral', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('automations', 'ephemeral')
