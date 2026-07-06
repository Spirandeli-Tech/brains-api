"""add repo_name to implementation_steps

Revision ID: 9c2d3e4f5a6b
Revises: 9b1c2d3e4f5a
Create Date: 2026-07-03 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c2d3e4f5a6b"
down_revision: Union[str, None] = "9b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "implementation_steps",
        sa.Column("repo_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("implementation_steps", "repo_name")
