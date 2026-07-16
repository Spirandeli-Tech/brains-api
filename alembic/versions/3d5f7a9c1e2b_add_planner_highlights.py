"""add planner_runs highlights

Revision ID: 3d5f7a9c1e2b
Revises: 2c4e6a8b0d1f
Create Date: 2026-07-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3d5f7a9c1e2b'
down_revision: Union[str, None] = '2c4e6a8b0d1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'planner_runs',
        sa.Column('highlights', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('planner_runs', 'highlights')
