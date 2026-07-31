"""add_tags_to_automations

Revision ID: 30877432d102
Revises: b8c9d0e1f2a3
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '30877432d102'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automations', sa.Column('tags', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('automations', 'tags')
