"""add repo_name to implementation_runs

Revision ID: a2b3c4d5e6f7
Revises: c3e4a5b6d7f8
Create Date: 2026-06-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'c3e4a5b6d7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('implementation_runs', sa.Column('repo_name', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('implementation_runs', 'repo_name')
