"""add_instructions_to_automations

Revision ID: b7c8d9e0f1a2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('instructions', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'instructions')
