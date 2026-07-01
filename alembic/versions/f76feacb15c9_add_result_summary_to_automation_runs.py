"""add_result_summary_to_automation_runs

Revision ID: f76feacb15c9
Revises: c9d0e1f2a3b4
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f76feacb15c9'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('automation_runs', sa.Column('result_summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('automation_runs', 'result_summary')
