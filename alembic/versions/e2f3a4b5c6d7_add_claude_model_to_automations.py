"""add_claude_model_to_automations

Revision ID: e2f3a4b5c6d7
Revises: c4d5e6f7a8b9
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('claude_model', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'claude_model')
