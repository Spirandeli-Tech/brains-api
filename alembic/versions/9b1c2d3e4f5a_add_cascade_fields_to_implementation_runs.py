"""add cascade fields to implementation_runs

Revision ID: 9b1c2d3e4f5a
Revises: c5d6e7f8a9b0
Create Date: 2026-07-03 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9b1c2d3e4f5a"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "implementation_runs",
        sa.Column("repo_names", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "implementation_runs",
        sa.Column("cascade_stages", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "implementation_runs",
        sa.Column("pr_targets", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("implementation_runs", "pr_targets")
    op.drop_column("implementation_runs", "cascade_stages")
    op.drop_column("implementation_runs", "repo_names")
