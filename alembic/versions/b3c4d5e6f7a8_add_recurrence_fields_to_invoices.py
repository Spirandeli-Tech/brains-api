"""add_recurrence_fields_to_invoices

Revision ID: b3c4d5e6f7a8
Revises: f7a8b9c0d1e2
Create Date: 2026-02-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('is_recurrent', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('invoices', sa.Column('recurrence_frequency', sa.String(), nullable=True))
    op.add_column('invoices', sa.Column('recurrence_day', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('invoices', 'recurrence_day')
    op.drop_column('invoices', 'recurrence_frequency')
    op.drop_column('invoices', 'is_recurrent')
