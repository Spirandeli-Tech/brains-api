"""add_approved_to_impl_steps

Revision ID: b2d3f4a5c6e7
Revises: a1c2e3f4d5b6
Create Date: 2026-06-19 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2d3f4a5c6e7'
down_revision: Union[str, None] = 'a1c2e3f4d5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'implementation_steps',
        sa.Column('approved', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('implementation_steps', 'approved')
